"""Keyword and field documentation for search (tasks.yaml I05/A10, keyword-field category).

Adds what a text index of PyDYNA field declarations lacks: the description PyDYNA ships for
each field (MIT), the card and columns the field occupies (option cards named), what a field
refers to (the engine's reference and type-code rules), where the keyword sits in the user's
local LS-DYNA manual and that field's description there, and whether engine-written cards of
the keyword ran on LS-DYNA here. The manual is copyrighted: its page index and text stay in a
local folder named by ``LSPP_MANUAL_INDEX`` (built by the user's own tooling), never in the
repository. Every record names its source, version and evidence level.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from importlib import metadata
from pathlib import Path

from . import links, lists, references
from .blocks import make_blocks
from .cards import card_text
from .layouts import Unsupported
from .schema import SYNTHETIC_OPTIONS, _pydyna_class
from .schema import layout as block_layout

ENV = "LSPP_MANUAL_INDEX"
# R14 relabelled contact slave/master fields as SURFA/SURFB, documentation only (columns unchanged;
# R14.0.0 release notes 3.1). PyDYNA uses both spellings, so lookups try the other one.
CONTACT_RENAMES = {"ssid": "surfa", "msid": "surfb", "sstyp": "surfatyp", "mstyp": "surfbtyp", "sboxid": "saboxid",
                   "mboxid": "sbboxid", "spr": "sapr", "mpr": "sbpr", "sfs": "sfsa", "sfm": "sfsb", "sst": "sast",
                   "mst": "sbst", "sfst": "sfsat", "sfmt": "sfsbt"}
_RENAMED = {**CONTACT_RENAMES, **{new: old for old, new in CONTACT_RENAMES.items()}}
_RECIPE = "engine-written card, LS-DYNA R11 normal termination (2026-10-05)"
_SWAP = "recipe card replaced the original contact of a public deck; R11 glstat identical (2026-10-05)"
# Keywords whose engine-written cards LS-DYNA R11 ran here (evidence level "verified").
VERIFIED_R11 = {
    **{k: _RECIPE for k in (
        "*BOUNDARY_NON_REFLECTING", "*BOUNDARY_PRESCRIBED_MOTION_SET", "*BOUNDARY_SPC_SET", "*CONSTRAINED_NODAL_RIGID_BODY",
        "*CONTROL_ENERGY", "*CONTROL_HOURGLASS", "*CONTROL_TERMINATION", "*CONTROL_TIMESTEP", "*DATABASE_BINARY_D3PLOT",
        "*DATABASE_GLSTAT", "*DATABASE_MATSUM", "*DATABASE_RCFORC", "*DEFINE_CURVE", "*EOS_GRUNEISEN",
        "*INITIAL_VELOCITY_GENERATION", "*LOAD_BODY_Z", "*LOAD_NODE_SET", "*LOAD_SEGMENT_SET", "*MAT_ELASTIC",
        "*MAT_JOHNSON_COOK", "*MAT_PIECEWISE_LINEAR_PLASTICITY", "*MAT_PLASTIC_KINEMATIC", "*MAT_RIGID",
        "*MAT_SIMPLIFIED_JOHNSON_COOK", "*PART", "*RIGIDWALL_PLANAR", "*SECTION_SOLID", "*SET_NODE_LIST",
        "*SET_SEGMENT")},
    **{k: _SWAP for k in ("*CONTACT_AUTOMATIC_SINGLE_SURFACE", "*CONTACT_ERODING_SURFACE_TO_SURFACE",
                          "*CONTACT_AUTOMATIC_NODES_TO_SURFACE", "*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE")},
    "*CONTACT_TIED_SURFACE_TO_SURFACE_OFFSET": "recipe card read and processed by R11 (normal termination); "
                                               "tying behaviour not checked",
    "*CONSTRAINED_JOINT": "card order ID, 1, PARM, LOCAL, FAILURE x2 confirmed on R11: TFAIL took effect (2026-10-05)",
}
_BARE = re.compile(r"^[A-Z][A-Z0-9_/\-]{0,11}$")  # a variable name alone on a line
_SENTENCE = re.compile(r"^(?:[A-Z(][a-z]|(?:EQ|LT|GT|NE|LE|GE)\.)")
_TABLE = re.compile(r"^(?:Card\b|Type\b|Default\b|Variable\b|Remarks\b|Data Card)")  # card layout tables
_HEADER = re.compile(r"^(?:\*\S+|R\d+@\S+.*|\d+-\d+ \([A-Z_ -]+\).*|VARIABLE|DESCRIPTION)\s*$")
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "of", "a", "an", "is", "to", "for", "in", "and", "or", "on", "by", "if", "be", "this", "with", "as"}


def _pydyna_version() -> str:
    try:
        return "ansys-dyna-core " + metadata.version("ansys-dyna-core")
    except metadata.PackageNotFoundError:
        return "ansys-dyna-core (not installed)"


def _help(cls: type, name: str) -> str:
    doc = (getattr(getattr(cls, name, None), "__doc__", None) or "").strip()
    return re.sub(r"^Get or set the\s+", "", doc).strip()


def _name(raw: str) -> str:
    """PyDYNA schema name (``qb/vdc``) as its property name (``qb_vdc``)."""
    return re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")


def _generated_layout(cls: type, keyword: str) -> list[dict]:
    """Fields of a container card (CardSet) read by the engine layout from a generated card.

    An empty CardSet writes nothing, so one field gets a value to make PyDYNA write one item.
    """
    layout = None
    for name in links.field_names(keyword):
        try:
            layout = block_layout(make_blocks(card_text(keyword, {name: 1}), "\n")[0], {})
        except Exception:  # noqa: BLE001 - PyDYNA raises many types (read-only properties, bad values)
            layout = None
            continue
        if layout.fields:
            break
    if layout is None:
        return []
    return [{"name": i.name, "columns": f"{i.slot.offset + 1}-{i.slot.offset + i.slot.width}", "type": i.kind,
             "default": i.default, "help": _help(cls, i.name)} for i in layout.fields]


def _walk(cls: type, keyword: str, card: object, index: int, out: list[dict], option: object = None) -> None:
    kind = type(card).__name__
    if kind == "OptionCardSet":
        spec = getattr(card, "_option_spec", None)
        for inner in getattr(card, "_cards", []):
            _walk(cls, keyword, inner, index, out, spec)
        return
    entry = {"card": index, "option": getattr(option, "name", None), "position": getattr(option, "position", None),
             "kind": kind}
    schema = getattr(card, "_schema", None)
    if schema is not None and getattr(schema, "fields", None):
        out.append({**entry, "fields": _field_rows(cls, list(schema.fields))})
    elif getattr(card, "_cards", None):
        for inner in card._cards:
            _walk(cls, keyword, inner, index, out, option)
    elif kind == "CardSet":
        out.append({**entry, "kind": "CardSet (engine layout of a generated card)",
                    "fields": _generated_layout(cls, keyword)})
    else:
        out.append({**entry, "fields": []})  # a series of values (set members, curve points)


def _cards(cls: type, keyword: str) -> list[dict]:
    """Base cards, option cards and the engine's synthesised option cards (PyDYNA lacks them)."""
    result = []
    for (prefix, option), (position, cards) in SYNTHETIC_OPTIONS.items():
        if keyword.startswith(prefix):
            for number, fields in enumerate(cards):
                result.append({"card": f"engine:{option}" + (str(number + 1) if number else ""), "option": option,
                               "position": position, "kind": "engine-synthesised (R11 Vol I 10-54..10-58)",
                               "fields": [{"name": name, "columns": f"{offset + 1}-{offset + width}", "type": kind,
                                           "default": None, "help": ""} for name, kind, offset, width in fields]})
    for index, card in enumerate(cls()._cards):
        _walk(cls, keyword, card, index, result)
    return result


