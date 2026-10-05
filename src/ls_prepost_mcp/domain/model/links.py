"""Reference fields of every keyword from PyDYNA link metadata (``_link_fields``).

PyDYNA marks the fields of 1,865 keyword classes that hold the ID of another keyword
(2,229 of them point to nodes). Together with the hand rules in :mod:`references`
(contact surface type codes, set members, ``*MAT_ADD_``) they decide which fields are
checked for dangling IDs and rewritten when IDs are renumbered.
"""
from __future__ import annotations

from functools import lru_cache

from .layouts import Unsupported
from .schema import _pydyna_class

# PyDYNA LinkType name -> reference kind used by :mod:`references`.
LINK_KINDS = {
    "NODE": "node", "ELEMENT_BEAM": "beam", "ELEMENT_SHELL": "shell", "ELEMENT_SOLID": "solid", "PART": "part",
    "MAT": "material", "SECTION": "section", "HOURGLASS": "hourglass", "DEFINE_CURVE": "curve",
    "DEFINE_CURVE_OR_TABLE": "curve", "DEFINE_BOX": "box", "DEFINE_COORDINATE_SYSTEM": "coordinate",
    "DEFINE_VECTOR": "vector", "DEFINE_TRANSFORMATION": "transformation", "SET_BEAM": "beam_set",
    "SET_DISCRETE": "discrete_set", "SET_NODE": "node_set", "SET_PART": "part_set", "SET_SEGMENT": "segment_set",
    "SET_SOLID": "solid_set", "SET_SHELL": "shell_set",
}


@lru_cache(maxsize=None)
def link_fields(name: str) -> tuple[tuple[str, str], ...]:
    """``(field, kind)`` pairs that PyDYNA marks as links for keyword ``name`` (empty if unknown)."""
    try:
        cls, _ = _pydyna_class(name)
    except Unsupported:
        return ()
    fields = getattr(cls, "_link_fields", None) or {}
    return tuple((field, LINK_KINDS[link.name]) for field, link in fields.items() if link.name in LINK_KINDS)


__all__ = ["LINK_KINDS", "link_fields"]
