"""Materials, equations of state, sections, hourglass controls and parts from recipes (tasks.yaml P03).

Field names are the keyword variables (PyDYNA's names, which follow the LS-DYNA manual). Every
physical value comes from the caller in the unit system the caller declares: required values
that are missing are refused, nothing is converted and no value is invented (unset optional
fields keep the LS-DYNA defaults). New IDs are the next free ID unless one is given. Parts may
only refer to sections, materials, EOS and hourglass definitions that exist.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .cards import insert_card
from .fields import FieldError, single_line

if TYPE_CHECKING:
    from .blocks import SourceFile
    from .deck import KeywordDeck

_EPS = tuple(f"eps{i}" for i in range(1, 9)) + tuple(f"es{i}" for i in range(1, 9))
# recipe -> (keyword, required, optional)
MATERIALS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "elastic": ("*MAT_ELASTIC", ("ro", "e", "pr"), ("da", "db")),  # MAT_001
    "plastic_kinematic": ("*MAT_PLASTIC_KINEMATIC", ("ro", "e", "pr", "sigy"),  # MAT_003
                          ("etan", "beta", "src", "srp", "fs", "vp")),
    "johnson_cook": ("*MAT_JOHNSON_COOK", ("ro", "g", "a", "b", "n", "c", "m", "tm", "tr", "epso", "cp"),  # MAT_015
                     ("e", "pr", "dtf", "vp", "rateop", "pc", "spall", "it", "d1", "d2", "d3", "d4", "d5",
                      "c2_p_xnp_d", "erod", "efmin", "numint", "k", "eps1")),
    "rigid": ("*MAT_RIGID", ("ro", "e", "pr"),  # MAT_020
              ("n", "couple", "m", "alias", "cmo", "con1", "con2", "lco_or_a1", "a2", "a3", "v1", "v2", "v3")),
    "piecewise_linear_plasticity": ("*MAT_PIECEWISE_LINEAR_PLASTICITY", ("ro", "e", "pr"),  # MAT_024
                                    ("sigy", "etan", "fail", "tdel", "c", "p", "lcss", "lcsr", "vp") + _EPS),
    "simplified_johnson_cook": ("*MAT_SIMPLIFIED_JOHNSON_COOK", ("ro", "e", "pr", "a", "b", "n", "c"),  # MAT_098
                                ("vp", "epso", "psfail", "sigmax", "sigsat")),
}
EOS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "linear_polynomial": ("*EOS_LINEAR_POLYNOMIAL", (), ("c0", "c1", "c2", "c3", "c4", "c5", "c6", "e0", "v0")),
    "gruneisen": ("*EOS_GRUNEISEN", ("c", "s1", "gamao"), ("s2", "s3", "a", "e0", "v0", "lcid")),
}
SECTIONS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "shell": ("*SECTION_SHELL", ("elform", "t1"),
              ("shrf", "nip", "propt", "qr_irid", "icomp", "setyp", "t2", "t3", "t4", "nloc", "marea", "idof",
               "edgset")),
    "solid": ("*SECTION_SOLID", ("elform",), ("aet",)),
}
HOURGLASS = ("*HOURGLASS", ("ihq",), ("qm", "ibq", "q1", "q2", "qb_vdc", "qw"))
# ID field and reference kind of each family
_IDS = {"material": ("mid", "material"), "eos": ("eosid", "eos"), "section": ("secid", "section"),
        "hourglass": ("hgid", "hourglass")}
PART_REFS = {"secid": "section", "mid": "material", "eosid": "eos", "hgid": "hourglass", "tmid": "thermal_material"}


def _params(params: dict, required: tuple[str, ...], optional: tuple[str, ...], what: str) -> dict:
    values = {str(k).lower(): v for k, v in params.items() if v is not None}
    unknown = sorted(set(values) - set(required) - set(optional))
    if unknown:
        raise FieldError(f"{what}: unknown parameters {unknown}; allowed {sorted(required + optional)}")
    missing = [name for name in required if name not in values]
    if missing:
        raise FieldError(f"{what}: missing {missing}; physical values are never filled in by default")
    return values


def _new_id(deck: KeywordDeck, family: str, wanted: int | None) -> int:
    defined = deck.references(False).defined.get(_IDS[family][1], set())
    if wanted is None:
        return max(defined, default=0) + 1
    if int(wanted) in defined:
        raise FieldError(f"{family} {wanted} is already defined")
    return int(wanted)


def _require_defined(deck: KeywordDeck, kind: str, ident: int, field: str) -> None:
    if ident and int(ident) not in deck.references(False).defined.get(kind, set()):
        raise FieldError(f"{field}={ident}: {kind} {ident} is not defined")


def _insert(deck: KeywordDeck, family: str, keyword: str, values: dict, ident: int | None, title: str | None,
            file: SourceFile | None) -> dict:
    id_field = _IDS[family][0]
    ident = _new_id(deck, family, ident)
    fields = {id_field: ident, **values}
    if title:
        keyword, fields = keyword + "_TITLE", {"title": title, **fields}
    block = insert_card(deck, keyword, fields, file=file)[0]
    return {"keyword": keyword, id_field: ident, "file": str(block.file.path), "line": block.line_number}


def add_material(deck: KeywordDeck, recipe: str, params: dict, *, mid: int | None = None, title: str | None = None,
                 file: SourceFile | None = None) -> dict:
    """A material from :data:`MATERIALS` (MAT_001/003/015/020/024/098)."""
    if recipe not in MATERIALS:
        raise FieldError(f"Unknown material recipe {recipe!r}; use one of {sorted(MATERIALS)}")
    keyword, required, optional = MATERIALS[recipe]
    values = _params(params, required, optional, keyword)
    if recipe == "piecewise_linear_plasticity" and "sigy" not in values and "lcss" not in values:
        raise FieldError(f"{keyword}: give SIGY (with ETAN) or an LCSS curve")
    for name in ("lcss", "lcsr"):
        if values.get(name):
            _require_defined(deck, "curve", values[name], name)
    result = _insert(deck, "material", keyword, values, mid, title, file)
    if recipe == "johnson_cook":
        result["note"] = "solid parts with *MAT_JOHNSON_COOK also need an EOS (eosid on the part)"
    return result


def add_eos(deck: KeywordDeck, recipe: str, params: dict, *, eosid: int | None = None, title: str | None = None,
            file: SourceFile | None = None) -> dict:
    """An equation of state from :data:`EOS`."""
    if recipe not in EOS:
        raise FieldError(f"Unknown EOS recipe {recipe!r}; use one of {sorted(EOS)}")
    keyword, required, optional = EOS[recipe]
    values = _params(params, required, optional, keyword)
    if recipe == "linear_polynomial" and not any(values.get(f"c{i}") for i in range(7)):
        raise FieldError(f"{keyword}: give at least one non-zero coefficient C0..C6")
    if values.get("lcid"):
        _require_defined(deck, "curve", values["lcid"], "lcid")
    return _insert(deck, "eos", keyword, values, eosid, title, file)


def add_section(deck: KeywordDeck, recipe: str, params: dict, *, secid: int | None = None, title: str | None = None,
                file: SourceFile | None = None) -> dict:
    """A section from :data:`SECTIONS`; ``thickness`` sets T1-T4 of a shell section at once."""
    if recipe not in SECTIONS:
        raise FieldError(f"Unknown section recipe {recipe!r}; use one of {sorted(SECTIONS)}")
    keyword, required, optional = SECTIONS[recipe]
    params = {str(k).lower(): v for k, v in params.items()}
    if recipe == "shell" and "thickness" in params:
        thickness = params.pop("thickness")
        params.update({f"t{i}": thickness for i in range(1, 5)})
    values = _params(params, required, optional, keyword)
    if values.get("icomp"):
        raise FieldError(f"{keyword}: ICOMP=1 needs layer angle cards, which this recipe does not write")
    return _insert(deck, "section", keyword, values, secid, title, file)


def add_hourglass(deck: KeywordDeck, params: dict, *, hgid: int | None = None, title: str | None = None,
                  file: SourceFile | None = None) -> dict:
    """A part-level *HOURGLASS definition (IHQ required)."""
    keyword, required, optional = HOURGLASS
    return _insert(deck, "hourglass", keyword, _params(params, required, optional, keyword), hgid, title, file)


def _part_block(deck: KeywordDeck, pid: int) -> object:
    for block in deck.blocks("*PART"):
        if pid in deck.layout(block).rows:
            return block
    raise FieldError(f"Part {pid} is not defined in a *PART block")


def add_part(deck: KeywordDeck, *, title: str, secid: int, mid: int, eosid: int = 0, hgid: int = 0, tmid: int = 0,
             pid: int | None = None, file: SourceFile | None = None) -> dict:
    """A *PART that refers to existing definitions; every field is read back."""
    if not title or len(title) > 70:
        raise FieldError("A part needs a heading of at most 70 characters")
    fields = {"secid": int(secid), "mid": int(mid), "eosid": int(eosid), "hgid": int(hgid), "tmid": int(tmid)}
    for name, value in fields.items():
        if name in ("secid", "mid") and not value:
            raise FieldError(f"A part needs {name}")
        _require_defined(deck, PART_REFS[name], value, name)
    defined = deck.references(False).defined.get("part", set())
    pid = max(defined, default=0) + 1 if pid is None else int(pid)
    if pid in defined:
        raise FieldError(f"Part {pid} is already defined")
    card = [pid, fields["secid"], fields["mid"], fields["eosid"], fields["hgid"], 0, 0, fields["tmid"]]
    block = deck.insert(f"*PART\n{single_line(title, 'Part heading')}\n" + "".join(f"{v:>10}" for v in card) + "\n", file=file)[0]
    read = {name: deck.get(block, name, row=pid).value for name in fields}
    if any(int(read[name] or 0) != value for name, value in fields.items()):
        deck.delete(block, force=True)
        raise FieldError(f"Generated *PART {pid} failed verification: {read}")
    return {"keyword": "*PART", "pid": pid, "file": str(block.file.path), "line": block.line_number, **fields}


def set_part(deck: KeywordDeck, pid: int, **fields: int) -> dict:
    """Change SECID / MID / EOSID / HGID / TMID of an existing part (targets must exist)."""
    unknown = sorted(set(fields) - set(PART_REFS))
    if unknown or not fields:
        raise FieldError(f"set_part changes {sorted(PART_REFS)}; got {sorted(fields) or 'nothing'}")
    block = _part_block(deck, int(pid))
    for name, value in fields.items():
        if name in ("secid", "mid") and not value:
            raise FieldError(f"A part needs {name}")
        _require_defined(deck, PART_REFS[name], int(value), name)
    for name, value in fields.items():
        deck.set(block, name, int(value), row=int(pid))
    return {"keyword": "*PART", "pid": int(pid), "changed": {k: int(v) for k, v in fields.items()}}


KINDS = {"material": add_material, "eos": add_eos, "section": add_section, "hourglass": add_hourglass}

__all__ = ["EOS", "HOURGLASS", "KINDS", "MATERIALS", "PART_REFS", "SECTIONS", "add_eos", "add_hourglass",
           "add_material", "add_part", "add_section", "set_part"]
