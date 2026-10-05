"""Control and output cards from recipes (tasks.yaml P10).

A recipe names its keyword, the parameters that must be given and the ones that may be given.
Missing required parameters are refused; nothing physical is filled in by default (unset fields
keep the LS-DYNA defaults). An existing single block of the keyword is updated, a missing one is
inserted, several existing blocks are refused.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .cards import insert_card
from .fields import FieldError

if TYPE_CHECKING:
    from .deck import KeywordDeck

# recipe -> (keyword, required parameters, optional parameters)
RECIPES = {
    "termination": ("*CONTROL_TERMINATION", ("endtim",), ("endcyc", "dtmin", "endeng", "endmas")),
    "timestep": ("*CONTROL_TIMESTEP", ("tssfac",), ("dtinit", "isdo", "tslimt", "dt2ms", "lctm", "erode", "ms1st")),
    "hourglass": ("*CONTROL_HOURGLASS", ("ihq", "qh"), ()),
    "energy": ("*CONTROL_ENERGY", ("hgen",), ("rwen", "slnten", "rylen")),
    "d3plot": ("*DATABASE_BINARY_D3PLOT", ("dt",), ("lcdt", "npltc", "psetid")),
}
ASCII = ("glstat", "matsum", "rcforc", "nodout", "elout", "secforc", "spcforc", "rwforc", "sleout", "bndout",
         "deforc", "jntforc", "nodfor", "abstat", "ncforc")


def _upsert(deck: KeywordDeck, keyword: str, fields: dict) -> dict:
    existing = [block for block in deck.iter_blocks() if block.name == keyword]
    if len(existing) > 1:
        raise FieldError(f"{len(existing)} {keyword} blocks exist; edit the intended one explicitly")
    if existing:
        block = existing[0]
        for name, value in fields.items():
            deck.set(block, name, value)
        action = "updated"
    else:
        block = insert_card(deck, keyword, fields)[0]
        action = "inserted"
    return {"keyword": keyword, "action": action, "file": str(block.file.path), "line": block.line_number,
            "fields": fields}


def apply_recipe(deck: KeywordDeck, recipe: str, params: dict) -> list[dict]:
    """Apply one recipe; ``ascii`` takes ``names`` (glstat, matsum, ...) and ``dt`` (``binary`` optional)."""
    params = {k.lower(): v for k, v in params.items()}
    if recipe == "ascii":
        names = [str(n).lower() for n in params.get("names", [])]
        unknown = sorted(set(names) - set(ASCII))
        if not names or unknown or "dt" not in params:
            raise FieldError(f"ascii needs names from {list(ASCII)} and dt; unknown: {unknown}")
        extra = {"binary": int(params["binary"])} if "binary" in params else {}
        return [_upsert(deck, f"*DATABASE_{name.upper()}", {"dt": float(params["dt"]), **extra}) for name in names]
    if recipe not in RECIPES:
        raise FieldError(f"Unknown recipe {recipe!r}; use one of {sorted(RECIPES) + ['ascii']}")
    keyword, required, optional = RECIPES[recipe]
    missing = [name for name in required if params.get(name) is None]
    if missing:
        raise FieldError(f"{recipe} needs {missing}; no default physical values are filled in")
    unknown = sorted(set(params) - set(required) - set(optional))
    if unknown:
        raise FieldError(f"{recipe} does not take {unknown}")
    return [_upsert(deck, keyword, {name: value for name, value in params.items() if value is not None})]


__all__ = ["ASCII", "RECIPES", "apply_recipe"]