def _field_rows(cls: type, fields: list[object]) -> list[dict]:
    return [{"name": _name(f.name), "columns": f"{f.offset + 1}-{f.offset + f.width}", "type": f.type.__name__,
             "default": f.default, "help": _help(cls, _name(f.name))} for f in fields
            if not f.name.lower().startswith("unused")]


def _references(keyword: str, base: str) -> list[dict]:
    rows = [{"field": field, "refers_to": kind} for field, kind in references._references(keyword, base, True)]
    rows += [{"field": field, "refers_to": "by " + code + ": " + ", ".join(f"{k}={v}" for k, v in table.items())}
             for field, code, table in references.coded_rules(base)]
    return rows


def _verified(keyword: str) -> str | None:
    if keyword in VERIFIED_R11:
        return VERIFIED_R11[keyword]
    return next((note for name, note in VERIFIED_R11.items() if keyword.startswith(name + "_")), None)


# ------------------------------------------------------------------------- local manual
@lru_cache(maxsize=4)
def _manual(directory: str) -> dict | None:
    path = Path(directory) / "r17_pages.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@lru_cache(maxsize=6)
def _pages(directory: str, volume: str) -> dict[int, str]:
    text = (Path(directory) / f"r17_vol{volume}.txt").read_text(encoding="utf-8", errors="replace")
    text = unicodedata.normalize("NFKC", text)  # PDF ligatures such as U+FB00 become plain letters
    parts = re.split(r"^=== \[pdf page (\d+)\] ===$", text, flags=re.M)
    return {int(number): body for number, body in zip(parts[1::2], parts[2::2])}


