"""Opt-in, bounded keyword geometry estimates; no native Contact Check evidence."""
from __future__ import annotations

import math
from numbers import Real
from typing import TYPE_CHECKING

from . import contact

if TYPE_CHECKING:
    from .deck import KeywordDeck


def options(value: dict | None, include_mesh: bool) -> dict | None:
    """Validate the request before loading a deck; callers can only lower hard limits."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("contact_geometry must be an options object or None")
    if not include_mesh:
        raise ValueError("contact_geometry requires include_mesh=True")
    unknown = value.keys() - (contact.HARD_LIMITS.keys() | {"tolerance"})
    if unknown:
        raise ValueError(f"Unknown contact_geometry options: {list(map(str, unknown))}")
    result = {**contact.HARD_LIMITS, "tolerance": 0.0, **value}
    tolerance = result["tolerance"]
    try:
        valid = (not isinstance(tolerance, bool) and isinstance(tolerance, Real)
                 and math.isfinite(tolerance) and tolerance >= 0)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("contact_geometry tolerance must be a finite nonnegative number in model coordinates")
    result["tolerance"] = float(tolerance)
    for name, hard_limit in contact.HARD_LIMITS.items():
        limit = result[name]
        minimum = 0 if name == "max_report" else 1
        if type(limit) is not int or not minimum <= limit <= hard_limit:
            raise ValueError(f"contact_geometry {name} must be an integer from {minimum} to {hard_limit}")
    return result


def estimate(deck: KeywordDeck, settings: dict) -> dict:
    """Reuse the loaded AST and existing nearest-triangle/pseudonormal kernel."""
    budget = contact.GeometryBudget(settings)
    results = contact.contact_checks(deck, settings["tolerance"], settings["max_report"], budget=budget)
    evaluated = [entry for entry in results if entry["checked"]]
    not_checked = [entry for entry in results if not entry["checked"]]
    candidates = []
    for index, entry in enumerate(results):
        site = {key: entry[key] for key in ("keyword", "file", "line") if key in entry}
        candidates.extend({"contact_index": index, **site, **row}
                          for row in entry.get("nodes", entry.get("partial_candidates", [])))
    total = len(deck.blocks("*CONTACT_*"))
    complete = not not_checked
    return {
        "method": "keyword_triangle_gap", "native_verified": False, "read_only": True,
        "units": "model_coordinates", "tolerance": settings["tolerance"],
        "coverage": {
            "complete": complete,
            "status": "not_applicable" if total == 0 else "passed" if complete else "missing",
            "total_contacts": total,
            "evaluated_contacts": len(evaluated),
            "not_checked_contacts": sum(entry.get("omitted_contacts", 1) for entry in not_checked),
            "candidate_nodes_reported": len(candidates),
            "candidate_nodes_found": sum(entry.get("penetrating", entry.get("partial_penetrating", 0))
                                         for entry in results),
            "budget_used": budget.used,
        },
        "limits": {key: settings[key] for key in contact.HARD_LIMITS},
        "evaluated": evaluated, "not_checked": not_checked, "candidates": candidates,
        "assumptions": [*contact.ASSUMPTIONS,
                        "reference-configuration geometry estimate, not a native LS-PrePost Contact Check",
                        "depth and tolerance use model coordinates; no unit system is inferred",
                        "only slave-to-master direction is estimated; single-surface/self contact is not evaluated",
                        "contact physics, solver activation and contact scale factors are not reproduced"],
    }
