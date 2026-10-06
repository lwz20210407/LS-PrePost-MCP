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

import numpy as np

from . import (
    contact,
    contacts,
    controls,
    coordinates,
    generate,
    geometry,
    joint_checks,
    joints,
    lists,
    loads,
    materials,
    mesh,
    persist,
    quality,
    renumber,
    selectors,
    sets,
    solver_rules,
)
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
    elements: dict[str, int] = {}  # element count per *ELEMENT_ keyword (tasks.yaml P01)
    for block in deck.iter_blocks():
        base = lists.base_name(block.name)[0]
        try:
            if base.startswith("*ELEMENT_"):
                rows = deck.layout(block).rows
                elements[block.name] = elements.get(block.name, 0) + sum(1 for _ in rows)
            elif base == "*PART":
                for pid in deck.layout(block).rows:
                    parts.append({**_site(block), "pid": pid,
                                  **_safe(deck, block, pid, ("heading", "secid", "mid", "eosid", "hgid"))})
            elif base.startswith("*SECTION_"):
                sections.append({**_site(block), **_safe(deck, block, None, ("secid", "title"))})
            elif base.startswith("*MAT_") and not base.startswith("*MAT_ADD_"):
                materials.append({**_site(block), **_safe(deck, block, None, ("mid", "tmid", "title"))})
            elif lists.is_list_set(block.name):
                ranged = lists.base_name(block.name)[0] in lists.RANGE_SETS
                sets.append({**_site(block), **_safe(deck, block, None, ("sid", "title")),
                             "members": None if ranged else len(deck.members(block)),
                             "member_form": "ranges" if ranged else "list"})
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
        "parts": parts, "sections": sections, "materials": materials, "sets": sets, "elements": elements,
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


def _create_set(deck: KeywordDeck, edit: dict) -> Change:
    """``{"op": "create_set", "kind": ..., "ids": [...] | "select": {...} | "selector": {...}, "sid"?, ...}``."""
    kind = edit["kind"]
    if "selector" in edit:
        if kind not in ("node", "shell", "solid", "part"):
            raise FieldError(f"A Selector cannot define a {kind} set; give ids or select")
        items = _selected(deck, edit["selector"], kind)
    elif "ids" in edit:
        items = list(edit["ids"])
    else:
        select = dict(edit.get("select") or {})
        if kind == "node":
            items = geometry.select_nodes(deck, **select).tolist()
        elif kind == "segment":
            items = geometry.exterior_segments(deck, **select).tolist()
        elif kind in ("shell", "solid"):
            keyword = "*ELEMENT_SOLID" if kind == "solid" else "*ELEMENT_SHELL"
            items = geometry.select_elements(deck, keyword, **select).tolist()
        else:
            raise FieldError(f"Give explicit ids for a {kind} set")
    sid, blocks = sets.create_set(deck, kind, items, sid=edit.get("sid"), title=edit.get("title"),
                                  file=_file(deck, edit.get("file")))
    change = deck.changes[-1]
    change.description = f"created {blocks[0].name} sid={sid} with {len(items)} items"
    if kind == "segment" and "ids" not in edit:
        select = dict(edit.get("select") or {})
        check = geometry.check_segment_normals(deck, blocks[0], select.get("direction"), select.get("angle", 30.0))
        if check["failures"]:
            deck.delete(blocks[0], force=True)
            raise FieldError(f"Segment normal check failed on rows {check['failures'][:10]} of the new set")
        change.description += (f"; normals checked on {check['sampled']} sampled segments: all outward"
                               + (f", within {check['max_angle_deg']} deg" if select.get("direction") else ""))
    return change


MESH_OPS = {"transform_nodes", "copy_elements", "array_elements", "offset_shells", "renumber",
            "merge_duplicate_nodes", "delete_elements", "reverse_elements", "unify_shell_normals", "clean_coordinates",
            "quantize_coordinates"}