def _manual_dir(directory: str | None) -> str | None:
    directory = directory or os.environ.get(ENV)
    return directory if directory and _manual(directory) else None


def manual_section(keyword: str, directory: str | None = None) -> dict | None:
    """Volume, PDF pages and printed pages of the manual section that documents ``keyword``."""
    directory = _manual_dir(directory)
    if directory is None:
        return None
    index = _manual(directory)
    sections = index["sections"]
    best = max((name for name in sections if keyword == name or keyword.startswith(name + "_")), key=len, default=None)
    if best is None:
        return None
    entry = sections[best]
    return {"manual": index.get("manual"), "section": best, "volume": entry["volume"],
            "pdf_pages": [entry["pdf_pages"][0], entry["pdf_pages"][-1]],
            "printed_pages": [entry["printed"][0], entry["printed"][-1]] if entry["printed"] else None}


def manual_field_text(keyword: str, field: str, directory: str | None = None, limit: int = 600) -> str | None:
    """The field's description paragraph in the local manual (first match in the section)."""
    section = manual_section(keyword, directory)
    if section is None:
        return None
    pages = _pages(_manual_dir(directory), section["volume"])
    first, last = section["pdf_pages"]
    lines = [line.strip() for n in range(first, last + 1) for line in pages.get(n, "").splitlines()]
    lines = [line for line in lines if line and not _HEADER.match(line)]
    names = {name.upper().replace("_", "/") for name in [field] + ([_RENAMED[field]] if field in _RENAMED else [])}
    names |= {name.replace("/", "_") for name in names}
    names |= {name[:-1] + "0" for name in names if name.endswith("O")}  # PyDYNA EPSO = manual EPS0
    stem = re.match(r"^([A-Z]+)(\d+)$", field.upper())
    for i, line in enumerate(lines[:-1]):
        span = re.match(r"^([A-Z]+)(\d+)\s*-\s*(?:[A-Z]+)?(\d+)$", line)  # "D1-D5" describes D4
        if stem and span and span[1] == stem[1] and int(span[2]) <= int(stem[2]) <= int(span[3]):
            line = field.upper()
        # the description table puts the variable alone on a line and a sentence after it;
        # card summaries list variables one per line, so the next line decides
        following = lines[i + 1]
        if line not in names or _BARE.match(following) or _TABLE.match(following) or not _SENTENCE.match(following):
            continue
        out: list[str] = []
        for text in lines[i + 1:]:
            if _BARE.match(text) or sum(map(len, out)) > limit:
                break
            out.append(text)
        return re.sub(r"\s+", " ", " ".join(out)).strip()[:limit]
    return None


