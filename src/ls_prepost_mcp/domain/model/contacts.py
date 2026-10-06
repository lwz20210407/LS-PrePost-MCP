"""Contact definitions from recipes (tasks.yaml P06); the initial-penetration check is :mod:`contact`.

Each side is given as ``{"part": pid}``, ``{"part_set": sid}``, ``{"parts": [...]}`` (a part set
is created), ``{"segment_set": sid}``, ``{"exterior": {...}}`` (a segment set of the outward solid
faces is created), ``{"shell_set": sid}``, ``{"node_set": sid}`` or ``{"nodes"|"select": ...}`` (a
node set is created); a single-surface contact also takes ``"all"``. The surface type codes are
written from the side (R11 Vol I *CONTACT card 1: 0 segment set, 1 shell set, 2 part set, 3 part,
4 node set, 5 all). Friction FS must be given for sliding contacts (0 is a valid choice); every
other field keeps the LS-DYNA default unless given.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import geometry, links, sets
from .cards import insert_card
from .fields import FieldError
from .schema import _pydyna_class

if TYPE_CHECKING:
    from .blocks import SourceFile
    from .deck import KeywordDeck

RECIPES = {
    "automatic_surface_to_surface": "*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE",
    "automatic_single_surface": "*CONTACT_AUTOMATIC_SINGLE_SURFACE",
    "eroding_surface_to_surface": "*CONTACT_ERODING_SURFACE_TO_SURFACE",
    "tied_surface_to_surface_offset": "*CONTACT_TIED_SURFACE_TO_SURFACE_OFFSET",
    "automatic_nodes_to_surface": "*CONTACT_AUTOMATIC_NODES_TO_SURFACE",
}
SIDE_TYPES = {"segment_set": 0, "shell_set": 1, "part_set": 2, "part": 3, "node_set": 4}
_SURFACES = {"segment_set", "shell_set", "part_set", "part"}
# recipe -> (allowed side A kinds, allowed side B kinds; None: no side B)
SIDES = {
    "automatic_surface_to_surface": (_SURFACES, _SURFACES),
    "eroding_surface_to_surface": (_SURFACES, _SURFACES),
    "tied_surface_to_surface_offset": (_SURFACES, _SURFACES),
    "automatic_nodes_to_surface": ({"node_set", "part_set", "part"}, _SURFACES),
    "automatic_single_surface": (_SURFACES - {"segment_set"} | {"all"}, None),
}
NO_FRICTION = {"tied_surface_to_surface_offset"}


def _fields_of_default_cards(keyword: str) -> set[str]:
    """Fields of the cards PyDYNA writes without options (cards 1-3 and type-specific cards)."""
    cls, _ = _pydyna_class(keyword)
    return {field.name.lower() for card in cls()._cards if getattr(card, "active", True)
            and hasattr(card, "_schema") for field in card._schema.fields}


_SELECTIONS = {"parts": "part_set", "exterior": "segment_set", "nodes": "node_set", "select": "node_set"}


def _code(spec: object) -> int | None:
    """Type code a side spec will get, without creating anything."""
    if spec == "all":
        return 5
    if isinstance(spec, dict) and len(spec) == 1:
        key = next(iter(spec))
        return SIDE_TYPES.get(_SELECTIONS.get(key, key))
    return None


def _side(deck: KeywordDeck, spec: object, allowed: set[str], label: str, created: list[dict]) -> tuple[int, int]:
    """``(id, type code)`` of one side; creates the set a selection needs."""
    if spec == "all":
        if "all" not in allowed:
            raise FieldError(f"Side {label} cannot be 'all'")
        return 0, 5
    if not isinstance(spec, dict) or len(spec) != 1:
        raise FieldError(f"Side {label} needs exactly one of part, part_set, parts, segment_set, exterior, "
                         "shell_set, node_set, nodes, select")
    (key, value), = spec.items()
    kind = _SELECTIONS.get(key, key)
    if kind not in SIDE_TYPES or kind not in allowed:
        raise FieldError(f"Side {label} cannot be a {kind}; allowed: {sorted(allowed)}")
    defined = deck.references(False).defined
    if key in SIDE_TYPES:
        ident = int(value)
        if ident not in defined.get(kind, set()):
            raise FieldError(f"Side {label}: {kind} {ident} is not defined")
        return ident, SIDE_TYPES[kind]
    if key == "parts":
        missing = sorted(set(map(int, value)) - defined.get("part", set()))
        if missing:
            raise FieldError(f"Side {label}: parts {missing} are not defined")
        ident = sets.create_set(deck, "part", [int(v) for v in value])[0]
    elif key == "exterior":
        ident = sets.create_set(deck, "segment", geometry.exterior_segments(deck, **value).tolist())[0]
    else:
        ids = value if key == "nodes" else geometry.select_nodes(deck, **value).tolist()
        ident = sets.create_set(deck, "node", ids)[0]
    created.append({"side": label, "kind": kind, "id": ident})
    return ident, SIDE_TYPES[kind]


def add_contact(deck: KeywordDeck, recipe: str, a: object, b: object = None, *, params: dict | None = None,
                cid: int | None = None, title: str | None = None, file: SourceFile | None = None) -> dict:
    """Insert one contact from :data:`RECIPES`; ``params`` are further fields of the default cards."""
    if recipe not in RECIPES:
        raise FieldError(f"Unknown contact recipe {recipe!r}; use one of {sorted(RECIPES)}")
    keyword = RECIPES[recipe]
    allowed_a, allowed_b = SIDES[recipe]
    if (b is None) != (allowed_b is None):
        raise FieldError(f"{keyword} needs {'no' if allowed_b is None else 'a'} side B")
    names = links.field_names(keyword)
    side_a, type_a, side_b, type_b = (("surfa", "surfatyp", "surfb", "surfbtyp") if "surfa" in names
                                      else ("ssid", "sstyp", "msid", "mstyp"))
    values = {str(k).lower(): v for k, v in (params or {}).items() if v is not None}
    unknown = sorted(set(values) - (_fields_of_default_cards(keyword) - {side_a, type_a, side_b, type_b}))
    if unknown:
        raise FieldError(f"{keyword}: fields {unknown} are not on its default cards (or are set from the sides)")
    if recipe not in NO_FRICTION and "fs" not in values:
        raise FieldError(f"{keyword}: give the static friction coefficient fs (0 is a valid choice)")
    # R17 Vol I 11-25: SABOXID/SBBOXID only with a part, part set or "all" side, never for ERODING
    # (checked before any set is created, so a refusal leaves the deck unchanged)
    for box, spec in (("saboxid", a), ("sbboxid", b)):
        if values.get(box) and (recipe == "eroding_surface_to_surface" or _code(spec) not in (2, 3, 5, 6)):
            raise FieldError(f"{box.upper()} needs that side as a part, part set or all, and is not "
                             "available for ERODING contacts")
    created: list[dict] = []
    fields = dict(values)
    fields[side_a], fields[type_a] = _side(deck, a, allowed_a, "A", created)
    if allowed_b is not None:
        fields[side_b], fields[type_b] = _side(deck, b, allowed_b, "B", created)
    if cid is not None or title:
        if cid is None:
            raise FieldError("A contact title needs a contact ID (cid)")
        keyword, fields = keyword + "_ID", {"cid": int(cid), "heading": title or "", **fields}
    block = insert_card(deck, keyword, fields, file=file)[0]
    return {"keyword": keyword, "file": str(block.file.path), "line": block.line_number, "created_sets": created,
            "sides": {"a": [fields[side_a], fields[type_a]],
                      "b": [fields[side_b], fields[type_b]] if allowed_b is not None else None}}


__all__ = ["RECIPES", "SIDES", "SIDE_TYPES", "add_contact"]
