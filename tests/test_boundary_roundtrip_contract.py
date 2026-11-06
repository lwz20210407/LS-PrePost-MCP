"""Independent P05 oracle/owned producer controls; no native execution here."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("ansys.dyna.core")

from ls_prepost_mcp.domain.model import KeywordDeck  # noqa: E402
from tools import verify_p05_boundary_roundtrip as verifier  # noqa: E402


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    return verifier.prepare_case(tmp_path_factory.mktemp("p05") / "case")


def changed(prepared, tmp_path, mutate):
    path = tmp_path / "edited.k"
    path.write_bytes(prepared["edited"].read_bytes())
    deck = KeywordDeck.load(path)
    mutate(deck)
    path.write_text(deck.main.text(), encoding="utf8", newline="\n")
    return path


def test_nine_kinds_have_handwritten_complete_definitions_and_dependencies(prepared):
    assert len(prepared["spec"]["operations"]) == len(prepared["spec"]["expected"]["boundaries"]) == 9
    assert verifier.compare(prepared["edited"], prepared["spec"]) == []
    assert verifier._one_file(prepared["source"]) == prepared["source_identity"]
    assert prepared["source"].read_bytes() != prepared["edited"].read_bytes()
    # Non-sequential user IDs, all-node wall ID=0 and explicit newly allocated
    # curve/set IDs are predetermined in the checked-in oracle.
    assert prepared["spec"]["expected"]["node_sets"]["103"] == [89, 121]
    assert prepared["spec"]["expected"]["boundaries"]["*RIGIDWALL_PLANAR"]["nsid"] == 0
    assert prepared["spec"]["expected"]["boundaries"]["*LOAD_SEGMENT_SET"]["lcid"] == 702


@pytest.mark.parametrize("keyword,field,value", [
    ("*BOUNDARY_SPC_SET", "dofy", 1),
    ("*BOUNDARY_PRESCRIBED_MOTION_RIGID", "sf", 0.5),
    ("*LOAD_NODE_SET", "dof", 2),
    ("*LOAD_SEGMENT_SET", "sf", 1250.0),
    ("*LOAD_BODY_Z", "sf", 9.81),
    ("*INITIAL_VELOCITY_GENERATION", "vz", 1.25),
    ("*RIGIDWALL_PLANAR", "fric", 0.1),
    ("*CONSTRAINED_NODAL_RIGID_BODY", "pnode", 11),
    ("*BOUNDARY_NON_REFLECTING", "as_", 1.0),
])
def test_each_boundary_field_change_is_detected(prepared, tmp_path, keyword, field, value):
    def mutate(deck):
        block = deck.blocks(keyword)[0]
        row = next(iter(deck.layout(block).rows), None)
        deck.set(block, field, value, row=row)

    path = changed(prepared, tmp_path, mutate)
    assert any(field in item["field"] for item in verifier.compare(path, prepared["spec"]))


@pytest.mark.parametrize("group", ["boundaries", "node_sets", "segment_sets", "part_sets", "curves", "nodes", "solids", "parts", "material_types"])
@pytest.mark.parametrize("fault", ["missing", "extra"])
def test_projection_rejects_missing_and_extra_definitions(prepared, group, fault):
    expected = verifier.expected_projection(prepared["spec"])
    actual = copy.deepcopy(expected)
    if fault == "missing":
        actual[group].pop(next(iter(actual[group])))
    else:
        actual[group]["unexpected"] = {}
    assert verifier.projection_differences(actual, expected)


@pytest.mark.parametrize("fault", ["missing", "extra", "bool", "wrong", "nan"])
def test_projection_cannot_ignore_missing_extra_or_mistyped_boundary_fields(prepared, fault):
    expected = verifier.expected_projection(prepared["spec"])
    actual = copy.deepcopy(expected)
    fields = actual["boundaries"]["*LOAD_NODE_SET"]
    if fault == "missing":
        fields.pop("m1")
    elif fault == "extra":
        fields["unverified"] = 0
    else:
        fields["lcid"] = {"bool": True, "wrong": 702, "nan": float("nan")}[fault]
    assert verifier.projection_differences(actual, expected)


@pytest.mark.parametrize("keyword,field,value", [
    ("*DEFINE_CURVE", "sfa", 2.0), ("*DEFINE_CURVE", "offo", 1.0),
    ("*SET_NODE_LIST", "da1", 1.0), ("*SET_SEGMENT", "da1", 1.0),
])
def test_dependency_header_changes_are_not_lost(prepared, tmp_path, keyword, field, value):
    def mutate(deck):
        deck.set(deck.blocks(keyword)[0], field, value)

    path = changed(prepared, tmp_path, mutate)
    assert any(field in item["field"] for item in verifier.compare(path, prepared["spec"]))


def test_segment_attributes_and_curve_points_are_checked(prepared, tmp_path):
    def mutate(deck):
        segment = deck.blocks("*SET_SEGMENT")[0]
        deck.set(segment, "a1", 4.0, row=next(iter(deck.layout(segment).rows)))
        deck.set_points(deck.blocks("*DEFINE_CURVE")[0], [(0., 2.), (1., 3.)])

    differences = verifier.compare(changed(prepared, tmp_path, mutate), prepared["spec"])
    assert any("a1" in item["field"] for item in differences)
    assert any("curves" in item["field"] for item in differences)


def test_duplicate_boundary_is_not_a_successful_single_instance(prepared, tmp_path):
    def mutate(deck):
        deck.insert("".join(deck.blocks("*LOAD_NODE_SET")[0].lines))

    with pytest.raises(ValueError, match="Duplicate"):
        verifier.snapshot(changed(prepared, tmp_path, mutate))


@pytest.mark.parametrize("keyword", ["*LOAD_NODE_SET_ID", "*BOUNDARY_UNVERIFIED", "*DEFINE_CURVE_TITLE"])
def test_alternate_options_or_unknown_passthrough_do_not_count_as_identified(prepared, tmp_path, keyword):
    path = tmp_path / "unverified.k"
    text = prepared["edited"].read_text(encoding="utf8")
    path.write_text(text.replace("*LOAD_NODE_SET\n", keyword + "\n"), encoding="utf8")
    with pytest.raises(ValueError, match="Unverified"):
        verifier.snapshot(path)


def test_missing_curve_is_a_definition_failure(prepared, tmp_path):
    def mutate(deck):
        deck.delete(deck.blocks("*DEFINE_CURVE")[0], force=True)

    with pytest.raises(ValueError, match="undefined"):
        verifier.snapshot(changed(prepared, tmp_path, mutate))


def test_readback_cannot_follow_include_to_original_fixture(prepared, tmp_path):
    path = tmp_path / "redirect.k"
    path.write_text("*KEYWORD\n*INCLUDE\n" + str(prepared["edited"]) + "\n*END\n", encoding="utf8")
    with pytest.raises((ValueError, PermissionError)):
        verifier.snapshot(path)


def test_dirty_identity_rejects_before_executable_or_native_io(tmp_path):
    def forbidden():
        pytest.fail("Native IO must not occur")

    prepared = dict(service=SimpleNamespace(settings=SimpleNamespace(native_executable=forbidden)))
    with pytest.raises(ValueError, match="clean actual Git"):
        verifier.verify_native(prepared, dict(actual_git_head="f" * 40, working_tree_dirty=True))


def test_missing_loads_identity_rejects_before_executable_io():
    identity = verifier.execution_identity(verifier.ROOT)
    identity["working_tree_dirty"] = False
    del identity["source_files"]["src/ls_prepost_mcp/domain/model/loads.py"]
    with pytest.raises(ValueError, match="required capture source"):
        verifier.verify_native({}, identity)


@pytest.mark.parametrize("name", ["contact_report", "contact"])
def test_missing_contact_check_helper_rejects_before_configuration_or_native_io(monkeypatch, name):
    identity = verifier.execution_identity(verifier.ROOT)
    identity["working_tree_dirty"] = False
    del identity["source_files"][f"src/ls_prepost_mcp/domain/model/{name}.py"]

    def forbidden(*args, **kwargs):
        pytest.fail("Required source rejection must precede configuration or native IO")

    monkeypatch.setattr(verifier, "locate_config", forbidden)
    with pytest.raises(ValueError, match="required capture source"):
        verifier.verify_native({}, identity)


def test_full_dependency_gate_explicitly_binds_identity_matching_and_loads():
    for name in ("_identity", "matching", "loads", "schema", "cards", "lists", "tables", "contact_report", "contact"):
        assert f"src/ls_prepost_mcp/domain/model/{name}.py" in verifier.PRODUCT_PATHS
    assert "tests/data/p05-boundary-roundtrip.json" in verifier.CAPTURE_SOURCE_PATHS
    assert len(verifier.PRODUCT_PATHS) == 36 and len(verifier.CAPTURE_SOURCE_PATHS) == 43


@pytest.mark.parametrize("fault", ["pid", "graphics", "returncode", "timed_out", "status", "required_check"])
def test_an_output_echo_cannot_replace_successful_native_engine_evidence(fault):
    manifest = dict(job_id="abc", action="export_keyword", engine_result=dict(job_id="abc", operation="export_keyword",
        status="unverified", stage="execution", backend="lsprepost", error=None,
        data=dict(pid=123, graphics=False, argv=["fake", "-nographics"], returncode=0, timed_out=False)))
    verifier._engine(manifest)
    engine = manifest["engine_result"]
    if fault in ("pid", "graphics", "returncode", "timed_out"):
        engine["data"][fault] = dict(pid=True, graphics=True, returncode=1, timed_out=True)[fault]
    elif fault == "status":
        engine["status"] = "failed"
    else:
        engine["checks"] = [dict(required=True, status="failed")]
    with pytest.raises(ValueError, match="headless"):
        verifier._engine(manifest)


def test_fixture_expected_values_are_not_rewritten_by_comparison(prepared):
    before = hashlib.sha256(verifier.FIXTURE.read_bytes()).hexdigest()
    expected = copy.deepcopy(prepared["spec"])
    expected["expected"]["boundaries"]["*LOAD_NODE_SET"]["sf"] = 8.0
    assert verifier.compare(prepared["edited"], expected)
    assert hashlib.sha256(verifier.FIXTURE.read_bytes()).hexdigest() == before
    assert json.loads(verifier.FIXTURE.read_text(encoding="utf8"))["expected"]["boundaries"]["*LOAD_NODE_SET"]["sf"] == -7.5


@pytest.mark.parametrize("fault", [None, "save_failed", "wrong_saved_root", "normalized_saved",
                                  "stage_mutated", "raw_tree", "export_failed", "wrong_output", "cfg_changed",
                                  "missing_before", "duplicate_observation",
                                  "documented_vid", "documented_icid", "documented_iv_card",
                                  "documented_set_headers", "documented_curve_headers",
                                  "observed_its_headers", "observed_wall_id", "complete_native_representation"])
def test_simulated_api_chain_requires_actual_saved_tree_exact_stage_and_all_guards(tmp_path, monkeypatch, fault):
    """Synthetic receipts exercise the producer only; these are not native passes."""
    prepared = verifier.prepare_case(tmp_path / "case")
    service = prepared["service"]
    executable, config = tmp_path / "owned-fake.exe", tmp_path / "owned-fake.conf"
    executable.write_bytes(b"synthetic executable fixture")
    config.write_bytes(b"synthetic configuration fixture")
    identity = dict(actual_git_head="a" * 40, working_tree_dirty=False, git_diff_sha256="b" * 64,
                    source_snapshot_sha256="c" * 64)
    monkeypatch.setattr(verifier, "source_identity", lambda identity: {"synthetic_unit_fixture": {}})
    monkeypatch.setattr(verifier, "execution_identity", lambda *a: identity)
    monkeypatch.setattr(type(service.settings), "native_executable", lambda self: executable)
    monkeypatch.setattr(verifier, "locate_config", lambda *a: config)
    monkeypatch.setattr(verifier, "require_installation", lambda *a: dict(version="4.13", version_source="file_version_resource"))
    monkeypatch.setattr(verifier, "require_capability", lambda *a: None)
    if hasattr(verifier, "OBSERVED_EXPORT_BUILDS"):
        monkeypatch.setitem(verifier.OBSERVED_EXPORT_BUILDS, verifier.sha(executable), "synthetic unit fixture, not native calibration")

    def job(action, engine=True):
        directory, manifest = service.jobs.create(action, {})
        manifest["status"] = "succeeded"
        if engine:
            manifest["engine_result"] = dict(job_id=manifest["job_id"], operation=action, backend="lsprepost",
                stage="execution", status="unverified", error=None,
                data=dict(pid=123, graphics=False, argv=[str(executable), "-nographics"], returncode=0, timed_out=False))
        (directory / "job.json").write_text(json.dumps(manifest), encoding="utf8")
        return directory, manifest

    def result(manifest, **data):
        return dict(job_id=manifest["job_id"], status="succeeded", data=data)

    def save(model):
        directory, manifest = job("save_model", engine=False)
        saved = directory / "deck" / "main.k"
        saved.parent.mkdir()
        saved.write_bytes(prepared["edited"].read_bytes())
        observations = {}
        for phase in ("before_save", "after_reopen"):
            _, observation = job("inspect_model")
            observations[phase] = result(observation)
        observations["after_reopen"]["input_open"] = dict(normalized=fault == "normalized_saved", load_name="main.k",
            cwd=str(saved.parent if fault != "wrong_saved_root" else tmp_path), resolved_main=str(saved))
        if fault == "missing_before":
            observations.pop("before_save")
        elif fault == "duplicate_observation":
            observations["before_save"]["job_id"] = observations["after_reopen"]["job_id"]
        value = result(manifest, main=str(saved), observations=observations)
        if fault == "save_failed":
            value["status"] = "failed"
        return value

    def export(model):
        directory, manifest = job("export_keyword")
        staged, output = directory / "input_data", directory / "model.k"
        staged.write_bytes(prepared["edited"].read_bytes())
        output.write_bytes(prepared["edited"].read_bytes())
        request = dict(model=str(staged), raw_keyword_tree=fault == "raw_tree")
        (directory / "request.json").write_text(json.dumps(request), encoding="utf8")
        if fault == "stage_mutated":
            staged.write_bytes(staged.read_bytes() + b"$ changed stage\n")
        if fault == "wrong_output":
            deck = KeywordDeck.load(output)
            deck.set(deck.blocks("*LOAD_BODY_Z")[0], "sf", 9.81)
            output.write_text(deck.main.text(), encoding="utf8")
        if fault in NATIVE_FORMS:
            write_native_form(output, fault)
        if fault == "cfg_changed":
            config.write_bytes(b"changed source configuration")
        value = result(manifest)
        value["artifacts"] = [dict(kind="keyword", path=str(output), sha256=verifier.sha(output))]
        if fault == "export_failed":
            value["status"] = "failed"
        return value

    monkeypatch.setattr(service, "save_model", save)
    monkeypatch.setattr(service, "export_keyword", export)
    if fault is None or fault in NATIVE_FORMS:
        proof = verifier.verify_native(prepared, identity)
        assert proof["status"] == "passed" and len(proof["native_job_ids"]) == 3
        assert proof["saved_sha256"] == proof["staged_input_sha256"]
    else:
        with pytest.raises(ValueError):
            verifier.verify_native(prepared, identity)
        proof = json.loads((prepared["directory"] / "comparison.json").read_text(encoding="utf8"))
        assert proof["status"] == "failed"


NATIVE_FORMS = {"documented_vid", "documented_icid", "documented_iv_card", "documented_set_headers",
                "documented_curve_headers", "observed_its_headers", "observed_wall_id", "complete_native_representation"}


def write_native_form(path, form="complete_native_representation"):
    """Independent tiny writer fixture, following the predeclared manual tables."""
    from ls_prepost_mcp.domain.model.cards import card_text

    deck = KeywordDeck.load(path)
    all_fields = form == "complete_native_representation"
    if all_fields or form == "documented_vid":
        deck.set(deck.blocks("*BOUNDARY_PRESCRIBED_MOTION_RIGID")[0], "vid", 0)
    if all_fields or form == "documented_icid":
        deck.set(deck.blocks("*INITIAL_VELOCITY_GENERATION")[0], "icid", 0)
    if all_fields or form == "documented_iv_card":
        block = deck.blocks("*INITIAL_VELOCITY_GENERATION")[0]
        while block.lines[-1].strip() == "":
            block.lines.pop()
        block.lines.append("".join(f"{v:>10}" for v in (0., 0., 0., 0., 0., 0., 0, 0)) + "\n")
        deck._layouts.clear()
    if all_fields or form == "documented_set_headers":
        for name in ("*SET_NODE_LIST", "*SET_PART_LIST"):
            for block in deck.blocks(name):
                for field in ("da1", "da2", "da3", "da4"):
                    deck.set(block, field, 0.)
                deck.set(block, "solver", "MECH")
    if all_fields or form == "documented_curve_headers":
        for block in deck.blocks("*DEFINE_CURVE"):
            for field, value in dict(sidr=0, sfa=1., sfo=1., offa=0., offo=0., dattyp=0, lcint=0).items():
                deck.set(block, field, value)
    if all_fields or form == "observed_its_headers":
        for name, value in (("*SET_NODE_LIST", 1), ("*SET_SEGMENT", 0)):
            for block in deck.blocks(name):
                deck.set(block, "its", value)
    if all_fields or form == "observed_wall_id":
        body = verifier.fixture()["expected"]["boundaries"]["*RIGIDWALL_PLANAR"]
        deck.delete(deck.blocks("*RIGIDWALL_PLANAR")[0], force=True)
        deck.insert(card_text("*RIGIDWALL_PLANAR_ID", {**body, "id": 1, "title": None}))
    path.write_text(deck.main.text(), encoding="utf8", newline="\n")


CALIBRATED_413 = "ce76fdf75a2f14c0a3e94964809ddd178934d04381f7f31e1e1eb05592bd5414"


@pytest.fixture(scope="module")
def native_projection(prepared, tmp_path_factory):
    directory = tmp_path_factory.mktemp("p05-writer-unit")
    path = directory / "writer.k"
    path.write_bytes(prepared["edited"].read_bytes())
    write_native_form(path)
    metadata = {}
    actual = verifier.snapshot(path, native_export=True, metadata=metadata)
    return path, actual, metadata, prepared["spec"]


def native_result(native_projection, mutate=None, *, build=CALIBRATED_413):
    _, actual, metadata, spec = native_projection
    actual, metadata, spec = copy.deepcopy(actual), copy.deepcopy(metadata), copy.deepcopy(spec)
    if mutate is not None:
        mutate(actual, metadata, spec)
    return verifier.native_projection_comparison(actual, spec, metadata, build)


def test_all_raw_differences_and_new_fields_survive_the_native_representation_audit(native_projection):
    proof = native_result(native_projection)
    assert proof["differences"] == [] and proof["strict_card_differences"]
    assert len(proof["documented_default_writes"]) == 37
    assert len(proof["observed_representation"]) == 6
    assert proof["general_ITS_semantics"] == "unverified"
    assert proof["native_definition_projection"]["boundaries"]["*RIGIDWALL_PLANAR_ID"]["id"] == 1
    assert proof["native_definition_projection"]["boundaries"]["*RIGIDWALL_PLANAR_ID"]["title"] is None
    assert len(next(row for row in proof["documented_default_writes"] if row["rule"].endswith("card2"))["actual"]) == 8
    node = proof["native_metadata"]["set_its"]["definition.node_sets.101.header.its"]
    assert type(node["decoded_value"]) is int and node["decoded_value"] == 1
    assert node["raw_token"] == "1" and node["ast_kind"] == "int" and node["sdk_declared_kind"] == "str"
    assert node["sdk_declared_default"] == "1"
    assert all(row["documented_R11_default"] is False for row in proof["observed_representation"])


def test_default_offline_comparison_still_refuses_the_added_native_option(native_projection):
    path, _, _, spec = native_projection
    with pytest.raises(ValueError, match="Unverified"):
        verifier.compare(path, spec)


DEFAULT_SLOT_PATHS = [
    ("boundaries", "*BOUNDARY_PRESCRIBED_MOTION_RIGID", "vid"),
    ("boundaries", "*INITIAL_VELOCITY_GENERATION", "icid"),
    *[("boundaries", "*INITIAL_VELOCITY_GENERATION", field) for field in ("xc", "yc", "zc", "nx", "ny", "nz", "phase", "irigid")],
    *[(group, sid, "header", field) for group, ids in (("node_sets", ("101", "102", "103")), ("part_sets", ("301",)))
      for sid in ids for field in ("da1", "da2", "da3", "da4", "solver")],
    *[("curves", sid, "header", field) for sid in ("701", "702") for field in ("sidr", "sfa", "sfo", "offa", "offo", "dattyp", "lcint")],
    *[(group, sid, "header", "its") for group, ids in (("node_sets", ("101", "102", "103")), ("segment_sets", ("201", "202"))) for sid in ids],
    ("boundaries", "*RIGIDWALL_PLANAR_ID", "id"), ("boundaries", "*RIGIDWALL_PLANAR_ID", "title"),
]


def set_path(record, path, value, *, remove=False):
    for key in path[:-1]:
        record = record[key]
    if remove:
        record.pop(path[-1])
    else:
        record[path[-1]] = value


@pytest.mark.parametrize("path", DEFAULT_SLOT_PATHS)
def test_each_nondefault_written_slot_remains_a_difference(native_projection, path):
    value = "UNEXPECTED" if path[-1] in ("title", "solver") else 3.25
    proof = native_result(native_projection, lambda actual, *_: set_path(actual, path, value))
    assert proof["differences"], path


@pytest.mark.parametrize("field", ["xc", "yc", "zc", "nx", "ny", "nz", "phase", "irigid"])
@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), 1e-20])
def test_added_initial_card_requires_all_exact_finite_defaults(native_projection, field, value):
    proof = native_result(native_projection, lambda actual, *_: set_path(
        actual, ("boundaries", "*INITIAL_VELOCITY_GENERATION", field), value))
    assert proof["differences"]
    assert not any(row["rule"].endswith("card2") for row in proof["documented_default_writes"])


@pytest.mark.parametrize("field", ["xc", "yc", "zc", "nx", "ny", "nz", "phase", "irigid"])
def test_a_partial_added_initial_card_is_not_normalized(native_projection, field):
    proof = native_result(native_projection, lambda actual, *_: set_path(
        actual, ("boundaries", "*INITIAL_VELOCITY_GENERATION", field), None, remove=True))
    assert proof["differences"]
    assert not any(row["rule"].endswith("card2") for row in proof["documented_default_writes"])


@pytest.mark.parametrize("fault", ["extra_card_field", "source_partial_card", "motion_dof4", "motion_vad1",
                                   "initial_styp2", "initial_id_changed", "initial_rotation", "source_missing_vid",
                                   "source_missing_icid", "source_explicit_vid", "source_explicit_icid"])
def test_documented_defaults_require_the_exact_owned_source_context(native_projection, fault):
    def mutate(actual, metadata, spec):
        motion, initial = "*BOUNDARY_PRESCRIBED_MOTION_RIGID", "*INITIAL_VELOCITY_GENERATION"
        if fault == "extra_card_field":
            actual["boundaries"][initial]["unverified"] = 0
        elif fault == "source_partial_card":
            spec["expected"]["boundaries"][initial]["xc"] = 0.
        elif fault in ("motion_dof4", "motion_vad1", "initial_styp2", "initial_id_changed", "initial_rotation"):
            keyword, field, value = {"motion_dof4": (motion, "dof", 4), "motion_vad1": (motion, "vad", 1),
                "initial_styp2": (initial, "styp", 2), "initial_id_changed": (initial, "id", 10),
                "initial_rotation": (initial, "omega", 2.)}[fault]
            actual["boundaries"][keyword][field] = value
            spec["expected"]["boundaries"][keyword][field] = value
        elif fault.endswith("vid"):
            fields, key = spec["expected"]["boundaries"][motion], "vid"
            fields.pop(key) if "missing" in fault else fields.update(vid=4)
        else:
            fields, key = spec["expected"]["boundaries"][initial], "icid"
            fields.pop(key) if "missing" in fault else fields.update(icid=4)

    assert native_result(native_projection, mutate)["differences"]


@pytest.mark.parametrize("group,sid,value", [("node_sets", "101", 1), ("segment_sets", "201", 0)])
@pytest.mark.parametrize("fault", ["missing_record", "bool", "float", "string", "raw_plus", "raw_zeros",
                                   "raw_other", "raw_float", "wrong_ast_kind", "wrong_sdk_kind", "wrong_sdk_hash",
                                   "wrong_sdk_default", "missing_sdk_default"])
def test_its_requires_exact_raw_ast_and_sdk_inventory(native_projection, group, sid, value, fault):
    def mutate(actual, metadata, spec):
        key = f"definition.{group}.{sid}.header.its"
        detail = metadata["set_its"][key]
        if fault == "missing_record":
            metadata["set_its"].pop(key)
        elif fault in ("bool", "float", "string"):
            bad = {"bool": bool(value), "float": float(value), "string": str(value)}[fault]
            actual[group][sid]["header"]["its"] = detail["decoded_value"] = bad
        elif fault.startswith("raw_"):
            raw = {"raw_plus": "+" + str(value), "raw_zeros": "0" + str(value), "raw_other": "3", "raw_float": f"{value}.0"}[fault]
            detail.update(raw=raw, raw_token=raw)
        elif fault == "wrong_ast_kind":
            detail["ast_kind"] = "str"
        elif fault == "wrong_sdk_kind":
            detail["sdk_declared_kind"] = "other"
        elif fault == "wrong_sdk_default":
            detail["sdk_declared_default"] = 9
        elif fault == "missing_sdk_default":
            detail.pop("sdk_declared_default")
        else:
            detail["sdk_class_sha256"] = "0" * 64

    assert native_result(native_projection, mutate)["differences"]


@pytest.mark.parametrize("fault", ["no_include_false", "no_include_string", "unknown_build", "id_bool", "id_float",
                                   "id_other", "title_changed", "title_missing", "body_changed", "body_missing",
                                   "both_keywords", "display_keyword", "source_second_wall"])
def test_observed_wall_representation_cannot_be_generalized(native_projection, fault):
    def mutate(actual, metadata, spec):
        plain, identified = "*RIGIDWALL_PLANAR", "*RIGIDWALL_PLANAR_ID"
        wall = actual["boundaries"][identified]
        if fault.startswith("no_include"):
            metadata["single_file_no_include_or_cosim"] = False if fault.endswith("false") else "true"
        elif fault in ("id_bool", "id_float", "id_other"):
            wall["id"] = {"id_bool": True, "id_float": 1., "id_other": 2}[fault]
        elif fault == "title_changed":
            wall["title"] = "unrequested descriptor"
        elif fault == "title_missing":
            wall.pop("title")
        elif fault == "body_changed":
            wall["zt"] = 2.
        elif fault == "body_missing":
            wall.pop("nsid")
        elif fault == "both_keywords":
            actual["boundaries"][plain] = spec["expected"]["boundaries"][plain]
        elif fault == "display_keyword":
            actual["boundaries"][identified + "_DISPLAY"] = actual["boundaries"].pop(identified)
        elif fault == "source_second_wall":
            spec["expected"]["boundaries"][plain + "_DISPLAY"] = spec["expected"]["boundaries"][plain]

    build = "0" * 64 if fault == "unknown_build" else CALIBRATED_413
    proof = native_result(native_projection, mutate, build=build)
    assert proof["differences"]
    assert not any(row["rule"].startswith("exact_single") for row in proof["observed_representation"])


def test_native_representation_never_rewrites_the_handwritten_source_oracle(native_projection):
    _, actual, metadata, spec = native_projection
    before = copy.deepcopy(spec)
    fixture_sha = verifier.sha(verifier.FIXTURE)
    proof = verifier.native_projection_comparison(actual, spec, metadata, CALIBRATED_413)
    assert proof["differences"] == [] and spec == before and verifier.sha(verifier.FIXTURE) == fixture_sha
    assert proof["source_definition_projection"]["node_sets"]["101"]["header"]["its"] is None
    assert proof["native_expected_projection"]["node_sets"]["101"]["header"]["its"] == 1
    assert "*RIGIDWALL_PLANAR" in proof["source_definition_projection"]["boundaries"]
    assert "*RIGIDWALL_PLANAR_ID" in proof["native_expected_projection"]["boundaries"]
    assert proof["source_definition_projection"]["boundaries"]["*INITIAL_VELOCITY_GENERATION"]["icid"] is None


@pytest.mark.parametrize("suffix", ["_DISPLAY", "+", " garbage", ",UNVERIFIED"])
def test_native_wall_option_is_exact_not_a_prefix_or_generic_id_strip(native_projection, tmp_path, suffix):
    path = tmp_path / "wrong-option.k"
    source = native_projection[0].read_text(encoding="utf8")
    path.write_text(source.replace("*RIGIDWALL_PLANAR_ID\n", "*RIGIDWALL_PLANAR_ID" + suffix + "\n"), encoding="utf8")
    with pytest.raises(ValueError, match="Unverified"):
        verifier.native_export_comparison(path, native_projection[3], CALIBRATED_413)
