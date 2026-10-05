"""JSON-friendly operations on keyword decks, intended as the backend of MCP tools.

* :func:`inspect_deck` - model overview (P01): files, include tree, parameters, parts,
  sections, materials, sets, curves, contacts and reference problems.
* :func:`read_fields` - named fields of matching blocks / rows.
* :func:`edit_deck` - an atomic batch of edits (P02) with dangling-reference guard and
  dry-run / save-as / in-place save (P11). Nothing is written unless every edit succeeds.

Inputs and outputs are plain JSON types; file paths are strings.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from . import lists
from .deck import Change, KeywordDeck
from .fields import FieldError
from .includes import identity
from .schema import Unsupported

MAX_DIFF = 20000


def _site(block: object) -> dict:
    return {"keyword": block.name, "file": str(block.file.path), "line": block.line_number}


def _values(deck: KeywordDeck, block: object, row: int | None, names: Iterable[str] | None = None) -> dict:
    lay = deck.layout(block)
    infos = list(lay.fields) + (list(lay.rows[row]) if row is not None and lay.key else [])
    wanted = {n.lower() for n in names} if names else None
    out = {}
    for info in infos:
        if wanted is None or info.name in wanted:
            value = deck._value(block, info)
            out[info.name] = {"value": value.value, "raw": value.raw.strip(), "parameter": value.parameter,
                              "card": value.card, "line": value.line}
    return out


def _safe(deck: KeywordDeck, block: object, row: int | None, names: Iterable[str]) -> dict:
    try:
        return {k: v["value"] for k, v in _values(deck, block, row, names).items()}
    except (Unsupported, FieldError, KeyError) as error:
        return {"error": str(error)}


def inspect_deck(path: str, include_paths: tuple[str, ...] = (), include_mesh: bool = False) -> dict:
    """Overview of a deck without modifying anything."""
    deck = KeywordDeck.load(path, include_paths)
    parts, sections, materials, sets, curves, contacts = [], [], [], [], [], []
    for block in deck.iter_blocks():
        base = lists.base_name(block.name)[0]
        try:
            if base == "*PART":
                for pid in deck.layout(block).rows:
                    parts.append({**_site(block), "pid": pid,
                                  **_safe(deck, block, pid, ("heading", "secid", "mid", "eosid", "hgid"))})
            elif base.startswith("*SECTION_"):
                sections.append({**_site(block), **_safe(deck, block, None, ("secid", "title"))})
            elif base.startswith("*MAT_") and not base.startswith("*MAT_ADD_"):
                materials.append({**_site(block), **_safe(deck, block, None, ("mid", "tmid", "title"))})
            elif lists.is_list_set(block.name):
                sets.append({**_site(block), **_safe(deck, block, None, ("sid", "title")),
                             "members": len(deck.members(block))})
            elif lists.is_curve(block.name):
                curves.append({**_site(block), **_safe(deck, block, None, ("lcid", "title")),
                               "points": len(deck.points(block))})
            elif base.startswith("*CONTACT_"):
                contacts.append({**_site(block), **_safe(deck, block, None,
                                                       ("cid", "surfa", "surfb", "surfatyp", "surfbtyp"))})
        except (Unsupported, FieldError) as error:
            deck.warnings.append(f"{block.name} at {_site(block)['file']}:{block.line_number}: {error}")
    report = deck.references(include_mesh)
    return {
        "summary": deck.summary(),
        "include_tree": deck.include_tree(),
        "parameters": [{"name": r.definition.name, "type": r.definition.type, "value": r.definition.value,
                        "raw": r.definition.raw, "expression": r.definition.expression,
                        "local": r.definition.local, "error": r.definition.error, **_site(r.block)}
                       for r in deck.parameters],
        "parts": parts, "sections": sections, "materials": materials, "sets": sets,
        "curves": curves, "contacts": contacts,
        "references": {**report.summary(), "dangling": report.dangling()[:200],
                       "duplicates": report.duplicates()[:200], "unused": report.unused(),
                       "mesh_checked": include_mesh},
        "read_only": True,
    }


def read_fields(path: str, keyword: str, match: dict | None = None, fields: list[str] | None = None,
                include_paths: tuple[str, ...] = ()) -> dict:
    """Named fields of every block (and row) matching ``keyword`` and ``match``."""
    deck = KeywordDeck.load(path, include_paths)
    results = []
    for block, row in deck.find(keyword, **(match or {})):
        try:
            results.append({**_site(block), "row": row, "fields": _values(deck, block, row, fields)})
        except (Unsupported, FieldError, KeyError) as error:
            results.append({**_site(block), "row": row, "error": str(error)})
    return {"keyword": keyword, "match": match or {}, "count": len(results), "results": results}


def _target(deck: KeywordDeck, edit: dict) -> tuple[object, int | None]:
    hits = deck.find(edit["keyword"], **edit.get("match", {}))
    if len(hits) != 1:
        raise FieldError(f"{edit['keyword']} {edit.get('match', {})} matches {len(hits)} targets; need exactly 1")
    return hits[0]


def _file(deck: KeywordDeck, name: str | None) -> object:
    if name is None:
        return deck.main
    wanted = Path(name)
    for source in deck.files.values():
        if identity(source.path) == identity(wanted if wanted.is_absolute() else deck.main_dir / wanted):
            return source
    raise FieldError(f"{name!r} is not a file of this deck")


def _apply(deck: KeywordDeck, edit: dict) -> list[Change]:
    op = edit.get("op")
    if op == "set":
        block, row = _target(deck, edit)
        return [deck.set(block, edit["field"], edit["value"], card=edit.get("card"), row=row)]
    if op == "set_parameter":
        return [deck.set_parameter(edit["name"], edit["value"], edit.get("file"))]
    if op == "set_members":
        block, _ = _target(deck, edit)
        return [deck.set_members(block, [int(i) for i in edit["members"]])]
    if op == "set_points":
        block, _ = _target(deck, edit)
        return [deck.set_points(block, [(float(a), float(o)) for a, o in edit["points"]])]
    if op == "insert":
        anchor_before = _target(deck, edit["before"])[0] if edit.get("before") else None
        anchor_after = _target(deck, edit["after"])[0] if edit.get("after") else None
        before = len(deck.changes)
        deck.insert(edit["text"], file=_file(deck, edit.get("file")), before=anchor_before, after=anchor_after)
        return deck.changes[before:]
    if op == "delete":
        block, _ = _target(deck, edit)
        return [deck.delete(block, force=bool(edit.get("force", False)))]
    raise FieldError(f"Unknown edit op {op!r}")


def edit_deck(path: str, edits: list[dict], *, output_dir: str | None = None, in_place: bool = False,
              allow_new_dangling: bool = False, include_paths: tuple[str, ...] = (),
              check_mesh: bool = False) -> dict:
    """Apply ``edits`` atomically; save to ``output_dir`` or in place, or only report (dry run).

    The batch fails (nothing written) when any edit fails or, unless ``allow_new_dangling``,
    when the edits create references to IDs that no longer exist.
    """
    if output_dir and in_place:
        raise ValueError("Choose output_dir or in_place, not both")
    deck = KeywordDeck.load(path, include_paths)
    dangling_before = {(d["kind"], d["id"]) for d in deck.references(check_mesh).dangling()}
    applied = []
    for number, edit in enumerate(edits):
        try:
            changes = _apply(deck, edit)
        except (FieldError, Unsupported, KeyError, IndexError, ValueError) as error:
            return {"status": "failed", "failed_edit": number, "error": f"{type(error).__name__}: {error}",
                    "applied_before_failure": len(applied), "written": False}
        applied.extend({"edit": number, "file": str(c.path), "line": c.line, "keyword": c.keyword,
                        "description": c.description, "exact": c.exact} for c in changes)
    after = deck.references(check_mesh)
    new_dangling = [d for d in after.dangling() if (d["kind"], d["id"]) not in dangling_before]
    diff = deck.diff()
    result = {"status": "succeeded", "changes": applied, "diff": diff[:MAX_DIFF],
              "diff_truncated": len(diff) > MAX_DIFF, "new_dangling": new_dangling[:200],
              "modified_files": [str(f.path) for f in deck.modified_files()], "warnings": deck.warnings,
              "written": False}
    if new_dangling and not allow_new_dangling:
        result.update(status="failed", error="Edits create dangling references; nothing written")
        return result
    if output_dir:
        result["save"] = deck.save_as(output_dir)
        result["written"] = True
    elif in_place:
        result["save"] = deck.save_in_place()
        result["written"] = True
    return result