PROPERTY_OPS = {"add_material": "material", "add_eos": "eos", "add_section": "section", "add_hourglass": "hourglass"}
SUMMARY_OPS = MESH_OPS | set(PROPERTY_OPS) | {"add_boundary", "set_control", "add_part", "set_part", "add_contact",
                                             "add_joint"}


def _setup_op(deck: KeywordDeck, edit: dict) -> dict:
    """P05 boundary conditions / loads (``units`` must be declared) and P10 control recipes."""
    if edit["op"] == "set_control":
        return {"cards": controls.apply_recipe(deck, edit["recipe"], dict(edit.get("params") or {}))}
    if edit["op"] == "add_part":
        fields = {k: edit[k] for k in ("title", "secid", "mid", "eosid", "hgid", "tmid", "pid") if k in edit}
        return materials.add_part(deck, **fields, file=_file(deck, edit.get("file")))
    if edit["op"] == "set_part":
        return materials.set_part(deck, edit["pid"], **{k: edit[k] for k in materials.PART_REFS if k in edit})
    if edit["op"] == "add_joint":
        params = {k: v for k, v in edit.items() if k not in ("op", "file")}
        return joints.add_joint(deck, **params, file=_file(deck, edit.get("file")))
    if edit["op"] == "add_contact":
        return contacts.add_contact(deck, edit["recipe"], edit["a"], edit.get("b"), params=edit.get("params"),
                                    cid=edit.get("cid"), title=edit.get("title"), file=_file(deck, edit.get("file")))
    if edit["op"] in PROPERTY_OPS:
        if not edit.get("units"):
            raise FieldError("Declare the unit system of the values (units); nothing is converted")
        family = PROPERTY_OPS[edit["op"]]
        ident = {"material": "mid", "eos": "eosid", "section": "secid", "hourglass": "hgid"}[family]
        extra = {ident: edit.get(ident), "title": edit.get("title"), "file": _file(deck, edit.get("file"))}
        params = dict(edit.get("params") or {})
        result = (materials.add_hourglass(deck, params, **extra) if family == "hourglass"
                  else materials.KINDS[family](deck, edit["recipe"], params, **extra))
        return {"units": edit["units"], **result}
    if not edit.get("units"):
        raise FieldError("Declare the unit system of the values (units); nothing is converted")
    kind = edit["kind"]
    if kind not in loads.KINDS:
        raise FieldError(f"Unknown boundary kind {kind!r}; use one of {sorted(loads.KINDS)}")
    params = {k: v for k, v in edit.items() if k not in ("op", "kind", "units")}
    return {"units": edit["units"], **loads.KINDS[kind](deck, **params)}


def _selected(deck: KeywordDeck, value: dict, entity: str) -> list[int]:
    """IDs of a ``core.contracts.Selector`` whose entity type must be ``entity``."""
    chosen = selectors.selector(value)
    if chosen.entity_type != entity:
        raise FieldError(f"Selector entity type {chosen.entity_type!r} does not match the {entity} target")
    return selectors.resolve(deck, chosen).tolist()


def _ids(deck: KeywordDeck, edit: dict, kind: str) -> list[int]:
    """Explicit ``ids``, a geometric ``select`` (box, sphere, plane, parts) or a ``selector``."""
    if "selector" in edit:
        entity = "node" if kind == "node" else ("shell" if edit["keyword"] == "*ELEMENT_SHELL" else "solid")
        return _selected(deck, edit["selector"], entity)
    if "ids" in edit:
        return [int(i) for i in edit["ids"]]
    select = dict(edit.get("select") or {})
    if not select:
        raise FieldError("Give ids or select")
    if kind == "node":
        return geometry.select_nodes(deck, **select).tolist()
    return geometry.select_elements(deck, edit["keyword"], **select).tolist()


