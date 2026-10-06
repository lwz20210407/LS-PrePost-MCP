"""Deterministic L3 graders: read the final deck with the keyword engine and the agent's last answer.

Every check returns ``(ok, detail)``. No check trusts the agent's own report; decks are re-read from
disk. The final deck is chosen by :meth:`Workspace.final_deck`; checks that need one fail when no
deck was written. A check that raises is a failed check with the error as detail.
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.geometry import elements, nodes

from .scenario import Check, Workspace, sha256


class CheckFailed(Exception):
    pass


@dataclass
class Context:
    workspace: Workspace
    answer: str = ""
    _decks: dict[Path, KeywordDeck] = field(default_factory=dict)

    def final(self) -> KeywordDeck:
        path = self.workspace.final_deck()
        if path is None:
            raise CheckFailed("no output deck was written under jobs/")
        return self.load(path)

    def initial(self) -> KeywordDeck:
        if not self.workspace.scenario.model:
            raise CheckFailed("scenario has no input model")
        return self.load(self.workspace.root / self.workspace.scenario.model)

    def load(self, path: Path) -> KeywordDeck:
        if path not in self._decks:
            self._decks[path] = KeywordDeck.load(path)
        return self._decks[path]


def _close(actual: object, expected: float, rel_tol: float) -> bool:
    try:
        return math.isclose(float(actual), float(expected), rel_tol=rel_tol, abs_tol=1e-30)
    except (TypeError, ValueError):
        return False


def records(deck: KeywordDeck, pattern: str) -> list[dict]:
    """Field values of every block (and row of table keywords) matching ``pattern``."""
    found = []
    for block in deck.blocks(pattern):
        layout = deck.layout(block)
        rows = list(layout.rows) if layout.key else [None]
        for row in rows:
            values = {f.name: f.value for f in deck.fields(block, row)}
            found.append({"_keyword": block.name, **values})
    return found


def _members(deck: KeywordDeck, kind: str, sid: int) -> set[int]:
    prefix = f"*SET_{kind.upper()}"
    for block in deck.iter_blocks():
        name = block.name
        if not (name == prefix or name.startswith(prefix + "_")) or any(
                tag in name for tag in ("_ADD", "_GENERATE", "_INTERSECT", "_COLUMN")):
            continue
        if int(deck.get(block, "sid").value) == int(sid):
            return set(deck.members(block))
    raise CheckFailed(f"*SET_{kind.upper()} {sid} is not defined as a list set")


def _solids(deck: KeywordDeck) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    eids, pids, conn = elements(deck, "*ELEMENT_SOLID", 8)
    return eids, pids, conn


def _node_xyz(deck: KeywordDeck) -> dict[int, np.ndarray]:
    ids, xyz = nodes(deck)
    return dict(zip(ids.tolist(), xyz))


def select(deck: KeywordDeck, spec: dict) -> set[int]:
    """Nodes of ``parts`` (default all) with coordinate ``axis`` equal to ``value`` within ``tol``."""
    coords = _node_xyz(deck)
    chosen = set(coords)
    if "parts" in spec:
        _, pids, conn = _solids(deck)
        chosen = set(np.unique(conn[np.isin(pids, spec["parts"])]).tolist()) & chosen
    if "axis" in spec:
        axis = "xyz".index(spec["axis"])
        tol = float(spec.get("tol", 1e-6))
        chosen = {n for n in chosen if abs(coords[n][axis] - float(spec["value"])) <= tol}
    if not chosen:
        raise CheckFailed(f"node selection {spec} is empty")
    return chosen


def input_unchanged(ctx: Context) -> tuple[bool, str]:
    changed = [name for name, digest in ctx.workspace.input_hashes.items()
               if sha256(ctx.workspace.root / name) != digest]
    return not changed, f"changed inputs: {changed}" if changed else "inputs byte-identical"


def deck_consistent(ctx: Context) -> tuple[bool, str]:
    deck = ctx.final()
    report = deck.references(True)
    problems = [*map(str, deck.warnings)]
    if report.dangling_count:
        problems.append(f"{report.dangling_count} dangling references: {report.dangling()[:3]}")
    if report.unverified_count:
        problems.append(f"{report.unverified_count} references not verifiable")
    return not problems, "; ".join(problems) or f"{ctx.workspace.final_deck().name} reloads, no dangling IDs"


def field_values(ctx: Context, keyword: str, expect: dict, match: dict | None = None, rel_tol: float = 1e-6,
                 count: int | None = None) -> tuple[bool, str]:
    found = [r for r in records(ctx.final(), keyword) if all(_close(r.get(k), v, 1e-9) if isinstance(v, (int, float))
                                                              else r.get(k) == v for k, v in (match or {}).items())]
    if count is not None and len(found) != count:
        return False, f"{len(found)} {keyword} matching {match or {}} (expected {count})"
    for record in found:
        if all(_close(record.get(k), v, rel_tol) for k, v in expect.items()):
            return True, f"{record['_keyword']} {', '.join(f'{k}={record.get(k)}' for k in expect)}"
    actual = [{k: r.get(k) for k in expect} for r in found[:3]]
    return False, f"no {keyword} matching {match or {}} has {expect}; found {actual}"


def _referenced(deck: KeywordDeck, spec: dict, key: str, ident: int) -> tuple[bool, str]:
    patterns = spec["keyword"] if isinstance(spec["keyword"], list) else [spec["keyword"]]
    for pattern in patterns:
        for record in records(deck, pattern):
            if record.get(key) is not None and int(record[key]) == ident:
                bad = {k: record.get(k) for k, v in spec.get("expect", {}).items()
                       if not _close(record.get(k), v, float(spec.get("rel_tol", 1e-6)))}
                return not bad, f"{record['_keyword']} {ident}" + (f" differs: {bad}" if bad else "")
    return False, f"{key} {ident} is not a {patterns}"


def part_uses(ctx: Context, pid: int, material: dict | None = None, section: dict | None = None,
              eos: dict | None = None, new: tuple[str, ...] = ()) -> tuple[bool, str]:
    deck = ctx.final()
    rows = [r for r in records(deck, "*PART") if int(r["pid"]) == int(pid)]
    if len(rows) != 1:
        return False, f"{len(rows)} *PART rows with pid {pid}"
    part, details, ok = rows[0], [], True
    before = ctx.initial().references(False).defined
    for kind, key, spec in (("material", "mid", material), ("section", "secid", section), ("eos", "eosid", eos)):
        if spec is None:
            continue
        ident = int(part.get(key) or 0)
        good, text = _referenced(deck, spec, key, ident)
        if kind in new and ident in before.get(kind, set()):
            good, text = False, f"{kind} {ident} already existed in the input; a new one was requested"
        ok &= good
        details.append(text)
    return ok, "; ".join(details)


def node_set(ctx: Context, sid: int, nodes: dict) -> tuple[bool, str]:
    deck = ctx.final()
    members, wanted = _members(deck, "node", sid), select(deck, nodes)
    missing, extra = sorted(wanted - members), sorted(members - wanted)
    return not (missing or extra), f"set {sid}: {len(members)} nodes; missing {missing[:5]}, extra {extra[:5]}"


def _set_nodes(deck: KeywordDeck, nsid: int) -> set[int]:
    return set(_node_xyz(deck)) if int(nsid) == 0 else _members(deck, "node", nsid)


def spc_nodes(ctx: Context, nodes: dict, exclusive: bool = True) -> tuple[bool, str]:
    deck = ctx.final()
    dofs = ("dofx", "dofy", "dofz", "dofrx", "dofry", "dofrz")
    fixed: dict[int, set[str]] = {}
    for record in records(deck, "*BOUNDARY_SPC_SET"):
        for nid in _set_nodes(deck, record["nsid"]):
            fixed.setdefault(nid, set()).update(d for d in dofs if int(record.get(d) or 0) == 1)
    for record in records(deck, "*BOUNDARY_SPC_NODE"):
        fixed.setdefault(int(record["nid"]), set()).update(d for d in dofs if int(record.get(d) or 0) == 1)
    wanted = select(deck, nodes)
    partial = sorted(n for n in wanted if fixed.get(n) != set(dofs))
    extra = sorted(set(fixed) - wanted) if exclusive else []
    return not (partial or extra), f"{len(wanted)} nodes; not fully fixed {partial[:5]}; others fixed {extra[:5]}"


def _velocities(deck: KeywordDeck) -> dict[int, np.ndarray]:
    found: dict[int, np.ndarray] = {}
    _, pids, conn = _solids(deck)
    for record in records(deck, "*INITIAL_VELOCITY_GENERATION"):
        if float(record.get("omega") or 0.0):
            raise CheckFailed("rotational initial velocity is not graded")
        styp, ident = int(record["styp"]), int(record["id"])
        parts = [ident] if styp == 2 else sorted(_members(deck, "part", ident)) if styp == 1 else None
        targets = set(np.unique(conn[np.isin(pids, parts)]).tolist()) if parts else _set_nodes(deck, ident)
        for nid in targets:
            found[nid] = np.array([record["vx"], record["vy"], record["vz"]], dtype=float)
    for record in records(deck, "*INITIAL_VELOCITY"):
        for nid in _set_nodes(deck, record["nsid"]):
            found[nid] = np.array([record["vx"], record["vy"], record["vz"]], dtype=float)
    for record in records(deck, "*INITIAL_VELOCITY_NODE"):
        found[int(record["nid"])] = np.array([record["vx"], record["vy"], record["vz"]], dtype=float)
    return found


def initial_velocity(ctx: Context, nodes: dict, velocity: list[float], rel_tol: float = 1e-6) -> tuple[bool, str]:
    deck = ctx.final()
    found, wanted, target = _velocities(deck), select(deck, nodes), np.array(velocity, dtype=float)
    scale = float(np.linalg.norm(target)) or 1.0
    wrong = sorted(n for n in wanted if n not in found or np.linalg.norm(found[n] - target) > rel_tol * scale)
    moving = sorted(n for n, v in found.items() if n not in wanted and np.linalg.norm(v) > 0)
    sample = {n: found.get(n, np.zeros(3)).tolist() for n in wrong[:2]}
    return not (wrong or moving), f"{len(wanted)} nodes; wrong {wrong[:5]} {sample}; others moving {moving[:5]}"


def _side_parts(deck: KeywordDeck, ident: int, styp: int) -> frozenset[int]:
    if styp == 3:
        return frozenset({int(ident)})
    if styp in (2, 6):
        return frozenset(_members(deck, "part", ident))
    raise CheckFailed(f"contact surface type {styp} is not graded (use part or part set)")


def contact(ctx: Context, keyword: str | list[str], parts: list[list[int]], expect: dict | None = None,
            rel_tol: float = 1e-6) -> tuple[bool, str]:
    deck, wanted = ctx.final(), {frozenset(side) for side in parts}
    patterns = keyword if isinstance(keyword, list) else [keyword]
    seen = []
    for pattern in patterns:
        for record in records(deck, pattern):
            # PyDYNA 0.12 names the sides surfa/surfb (R11 manual: ssid/msid)
            a, at, b, bt = (("surfa", "surfatyp", "surfb", "surfbtyp") if "surfa" in record
                            else ("ssid", "sstyp", "msid", "mstyp"))
            sides = {_side_parts(deck, record[a], int(record[at])), _side_parts(deck, record[b], int(record[bt]))}
            values = {k: record.get(k) for k in (expect or {})}
            seen.append((record["_keyword"], [sorted(s) for s in sides], values))
            if sides == wanted and all(_close(record.get(k), v, rel_tol) for k, v in (expect or {}).items()):
                return True, f"{record['_keyword']} between {[sorted(s) for s in sides]} {values}"
    return False, f"no {patterns} between {[sorted(s) for s in wanted]} with {expect}; found {seen[:3]}"


def _centroids(deck: KeywordDeck, parts: list[int] | None = None) -> np.ndarray:
    coords = _node_xyz(deck)
    _, pids, conn = _solids(deck)
    rows = conn if parts is None else conn[np.isin(pids, parts)]
    return np.array([np.mean([coords[n] for n in row], axis=0) for row in rows]).reshape(-1, 3)


def solid_copies(ctx: Context, part: int, offsets: list[list[float]], tol: float = 1e-6) -> tuple[bool, str]:
    source = _centroids(ctx.initial(), [part])
    before, after = _centroids(ctx.initial()), _centroids(ctx.final())

    def count(points: np.ndarray) -> int:
        return sum(bool(np.any(np.linalg.norm(after - p, axis=1) <= tol)) for p in points)

    kept = count(before)
    copies = [count(source + np.array(offset, dtype=float)) for offset in offsets]
    expected_total = len(before) + len(source) * len(offsets)
    ok = kept == len(before) and all(c == len(source) for c in copies) and len(after) == expected_total
    return ok, f"original kept {kept}/{len(before)}; copies {copies} of {len(source)}; solids {len(after)}/" \
               f"{expected_total}"


def answer_contains(ctx: Context, all_of: list[str] = (), any_of: list[list[str]] = ()) -> tuple[bool, str]:
    text = ctx.answer.lower()
    missing = [item for item in all_of if not re.search(item.lower(), text)]
    unmet = [group for group in any_of if not any(re.search(item.lower(), text) for item in group)]
    return not (missing or unmet), f"missing {missing}; unmet groups {unmet}" if missing or unmet else "answer ok"


CHECKS: dict[str, Callable[..., tuple[bool, str]]] = {
    "input_unchanged": input_unchanged, "deck_consistent": deck_consistent, "field": field_values,
    "part_uses": part_uses, "node_set": node_set, "spc_nodes": spc_nodes, "initial_velocity": initial_velocity,
    "contact": contact, "solid_copies": solid_copies, "answer_contains": answer_contains,
}


def grade(ctx: Context, checks: list[Check]) -> list[dict]:
    results = []
    for item in checks:
        try:
            ok, detail = CHECKS[item.check](ctx, **item.params)
        except CheckFailed as error:
            ok, detail = False, str(error)
        except Exception as error:  # noqa: BLE001 - a grader error is a failed check, never a pass
            ok, detail = False, f"{type(error).__name__}: {error}"
        results.append({"check": item.check, "ok": bool(ok), "detail": detail})
    return results


__all__ = ["CHECKS", "CheckFailed", "Context", "grade", "records", "select"]