# ------------------------------------------------------------------------- public API
def keyword_doc(keyword: str, manual_dir: str | None = None) -> dict:
    """Cards, fields, references, manual location and evidence of one keyword."""
    keyword = keyword.strip().upper()
    try:
        cls, base = _pydyna_class(keyword)
    except Unsupported as error:
        raise KeyError(f"{keyword}: {error}") from error
    verified = _verified(keyword)
    return {"keyword": keyword, "pydyna_class": cls.__name__, "pydyna_base": base,
            "options": [spec.name for spec in getattr(cls(), "option_specs", [])],
            "cards": _cards(cls, keyword), "references": _references(keyword, lists.base_name(keyword)[0]),
            "manual": manual_section(keyword, manual_dir), "engine_verified": verified,
            "evidence": "verified" if verified else "documented",
            "source": {"fields": _pydyna_version(), "manual": "local index (" + ENV + ")" if _manual_dir(manual_dir)
                       else "not configured"}}


def field_doc(keyword: str, field: str, manual_dir: str | None = None) -> dict:
    """One field: card, columns, type, default, PyDYNA help, references, manual text, evidence."""
    doc = keyword_doc(keyword, manual_dir)
    wanted = field.strip().lower()
    for name in (wanted, _RENAMED.get(wanted)):
        for card in doc["cards"]:
            row = next((f for f in card["fields"] if f["name"] == name), None)
            if row:
                refs = [r["refers_to"] for r in doc["references"] if r["field"] == name]
                return {"keyword": doc["keyword"], "field": name, "asked": wanted, "card": card["card"],
                        "option": card["option"], **{k: row[k] for k in ("columns", "type", "default", "help")},
                        "refers_to": refs[0] if refs else None,
                        "manual": doc["manual"], "manual_text": manual_field_text(doc["keyword"], name, manual_dir),
                        "evidence": doc["evidence"], "engine_verified": doc["engine_verified"], "source": doc["source"]}
    raise KeyError(f"{doc['keyword']} has no field {field!r}")


@lru_cache(maxsize=1)
def _catalog() -> tuple[tuple[str, str, str], ...]:
    """(keyword, field, help) for every PyDYNA keyword class (imports all classes once)."""
    from ansys.dyna.core.keywords.keyword_classes.type_mapping import TypeMapping

    rows = []
    for keyword in sorted(TypeMapping):
        try:
            cls, _ = _pydyna_class(keyword)
        except Unsupported:
            continue
        rows.append((keyword, "", ""))
        names = list(links.field_names(keyword))
        if any(type(card).__name__ in ("TableCardGroup", "CardSet") for card in cls()._cards):
            # table groups (*PART) and card sets expose their fields only through the cards
            names += [f["name"] for card in _cards(cls, keyword) for f in card["fields"] if f["name"] not in names]
        rows.extend((keyword, name, _help(cls, name)) for name in names)
    return tuple(rows)


def search(query: str, limit: int = 10) -> list[dict]:
    """Rank keyword/field records for a free-text query (keyword names, field names, help words)."""
    keyword_terms = [t.upper() for t in re.findall(r"\*[A-Za-z0-9_\-]+", query)]
    rest = re.sub(r"\*[A-Za-z0-9_\-]+", " ", query)
    field_terms = {t.lower() for t in re.findall(r"\b[A-Z][A-Z0-9_]{1,9}\b", rest)}
    field_terms |= {_RENAMED[t] for t in field_terms if t in _RENAMED}
    words = {w for w in _WORD.findall(rest.lower()) if w not in _STOP and len(w) > 2}
    scored = []
    for keyword, field, help_text in _catalog():
        score = 0.0
        for term in keyword_terms:
            if keyword == term:
                score += 12
            elif keyword.startswith(term + "_") or keyword.startswith(term):
                score += 8 - min(len(keyword) - len(term), 60) / 20
        if field and field in field_terms:
            score += 10
        if field and words:
            score += len(words & set(_WORD.findall(help_text.lower()))) * 1.5
        if not field and (field_terms or words) and keyword_terms:
            score -= 1  # prefer the field record when a field was asked for
        if score > 0:
            scored.append((score, keyword, field, help_text))
    scored.sort(key=lambda row: (-row[0], len(row[1]), row[2]))
    return [{"keyword": k, "field": f or None, "help": h, "score": round(s, 2),
             "evidence": "verified" if _verified(k) else "documented", "source": _pydyna_version()}
            for s, k, f, h in scored[:limit]]


__all__ = ["CONTACT_RENAMES", "ENV", "VERIFIED_R11", "field_doc", "keyword_doc", "manual_field_text",
           "manual_section", "search"]