def _affine(edit: dict) -> tuple[object, object]:
    """``(matrix, offset)`` from ``translate``, ``rotate``, ``reflect`` or ``matrix``/``offset``."""
    if "translate" in edit:
        return None, edit["translate"]
    if "rotate" in edit:
        spec = edit["rotate"]
        matrix = mesh.rotation_matrix(spec["axis"], float(spec["angle_deg"]))
        center = np.asarray(spec.get("center", (0.0, 0.0, 0.0)), dtype=float)
        return matrix, center - matrix @ center
    if "reflect" in edit:
        spec = edit["reflect"]
        return mesh.reflection(spec["normal"], spec.get("point", (0.0, 0.0, 0.0)))
    if "matrix" in edit:
        return edit["matrix"], edit.get("offset")
    raise FieldError("Give translate, rotate, reflect or matrix")


def _mesh_op(deck: KeywordDeck, edit: dict) -> dict:
    """P08 operations; each returns its own summary (changes are recorded by the deck)."""
    op = edit["op"]
    if op == "clean_coordinates":
        return coordinates.clean_coordinates(deck, edit.get("axes"), edit.get("rel_tol", 1e-9))
    if op == "quantize_coordinates":
        return coordinates.quantize_coordinates(deck, edit.get("axes"), edit.get("magnitude"), edit.get("rel_tol", 1e-9))
    if op == "transform_nodes":
        ids = _ids(deck, edit, "node")
        if "reflect" in edit:
            spec = edit["reflect"]
            return mesh.reflect_nodes(deck, ids, spec["normal"], spec.get("point", (0.0, 0.0, 0.0)),
                                      fix_orientation=bool(spec.get("fix_orientation", True)))
        matrix, offset = _affine(edit)
        return mesh.transform_nodes(deck, ids, matrix, offset)
    if op == "copy_elements":
        matrix, offset = _affine(edit) if any(k in edit for k in ("translate", "rotate", "reflect", "matrix")) \
            else (None, None)
        return mesh.copy_elements(deck, edit["keyword"], _ids(deck, edit, "element"), matrix=matrix,
                                  offset=offset, part_id=edit.get("part_id"))
    if op == "array_elements":
        matrix, offset = _affine(edit)
        return generate.array_elements(deck, edit["keyword"], _ids(deck, edit, "element"), edit["count"],
                                       matrix=matrix, offset=offset, part_id=edit.get("part_id"))
    if op == "offset_shells":
        return generate.offset_shells(deck, _ids(deck, {**edit, "keyword": "*ELEMENT_SHELL"}, "element"),
                                      edit["distance"], copy=bool(edit.get("copy", True)),
                                      part_id=edit.get("part_id"))
    if op == "renumber":
        if "mapping" in edit:
            return renumber.renumber(deck, edit["kind"], {int(a): int(b) for a, b in edit["mapping"].items()})
        return renumber.renumber_range(deck, edit["kind"], int(edit["first"]), int(edit["last"]), int(edit["start"]))
    if op == "merge_duplicate_nodes":
        ids = _ids(deck, edit, "node") if ("ids" in edit or "select" in edit) else None
        return renumber.merge_duplicate_nodes(deck, float(edit["tolerance"]), ids)
    if op == "delete_elements":
        return renumber.delete_elements(deck, edit["keyword"], _ids(deck, edit, "element"),
                                        delete_orphan_nodes=bool(edit.get("delete_orphan_nodes", False)))
    if op == "reverse_elements":
        return mesh.reverse_elements(deck, edit["keyword"], _ids(deck, edit, "element"))
    if op == "unify_shell_normals":
        ids = _ids(deck, {**edit, "keyword": "*ELEMENT_SHELL"}, "element") if ("ids" in edit or "select" in edit) \
            else None
        return mesh.unify_shell_normals(deck, ids, edit.get("direction"))
    raise FieldError(f"Unknown mesh op {op!r}")


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
        target = _file(deck, edit.get("file")) if edit.get("file") or not (anchor_before or anchor_after) else None
        if "card" in edit:
            card = edit["card"]
            deck.insert_card(card["keyword"], card.get("fields", {}), options=card.get("options"),
                             file=target, before=anchor_before, after=anchor_after)
        else:
            deck.insert(edit["text"], file=target, before=anchor_before, after=anchor_after)
        return deck.changes[before:]
    if op == "create_set":
        return [_create_set(deck, edit)]
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

    Field ops: set, set_parameter, set_members, set_points, insert, delete, create_set.
    Mesh ops (P08, summaries in ``summaries``): transform_nodes (translate / rotate / reflect /
    matrix), copy_elements, array_elements (count + step transform), offset_shells (distance,
    copy?, part_id?), renumber (mapping or first/last/start), merge_duplicate_nodes,
    delete_elements, reverse_elements, unify_shell_normals, clean_coordinates (axes?; one-pass cluster snap),
    quantize_coordinates (axes?, magnitude?; LS-PrePost move-far-and-back);
    targets by ``ids`` or ``select``.
    Setup ops: add_boundary (P05; ``kind`` from loads.KINDS, ``units`` required) and set_control
    (P10; ``recipe`` from controls.RECIPES or ascii, ``params``). Property ops (P03, ``units``
    required): add_material / add_eos / add_section (``recipe``, ``params``), add_hourglass
    (``params``); add_part (title, secid, mid, eosid?, hgid?, tmid?) and set_part (pid + fields).
    Contacts (P06): add_contact (``recipe`` from contacts.RECIPES, sides ``a``/``b``, ``params``
    with fs, ``cid``/``title``).
    """
    if output_dir and in_place:
        raise ValueError("Choose output_dir or in_place, not both")
    deck = KeywordDeck.load(path, include_paths)
    check_mesh = check_mesh or any(edit.get("op") in MESH_OPS for edit in edits)
    dangling_before = {(d["kind"], d["id"]) for d in deck.references(check_mesh).dangling()}
    applied, summaries = [], []
    for number, edit in enumerate(edits):
        try:
            if edit.get("op") in SUMMARY_OPS:
                before = len(deck.changes)
                run = _mesh_op if edit["op"] in MESH_OPS else _setup_op
                summaries.append({"edit": number, "op": edit["op"], **run(deck, edit)})
                changes = deck.changes[before:]
            else:
                changes = _apply(deck, edit)
        except (FieldError, Unsupported, KeyError, IndexError, ValueError) as error:
            return {"status": "failed", "failed_edit": number, "error": f"{type(error).__name__}: {error}",
                    "applied_before_failure": len(applied), "written": False}
        applied.extend({"edit": number, "file": str(c.path), "line": c.line, "keyword": c.keyword,
                        "description": c.description, "exact": c.exact} for c in changes)
    after = deck.references(check_mesh)
    new_dangling = [d for d in after.dangling() if (d["kind"], d["id"]) not in dangling_before]
    diff, truncated = persist.diff_preview(deck, MAX_DIFF)
    result = {"status": "succeeded", "changes": applied, "summaries": summaries, "diff": diff,
              "diff_truncated": truncated, "new_dangling": new_dangling[:200],
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


def check_deck(path: str, include_paths: tuple[str, ...] = (), thresholds: dict | None = None,
               coincident_tol: float | None = None, include_mesh: bool = True) -> dict:
    """Model check without LS-PrePost (P09): includes, parameters, references and element quality.

    Errors are objective defects (missing includes, include cycles, parameter errors, dangling
    or duplicate IDs, inverted/degenerate elements). Quality metrics are judged only against
    the given ``thresholds``.
    """
    deck = KeywordDeck.load(path, include_paths)
    errors = [{"kind": "include", "message": w} for w in deck.warnings
              if w.startswith(("Missing include", "Include cycle"))]
    errors += [{"kind": "parameter", "name": r.definition.name, "message": r.definition.error,
                **_site(r.block)} for r in deck.parameters if r.definition.error]
    report = deck.references(include_mesh)
    if report.dangling_count:
        errors.append({"kind": "dangling_references", "count": report.dangling_count, "sample": report.dangling()[:50]})
    duplicates = report.duplicates()
    if duplicates:
        errors.append({"kind": "duplicate_ids", "count": len(duplicates), "sample": duplicates[:50]})
    too_long, sample = solver_rules.long_free_items(deck)
    if too_long:
        errors.append({"kind": "free_format_item_too_long", "count": too_long, "sample": sample,
                       "message": "comma-separated values must fit the field width (R11 Error 10459)"})
    warnings = list(deck.warnings)
    joint_report = joint_checks.check_joints(deck)
    for kind in sorted({e["kind"] for e in joint_report["errors"]}):
        found = [e for e in joint_report["errors"] if e["kind"] == kind]
        errors.append({"kind": kind, "count": len(found), "sample": found[:20], "message": found[0]["message"]})
    warnings += [f"{w.get('keyword', 'joints')} ({w.get('file', '')}:{w.get('line', '')}): {w['message']}"
                 for w in joint_report["warnings"][:50]]
    for short in solver_rules.short_motion_curves(deck):
        warnings.append(f"{short['keyword']} ({short['file']}:{short['line']}) uses curve {short['lcid']}, which ends "
                        f"at {short['curve_end']:g} but the motion is active until {short['active_until']:g}; past "
                        "the last point R11 takes the prescribed value as 0 (extend the curve)")
    if report.unverified_count:
        warnings.append(f"{report.unverified_count} references to {', '.join(sorted(report.unverified_kinds))} IDs "
                        "could not be verified because a defining block was not read")
    result = {"references": {**report.summary(), "unused": report.unused(), "unverified": report.unverified()[:50]},
              "warnings": warnings, "read_only": True, "mesh_checked": include_mesh,
              "joints": {"checked": len(joint_report["joints"]), "summary": joint_report["joints"][:50],
                         "not_checked": joint_report["not_checked"][:20]}}
    unchecked = [f"References not read: {name} x{count}" for name, count in report.unchecked.items()]
    unchecked += [f"Joint check not verified: {u.get('keyword', '')} {u['reason']}" for u in joint_report["unverified"][:20]]
    if include_mesh:
        checked = quality.check_quality(deck, thresholds, coincident_tol)
        errors += checked["errors"]
        unchecked += [f"Mesh block not read: {item}" for item in checked["unchecked_mesh_blocks"]]
        result["quality"] = {k: v for k, v in checked.items() if k != "errors"}
        if not checked["unchecked_mesh_blocks"]:
            noise = coordinates.coordinate_noise(deck)
            result["coordinate_noise"] = noise
            if noise["nodes_affected"]:
                warnings.append(f"{noise['nodes_affected']} nodes have coordinate round-off below "
                                f"{noise['tolerance']:.3g} on axes {''.join(noise['noisy_axes'])}; "
                                "clean_coordinates snaps them to one value per cluster")
    result["errors"] = errors
    result["unchecked"] = unchecked
    result["complete"] = not unchecked  # ok=True only means no defect was found in what was read
    result["ok"] = not errors
    return result


def check_contacts(path: str, include_paths: tuple[str, ...] = (), tolerance: float = 0.0,
                   max_report: int = 50) -> dict:
    """Initial penetration of every *CONTACT definition at keyword level (P06, read-only)."""
    deck = KeywordDeck.load(path, include_paths)
    results = contact.contact_checks(deck, tolerance, max_report)
    return {"contacts": results, "penetrating_contacts": sum(1 for r in results if r.get("penetrating")),
            "not_checked": sum(1 for r in results if not r["checked"]), "assumptions": contact.ASSUMPTIONS,
            "read_only": True}
