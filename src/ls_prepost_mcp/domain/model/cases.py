"""Parameter-study case generation at keyword level (tasks.yaml A09, deck part).

Each case is a complete copy of the base deck (include layout kept, untouched files
copied verbatim) with its own parameter values and edits, followed by a semantic
comparison against the base so that every case is shown to differ only where intended.
A failing case is reported and does not stop the others.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .compare import compare_decks
from .operations import edit_deck

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _case_name(case: dict, number: int) -> str:
    name = _SAFE.sub("_", str(case.get("name") or f"case_{number:03d}")).strip("._")
    if not name:
        raise ValueError(f"Case {number} has an empty name")
    return name


def _changes(comparison: dict) -> dict:
    """Short view of what differs from the base."""
    entities = {kind: {k: v for k, v in entry.items() if k in ("added_count", "removed_count", "changed_count")}
                for kind, entry in comparison["entities"].items()
                if entry["added_count"] or entry["removed_count"] or entry["changed_count"]}
    return {"parameters": comparison["parameters"], "entities": entities,
            "keywords": {name: len(entry["changed"]) for name, entry in comparison["keywords"].items()}}


def generate_cases(path: str, cases: list[dict], out_dir: str, *, include_paths: tuple[str, ...] = (),
                   allow_new_dangling: bool = False, compare_mesh: bool = False) -> dict:
    """Write one deck per case into ``out_dir/<name>/``.

    ``cases``: ``[{"name": "v600", "parameters": {"vel": 600.0}, "edits": [...]}, ...]`` where
    ``edits`` uses the :func:`edit_deck` operations. ``out_dir`` must not exist or be empty.
    """
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} is not empty")
    names = [_case_name(case, number) for number, case in enumerate(cases, 1)]
    if len(set(names)) != len(names):
        raise ValueError("Case names must be unique")
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for name, case in zip(names, cases):
        edits = [{"op": "set_parameter", "name": key, "value": value}
                 for key, value in (case.get("parameters") or {}).items()]
        edits += list(case.get("edits") or [])
        outcome = edit_deck(path, edits, output_dir=str(out / name), include_paths=include_paths,
                            allow_new_dangling=allow_new_dangling)
        entry = {"name": name, "status": outcome["status"], "parameters": case.get("parameters") or {},
                 "edits": len(edits)}
        if outcome["status"] != "succeeded":
            entry["error"] = outcome.get("error")
            entry["failed_edit"] = outcome.get("failed_edit")
        else:
            entry["main"] = outcome["save"]["main"]
            entry["difference_from_base"] = _changes(compare_decks(path, entry["main"], include_mesh=compare_mesh))
        results.append(entry)
    manifest = {"base": str(path), "cases": results,
                "succeeded": sum(r["status"] == "succeeded" for r in results),
                "failed": sum(r["status"] != "succeeded" for r in results)}
    (out / "cases.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return {**manifest, "manifest": str(out / "cases.json")}
