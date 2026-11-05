"""Owned P05 single-file definitions through the existing create/save/export APIs.

The oracle is handwritten. Keyword export retention is neither typed native
boundary recognition nor a solver-response test. Native execution is opt-in.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import stat
import subprocess
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck, access, preflight_includes
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.native.versions import require_capability, require_installation
from ls_prepost_mcp.service import Service
from tools.native_regression import execution_identity

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/data/p05-boundary-roundtrip.json"
ATOL, RTOL = 1e-10, 1e-12
MAX_BYTES = 10 * 1024 * 1024
PRODUCT_PATHS = tuple("src/ls_prepost_mcp/" + path for path in (
    "domain/model/_identity.py", "domain/model/loads.py", "domain/model/deck.py",
    "domain/model/matching.py", "domain/model/fields.py", "domain/model/layouts.py",
    "domain/model/schema.py", "domain/model/cards.py", "domain/model/keyword_docs.py",
    "domain/model/blocks.py", "domain/model/text.py", "domain/model/geometry.py",
    "domain/model/access.py", "domain/model/preflight.py", "domain/model/persist.py",
    "domain/model/node_sets.py", "domain/model/sets.py", "domain/model/selectors.py",
    "domain/model/operations.py", "domain/model/references.py", "domain/model/lists.py",
    "domain/model/tables.py", "model_save.py", "model_target_tools.py", "keyword_staging.py",
    "service.py", "config.py", "jobs.py", "runner.py", "engine/batch.py",
    "engine/environment.py", "engine/processes.py", "native/commands.py", "native/versions.py",
))
CAPTURE_SOURCE_PATHS = PRODUCT_PATHS + (
    "tools/verify_p05_boundary_roundtrip.py", "tools/native_regression.py",
    "tests/data/p05-boundary-roundtrip.json", "tests/test_boundary_roundtrip_contract.py",
    "tests/test_boundary_native_readback.py",
    "pyproject.toml", "uv.lock",
)
MANUAL_SOURCE = dict(release="R11", volume="I",
    sha256="3f1cf3cc8c8222ad059459aca2c452f6af6afcce263b8eb8ba157495684da343")
MANUAL_PAGES = {
    "vid": (575, "5-47"), "initial": (2337, "24-95"), "icid": (2338, "24-96"),
    "node_sets": (2872, "39-20"), "part_sets": (2882, "39-30"),
    "segment_sets": (2887, "39-35"), "curves": (1716, "15-74"),
    "wall_id": (2731, "36-15"),
}
SDK_SOURCES = {
    "motion": "b063e5dc7937d792e78152e37fa2e7c4d37ac990f758adab2c9f54ea3a837b5e",
    "initial": "e4c36a223f9c0cdb710d62a6418cf0ed838a19e08fff2bc650fe758ba392d572",
    "node_sets": "9dcad2a77977e44212ce2ad256b7f435cd1678b4d63ae07e490102d57c274312",
    "segment_sets": "b03e41fb2b00e7912463c5e6ff9ca0d45c0d8c422f2fb57a4a37a790ba3d7908",
    "part_sets": "4f8c17211910a14ada4a7c54c766eaf66ef68292e898e8f9cf6fcad57bda32ed",
    "curves": "ebb3f922a3e58676a19aba2b892076c6ebc093db2b19dc55690c59d2c3da2fed",
    "wall_id": "9a53a669d629830186e73062067052462b047c0172d88956cf8765fc8ad011a7",
}
INITIAL_CARD = dict(xc=0., yc=0., zc=0., nx=0., ny=0., nz=0., phase=0, irigid=0)
CURVE_DEFAULTS = dict(sidr=0, sfa=1., sfo=1., offa=0., offo=0., dattyp=0, lcint=0)
OBSERVED_EXPORT_BUILDS = {
    "ce76fdf75a2f14c0a3e94964809ddd178934d04381f7f31e1e1eb05592bd5414": "4.13 observed calibration",
    "e24c2d20f5ccae3b125c553f7469cffe9f910ea25a1e38abff7d940298d0087b": "4.10 transfer check, not an independent default source",
}
EXPORT_CALIBRATION = dict(actual_git_revision="8e247c16c05e099b49d31fc6300789f7a4cf7807",
    export_sha256="ca8297369884d2d8d264582a16e580947dbe47132ba2b5c7910ee97534c714fa",
    capture_status="failed", scope="Observed writer representation only; not a prior native acceptance pass")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf8"))


def source_identity(identity):
    captured = identity.get("source_files", {})
    revision = identity.get("actual_git_head", "")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("Missing committed capture source revision")
    for path in CAPTURE_SOURCE_PATHS:
        digest = captured.get(path)
        if (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or not (ROOT / path).is_file() or sha(ROOT / path) != digest):
            raise ValueError("Missing or changed required capture source: " + path)
    output = subprocess.check_output(["git", "ls-tree", "-r", revision, "--", *CAPTURE_SOURCE_PATHS],
                                     cwd=ROOT, text=True, timeout=10)
    blobs = {}
    for line in output.splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, blob = metadata.split()
        if mode in ("100644", "100755") and kind == "blob":
            blobs[path] = blob
    if set(CAPTURE_SOURCE_PATHS) - blobs.keys():
        raise ValueError("Required sources must exist in the committed capture revision")
    return {path: dict(git_blob_id=blobs[path], captured_file_sha256=captured[path]) for path in CAPTURE_SOURCE_PATHS}


def build_source(directory, spec):
    """Write only declared tiny input geometry/dependencies, never oracle values."""
    directory.mkdir(parents=True, exist_ok=False)
    lines = ["*KEYWORD", "*TITLE", "P05 owned boundary definition fixture", "*NODE"]
    for uid, xyz in spec["nodes"].items():
        lines.append(f"{int(uid):>8}" + "".join(f"{float(v):>16g}" for v in xyz))
    lines.append("*ELEMENT_SOLID")
    for eid, element in spec["solids"].items():
        lines.append("".join(f"{v:>8}" for v in (int(eid), element["pid"], *element["nodes"])))
    lines += ["*SECTION_SOLID", "         1         1"]
    for pid, mid in spec["parts"].items():
        lines += ["*PART", f"fixture Part {pid}", f"{int(pid):>10}{1:>10}{mid:>10}"]
    lines += ["*MAT_ELASTIC", "         1      7800   2.1e11       0.3",
              "*MAT_RIGID", "         2      7800   2.1e11       0.3", "         0", "         0",
              "*CONTROL_TERMINATION", "       1.0"]
    for key, keyword in (("input_node_sets", "*SET_NODE_LIST"), ("part_sets", "*SET_PART_LIST")):
        for sid, members in spec[key].items():
            lines += [keyword, f"{int(sid):>10}", "".join(f"{n:>10}" for n in members)]
    for sid, rows in spec["input_segment_sets"].items():
        lines += ["*SET_SEGMENT", f"{int(sid):>10}", *["".join(f"{n:>10}" for n in row) for row in rows]]
    for lcid, points in spec["input_curves"].items():
        lines += ["*DEFINE_CURVE", f"{int(lcid):>10}", *[f"{float(x):>20g}{float(y):>20g}" for x, y in points]]
    path = directory / "main.k"
    path.write_text("\n".join([*lines, "*END", ""]), encoding="ascii", newline="\n")
    return path


def _fields(deck, block, row=None):
    fields = {}
    for item in deck.fields(block, row=row):
        if item.name in fields:
            raise ValueError("Ambiguous named field: " + item.name)
        fields[item.name] = item.value
    return fields


def _rows(deck, block):
    layout = deck.layout(block)
    return [_fields(deck, block, row) for row in layout.rows] if layout.rows else [_fields(deck, block)]


def _headers(deck, block):
    result = {}
    for item in deck.layout(block).fields:
        if item.name in result:
            raise ValueError("Ambiguous header field: " + item.name)
        result[item.name] = deck.get(block, item.name, card=item.card).value
    return result


def _unique(mapping, key, value):
    if key in mapping:
        raise ValueError("Duplicate fixture definition: " + str(key))
    mapping[key] = value


def _regular(path):
    info = path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400 or info.st_size > MAX_BYTES):
        raise ValueError("Expected a bounded owned regular keyword file")


def snapshot(path, *, native_export=False, metadata=None):
    """Use the existing guarded AST and named fields; never parse another grammar."""
    path = Path(path).absolute()
    guard = access.root_guard((path.parent,))
    with access.confined(guard):
        guard(path)
        _regular(path)
        preflight = preflight_includes(path)
        if not preflight["ok"] or preflight["references"] or len(preflight["files"]) != 1:
            raise ValueError("P05 fixture readback must be a standalone single file")
        deck = KeywordDeck.load(path)
        result = dict(boundaries={}, node_sets={}, segment_sets={}, part_sets={}, curves={},
                      nodes={}, parts={}, solids={}, material_types={})
        wanted = fixture()["expected"]["boundaries"]
        inert = {"*KEYWORD", "*TITLE", "*END", "*SECTION_SOLID", "*MAT_ELASTIC", "*MAT_RIGID",
                 "*CONTROL_TERMINATION"}
        for block in deck.iter_blocks():
            name = block.name
            if name in wanted or (native_export and name == "*RIGIDWALL_PLANAR_ID"):
                if name == "*RIGIDWALL_PLANAR_ID" and (block.keyword.flag or block.keyword.extra):
                    raise ValueError("Unverified native wall keyword flags or trailing options")
                rows = _rows(deck, block)
                if len(rows) != 1:
                    raise ValueError("This fixture requires one complete boundary instance per exact keyword")
                _unique(result["boundaries"], name, rows[0])
            elif name == "*NODE":
                for row in _rows(deck, block):
                    _unique(result["nodes"], str(row["nid"]), [row[k] for k in ("x", "y", "z")])
            elif name == "*ELEMENT_SOLID":
                for row in _rows(deck, block):
                    _unique(result["solids"], str(row["eid"]), dict(pid=row["pid"], nodes=[row[f"n{i}"] for i in range(1, 9)]))
            elif name == "*PART":
                for row in _rows(deck, block):
                    _unique(result["parts"], str(row["pid"]), dict(mid=row["mid"], secid=row["secid"]))
            elif name in ("*MAT_ELASTIC", "*MAT_RIGID"):
                _unique(result["material_types"], str(deck.get(block, "mid").value), name)
            elif name in ("*SET_NODE_LIST", "*SET_PART_LIST"):
                group = "node_sets" if name == "*SET_NODE_LIST" else "part_sets"
                _unique(result[group], str(deck.get(block, "sid").value),
                        dict(header=_headers(deck, block), members=deck.members(block)))
                if metadata is not None and name == "*SET_NODE_LIST":
                    _its_metadata(deck, block, group, metadata)
            elif name == "*SET_SEGMENT":
                _unique(result["segment_sets"], str(deck.get(block, "sid").value),
                        dict(header=_headers(deck, block), rows=_rows(deck, block)))
                if metadata is not None:
                    _its_metadata(deck, block, "segment_sets", metadata)
            elif name == "*DEFINE_CURVE":
                _unique(result["curves"], str(deck.get(block, "lcid").value),
                        dict(header=_headers(deck, block), points=[list(point) for point in deck.points(block)]))
            elif name not in inert:
                raise ValueError("Unverified fixture keyword/options: " + name)
        refs = deck.references()
        if refs.dangling_count:
            raise ValueError("Readback has undefined keyword references")
        if metadata is not None:
            metadata["single_file_no_include_or_cosim"] = True
        return result


def _its_metadata(deck, block, group, metadata):
    value = deck.get(block, "its")
    sid = deck.get(block, "sid").value
    metadata.setdefault("set_its", {})[f"definition.{group}.{sid}.header.its"] = dict(
        raw=value.raw, raw_token=value.raw.strip(), decoded_value=value.value,
        ast_kind=deck.layout(block).lookup("its").kind,
        sdk_declared_kind="str" if group == "node_sets" else "int",
        sdk_declared_default="1" if group == "node_sets" else None,
        sdk_class_sha256=SDK_SOURCES[group])


def projection_differences(actual, expected):
    """All declared keys and named fields must agree, with fixed physical-value tolerances."""
    differences = []

    def walk(path, wanted, observed):
        if isinstance(wanted, dict):
            if not isinstance(observed, dict) or wanted.keys() != observed.keys():
                differences.append(dict(field=path + ".keys", expected=sorted(wanted),
                                        actual=sorted(observed) if isinstance(observed, dict) else observed))
            for key, value in wanted.items():
                walk(path + "." + str(key), value, observed.get(key) if isinstance(observed, dict) else None)
        elif isinstance(wanted, list):
            if not isinstance(observed, list) or len(wanted) != len(observed):
                differences.append(dict(field=path, expected=wanted, actual=observed))
            else:
                for index, (a, b) in enumerate(zip(wanted, observed)):
                    walk(f"{path}[{index}]", a, b)
        elif type(wanted) is float:
            if (type(observed) not in (int, float) or not math.isfinite(observed)
                    or not math.isclose(wanted, observed, rel_tol=RTOL, abs_tol=ATOL)):
                differences.append(dict(field=path, expected=wanted, actual=observed))
        elif type(wanted) is int:
            if type(observed) is not int or observed != wanted:
                differences.append(dict(field=path, expected=wanted, actual=observed))
        elif observed != wanted:
            differences.append(dict(field=path, expected=wanted, actual=observed))

    walk("definition", expected, actual)
    return differences


def expected_projection(spec):
    # These are separate handwritten input and output declarations, not actual data.
    result = {**copy.deepcopy(spec["expected"]), **{key: copy.deepcopy(spec[key]) for key in ("nodes", "parts", "solids", "material_types")}}
    result["parts"] = {pid: dict(mid=mid, secid=1) for pid, mid in spec["parts"].items()}
    # Coordinate and curve values are continuous; IDs remain exact integers.
    result["nodes"] = {uid: [float(v) for v in xyz] for uid, xyz in spec["nodes"].items()}
    defaults = spec["expected_dependency_defaults"]
    for group in ("node_sets", "part_sets"):
        result[group] = {sid: dict(header=dict(sid=int(sid), **defaults[group]), members=members)
                         for sid, members in result[group].items()}
    result["segment_sets"] = {sid: dict(header=dict(sid=int(sid), **defaults["segment_sets"]),
        rows=[{**dict(zip(("n1", "n2", "n3", "n4"), nodes)), **defaults["segment_row"]} for nodes in rows])
        for sid, rows in result["segment_sets"].items()}
    result["curves"] = {lcid: dict(header=dict(lcid=int(lcid), **defaults["curves"]), points=points)
                        for lcid, points in result["curves"].items()}
    return result


def compare(path, spec):
    return projection_differences(snapshot(path), expected_projection(spec))


def _exact_written(value, wanted):
    if type(wanted) is float:
        return type(value) in (int, float) and math.isfinite(value) and value == wanted
    return type(value) is type(wanted) and value == wanted


def _basis(group, *, page=None):
    number, printed = MANUAL_PAGES[page or group]
    result = dict(manual={**MANUAL_SOURCE, "pdf_page": number, "printed_page": printed},
                  sdk=dict(package="ansys-dyna-core", version="0.12.1", class_sha256=SDK_SOURCES[group]))
    if group == "curves":
        result["manual"]["lcint_note"] = "LCINT0 inherits CONTROL_SOLUTION (pdf1718); it does not mean zero interpolation points"
    return result


def native_projection_comparison(actual, spec, metadata, executable_sha256):
    """Finite documented forms of this owned fixture; the source oracle stays strict.

    Added wall ID and ITS are observed representations, not documented defaults.
    Every source/actual field and newly introduced metadata remains available.
    """
    source = expected_projection(spec)
    expected = copy.deepcopy(source)
    strict = projection_differences(actual, source)
    formats, observations = [], []
    no_include = metadata.get("single_file_no_include_or_cosim") is True

    def write(target, observed, field, value, path, basis, group):
        if field in target and target[field] is None and field in observed and _exact_written(observed[field], value):
            target[field] = value
            formats.append(dict(field=path + "." + field, expected=None, actual=observed[field],
                                rule=group, source=basis))

    motion = "*BOUNDARY_PRESCRIBED_MOTION_RIGID"
    wanted, observed = expected["boundaries"].get(motion, {}), actual.get("boundaries", {}).get(motion, {})
    if all(type(record.get("dof")) is int and record["dof"] == 2
           and type(record.get("vad")) is int and record["vad"] == 0 for record in (wanted, observed)):
        write(wanted, observed, "vid", 0, "definition.boundaries." + motion,
              _basis("motion", page="vid"), "documented_motion_vid_default_in_owned_dof2_vad0")
    initial = "*INITIAL_VELOCITY_GENERATION"
    wanted, observed = expected["boundaries"].get(initial, {}), actual.get("boundaries", {}).get(initial, {})
    initial_context = no_include and all(
        type(record.get("styp")) is int and record["styp"] == 1
        and type(record.get("id")) is int and record["id"] == 301
        and _exact_written(record.get("omega"), 0.) for record in (wanted, observed))
    if initial_context:
        write(wanted, observed, "icid", 0, "definition.boundaries." + initial,
              _basis("initial", page="icid"), "documented_initial_global_coordinate_default")
        if (not (INITIAL_CARD.keys() & wanted.keys()) and set(observed) == set(wanted) | INITIAL_CARD.keys()
                and all(_exact_written(observed[key], value) for key, value in INITIAL_CARD.items())):
            wanted.update(INITIAL_CARD)
            formats.append(dict(field="definition.boundaries." + initial + ".added_card2",
                expected="absent", actual={key: observed[key] for key in INITIAL_CARD},
                rule="documented_complete_zero_default_initial_card2", source=_basis("initial")))
    for group in ("node_sets", "part_sets", "segment_sets", "curves"):
        defaults = CURVE_DEFAULTS if group == "curves" else dict(da1=0., da2=0., da3=0., da4=0., solver="MECH")
        for uid, record in expected[group].items():
            header = record["header"]
            observed_header = actual.get(group, {}).get(uid, {}).get("header", {})
            prefix = f"definition.{group}.{uid}.header"
            for field, value in defaults.items():
                write(header, observed_header, field, value, prefix, _basis(group), "documented_" + group + "_header_default")
            # ITS is not in R11's header table. It is only a recorded, exact
            # non-applicable slot in this one no-Include/COSIM fixture/build.
            if group not in ("node_sets", "segment_sets") or not no_include or executable_sha256 not in OBSERVED_EXPORT_BUILDS:
                continue
            value = 1 if group == "node_sets" else 0
            detail = metadata.get("set_its", {}).get(prefix + ".its", {})
            sdk_kind = "str" if group == "node_sets" else "int"
            sdk_default = "1" if group == "node_sets" else None
            if ("its" in header and header["its"] is None and _exact_written(observed_header.get("its"), value)
                    and _exact_written(detail.get("decoded_value"), value) and detail.get("ast_kind") == "int"
                    and detail.get("sdk_declared_kind") == sdk_kind and detail.get("raw_token") == str(value)
                    and "sdk_declared_default" in detail and detail["sdk_declared_default"] == sdk_default
                    and detail.get("sdk_class_sha256") == SDK_SOURCES[group]
                    and isinstance(detail.get("raw"), str) and detail["raw"].strip() == str(value)):
                header["its"] = value
                observations.append(dict(field=prefix + ".its", expected=None, actual=value,
                    metadata=copy.deepcopy(detail), rule="inapplicable_ITS_slot_in_owned_no_include_fixture",
                    documented_R11_default=False, general_ITS_semantics="unverified",
                    sdk=dict(package="ansys-dyna-core", version="0.12.1", declared_kind=sdk_kind,
                             declared_default=sdk_default,
                             class_sha256=SDK_SOURCES[group], applicability="Only IncludeCosim coupling sets are described"),
                    calibration=copy.deepcopy(EXPORT_CALIBRATION), build_scope=OBSERVED_EXPORT_BUILDS[executable_sha256]))
    plain, identified = "*RIGIDWALL_PLANAR", "*RIGIDWALL_PLANAR_ID"
    wall = actual.get("boundaries", {}).get(identified, {})
    body = {key: value for key, value in wall.items() if key not in ("id", "title")}
    if (no_include and executable_sha256 in OBSERVED_EXPORT_BUILDS and plain in expected["boundaries"]
            and identified not in expected["boundaries"] and plain not in actual.get("boundaries", {})
            and sum(name.startswith("*RIGIDWALL") for name in expected["boundaries"]) == 1
            and sum(name.startswith("*RIGIDWALL") for name in actual.get("boundaries", {})) == 1
            and set(wall) == set(expected["boundaries"][plain]) | {"id", "title"}
            and type(wall.get("id")) is int and wall["id"] == 1 and wall.get("title") is None
            and not projection_differences(body, expected["boundaries"][plain])):
        expected["boundaries"][identified] = {**expected["boundaries"].pop(plain), "id": 1, "title": None}
        observations.append(dict(field="definition.boundaries." + identified, expected_keyword=plain,
            actual_keyword=identified, added_fields=dict(id=wall["id"], title=wall["title"]),
            rule="exact_single_nonDISPLAY_wall_native_ID_representation", documented_R11_default=False,
            source=_basis("wall_id"), calibration=copy.deepcopy(EXPORT_CALIBRATION),
            scope="R11 permits RWID but gives no default; title comes from SDK, not that R11 table",
            build_scope=OBSERVED_EXPORT_BUILDS[executable_sha256]))
    return dict(strict_card_differences=strict, documented_default_writes=formats,
                observed_representation=observations, differences=projection_differences(actual, expected),
                source_definition_projection=source, native_expected_projection=expected,
                native_definition_projection=actual, native_metadata=metadata,
                general_ITS_semantics="unverified", typed_boundary_recognition="unverified", physical_response="not_run")


def native_export_comparison(path, spec, executable_sha256):
    metadata = {}
    actual = snapshot(path, native_export=True, metadata=metadata)
    return native_projection_comparison(actual, spec, metadata, executable_sha256)


def _one_file(path):
    _regular(path)
    return dict(**_file_identity(path), names=sorted(item.name for item in path.parent.iterdir()))


def prepare_case(directory, executable=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    spec = fixture()
    source = build_source(directory / "input", spec)
    before = _one_file(source)
    service = Service(Settings(directory / "work", executable, (source.parent,), timeout=60))
    created = service.create_entities(str(source), spec["operations"])
    if created["status"] != "succeeded":
        raise ValueError("create_entities failed: " + str(created.get("error")))
    edited = Path(created["data"]["main"])
    differences = compare(edited, spec)
    checked = service.check_model(str(edited))
    if differences or checked["status"] != "succeeded" or checked["data"]["errors"]:
        raise ValueError("Offline P05 fixture failed: " + str(differences or checked))
    if _one_file(source) != before:
        raise ValueError("Original P05 input changed during creation")
    return dict(directory=directory, source=source, service=service, spec=spec, edited=edited,
                source_identity=before, edited_identity=_one_file(edited), creation=created)


def _job(service, result):
    job_id = result.get("job_id")
    if not isinstance(job_id, str) or re.fullmatch(r"[0-9a-f]{32}", job_id) is None:
        raise ValueError("Native API result lacks an owned job ID")
    directory = service.jobs.root / job_id
    manifest = service.jobs.get(job_id)
    if (result.get("status") != "succeeded" or manifest.get("status") != "succeeded"
            or manifest.get("job_id") != job_id or directory.is_symlink()
            or getattr(directory.lstat(), "st_file_attributes", 0) & 0x400):
        raise ValueError("Native API job did not succeed in its owned directory")
    return directory, manifest


def _engine(manifest):
    engine = manifest.get("engine_result") or {}
    process = engine.get("data") or {}
    if (engine.get("job_id") != manifest.get("job_id") or engine.get("operation") != manifest.get("action")
            or engine.get("backend") != "lsprepost" or engine.get("stage") != "execution"
            or engine.get("status") not in ("unverified", "succeeded") or engine.get("error")
            or type(process.get("pid")) is not int or process["pid"] <= 0
            or process.get("graphics") is not False or "-nographics" not in process.get("argv", [])
            or process.get("returncode") != 0 or process.get("timed_out")
            or any(check.get("required", True) and check.get("status") not in ("passed", "not_applicable")
                   for check in engine.get("checks", []))):
        raise ValueError("Native job lacks successful owned headless execution evidence")


def _plain(value):
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    return value


def _file_identity(path):
    info = path.stat()
    return dict(sha256=sha(path), size=info.st_size, mtime_ns=info.st_mtime_ns)


def verify_native(prepared, identity):
    """Use only existing save_model (actual saved tree) and ordinary export_keyword."""
    if not identity.get("actual_git_head") or identity.get("working_tree_dirty") is not False:
        raise ValueError("Native verification requires a clean actual Git identity")
    sources = source_identity(identity)
    service, source, edited = prepared["service"], prepared["source"], prepared["edited"]
    executable = service.settings.native_executable()
    policy = require_installation(executable)
    if policy["version"] not in ("4.13", "4.10") or policy["version_source"] != "file_version_resource":
        raise ValueError("P05 fixture requires registered file-resource 4.13 or 4.10")
    require_capability(executable, "batch")
    config = locate_config(executable, os.environ)
    if config is None:
        raise ValueError("An initialized source configuration is required")
    executable_before, config_before = _file_identity(executable), _file_identity(config)
    proof = dict(status="failed", native_executed=False, differences=None, typed_boundary_recognition="unverified",
                 physical_response="not_run", scope="Owned single-file keyword definitions only",
                 actual_git_revision=identity["actual_git_head"], working_tree_dirty=False,
                 git_diff_sha256=identity["git_diff_sha256"], source_snapshot_sha256=identity["source_snapshot_sha256"],
                 source_identity=sources, executable=executable_before, source_config=config_before,
                 source_config_path=str(config),
                 source_config_origin="explicit_LSPP_CONFIG_SOURCE" if os.environ.get("LSPP_CONFIG_SOURCE") else "located_source",
                 binary_profile=policy, native_job_ids=[])
    saved_main, saved_before = None, None

    def remember(result):
        job_id = result.get("job_id")
        if isinstance(job_id, str) and re.fullmatch(r"[0-9a-f]{32}", job_id):
            manifest = service.jobs.get(job_id)
            process = (manifest.get("engine_result") or {}).get("data") or {}
            if type(process.get("pid")) is int and process["pid"] > 0:
                proof["native_executed"] = True
                proof["native_job_ids"].append(job_id)

    try:
        # Native entity counts/registry are compared before/after by save_model.
        # CNRB native Part classification is not inferred from its keyword PID.
        saved = service.save_model(str(edited))
        proof["save_model"] = saved
        for observation in saved.get("data", {}).get("observations", {}).values():
            remember(observation)
        save_dir, _ = _job(service, saved)
        observations = saved["data"]["observations"]
        if set(observations) != {"before_save", "after_reopen"}:
            raise ValueError("save_model lacks both required native observations")
        for observation in observations.values():
            _engine(service.jobs.get(observation["job_id"]))
        saved_main = Path(saved["data"]["main"])
        access.root_guard((save_dir,))(saved_main)
        _regular(saved_main)
        opened = saved["data"]["observations"]["after_reopen"].get("input_open") or {}
        if (opened.get("normalized") is not False or opened.get("load_name") != saved_main.name
                or Path(opened.get("cwd", "")).resolve() != saved_main.parent.resolve()
                or Path(opened.get("resolved_main", "")).resolve() != saved_main.resolve()):
            raise ValueError("save_model did not attest the actual saved-root reopen")
        if saved_main.read_bytes() != edited.read_bytes() or _one_file(edited) != prepared["edited_identity"]:
            raise ValueError("save_model changed this standalone definition fixture")
        saved_before = _one_file(saved_main)
        exported = service.export_keyword(str(saved_main))
        proof["export_result"] = exported
        remember(exported)
        export_dir, manifest = _job(service, exported)
        _engine(manifest)
        request = json.loads((export_dir / "request.json").read_text(encoding="utf8"))
        staged = export_dir / "input_data"
        _regular(staged)
        if (request.get("raw_keyword_tree") or "input_tree" in manifest
                or Path(request.get("model", "")).resolve() != staged.resolve()
                or staged.read_bytes() != saved_main.read_bytes()):
            raise ValueError("Export did not open the byte-identical standalone staged input")
        readback = export_dir / "model.k"
        _regular(readback)
        registered = [item for item in exported.get("artifacts", [])
                      if item.get("kind") == "keyword" and Path(item.get("path", "")) == readback]
        if len(registered) != 1 or registered[0].get("sha256") != sha(readback):
            raise ValueError("Exported definition lacks an exact registered artifact")
        proof.update(native_export_comparison(readback, prepared["spec"], executable_before["sha256"]))
        if proof["differences"]:
            raise ValueError("Exported definitions differ from handwritten expectations")
        if len(proof["native_job_ids"]) != 3 or len(set(proof["native_job_ids"])) != 3:
            raise ValueError("This fixture requires three distinct existing-API native jobs")
        proof.update(status="passed", readback_sha256=sha(readback), staged_input_sha256=sha(staged),
                     saved_sha256=sha(saved_main), boundary_count=9)
    except Exception as error:
        proof["error"] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        guards = dict(original_unchanged=lambda: _one_file(source) == prepared["source_identity"],
                      edited_unchanged=lambda: _one_file(edited) == prepared["edited_identity"],
                      executable_unchanged=lambda: _file_identity(executable) == executable_before,
                      source_configuration_unchanged=lambda: _file_identity(config) == config_before)
        if saved_main is not None and saved_before is not None:
            guards["saved_unchanged"] = lambda: _one_file(saved_main) == saved_before

        def same_checkout():
            after = execution_identity(ROOT)
            return (after["actual_git_head"] == identity["actual_git_head"] and after["working_tree_dirty"] is False
                    and after["source_snapshot_sha256"] == identity["source_snapshot_sha256"])

        guards["checkout_unchanged"] = same_checkout
        for name, check in guards.items():
            try:
                proof[name] = bool(check())
            except Exception as error:
                proof[name] = False
                proof.setdefault("guard_errors", {})[name] = str(error)
        if not all(proof[name] for name in guards):
            proof["status"] = "failed"
        (prepared["directory"] / "comparison.json").write_text(
            json.dumps(_plain(proof), ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf8")
        if proof["status"] != "passed" and "error" not in proof:
            raise ValueError("P05 source or native input identity guard failed")
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-native", action="store_true")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--profile", choices=("4.13", "4.10"))
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT):
        parser.error("--output must be fresh and outside the checkout")
    identity = None
    if args.run_native:
        if args.executable is None or args.profile is None:
            parser.error("--run-native requires an executable and explicit registered profile")
        policy = require_installation(args.executable, version=args.profile)
        if policy["version_source"] != "file_version_resource":
            parser.error("Native fixture requires file-resource executable identification")
        require_capability(args.executable, "batch")
        identity = execution_identity(ROOT)
        if identity["working_tree_dirty"] is not False:
            parser.error("Native fixture requires a clean actual Git checkout")
        source_identity(identity)
    prepared = prepare_case(output, args.executable)
    if args.run_native:
        current = execution_identity(ROOT, output)
        if (current["actual_git_head"] != identity["actual_git_head"] or current["working_tree_dirty"] is not False
                or current["source_snapshot_sha256"] != identity["source_snapshot_sha256"]):
            raise ValueError("Checkout changed during offline preparation")
        (output / "execution-context.json").write_text(json.dumps(current, separators=(",", ":")) + "\n", encoding="utf8")
        proof = verify_native(prepared, identity)
    else:
        proof = dict(status="passed", native_executed=False, scope="Offline Python creation/check only", boundary_count=9)
    print(json.dumps(_plain(proof), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
