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


def test_full_dependency_gate_explicitly_binds_identity_matching_and_loads():
    for name in ("_identity", "matching", "loads", "schema", "cards", "lists", "tables"):
        assert f"src/ls_prepost_mcp/domain/model/{name}.py" in verifier.PRODUCT_PATHS
    assert "tests/data/p05-boundary-roundtrip.json" in verifier.CAPTURE_SOURCE_PATHS


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
                                  "missing_before", "duplicate_observation"])
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
        if fault == "cfg_changed":
            config.write_bytes(b"changed source configuration")
        value = result(manifest)
        value["artifacts"] = [dict(kind="keyword", path=str(output), sha256=verifier.sha(output))]
        if fault == "export_failed":
            value["status"] = "failed"
        return value

    monkeypatch.setattr(service, "save_model", save)
    monkeypatch.setattr(service, "export_keyword", export)
    if fault is None:
        proof = verifier.verify_native(prepared, identity)
        assert proof["status"] == "passed" and len(proof["native_job_ids"]) == 3
        assert proof["saved_sha256"] == proof["staged_input_sha256"]
    else:
        with pytest.raises(ValueError):
            verifier.verify_native(prepared, identity)
        proof = json.loads((prepared["directory"] / "comparison.json").read_text(encoding="utf8"))
        assert proof["status"] == "failed"
