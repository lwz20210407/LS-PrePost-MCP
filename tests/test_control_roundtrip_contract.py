"""P10 explicit-field readback contracts; all native-facing tests use owned fake receipts."""
import copy
import json
import stat
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from tools import verify_p10_control_roundtrip as verifier


@pytest.fixture
def prepared(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    return verifier.prepare_case(tmp_path / "case")


def test_offline_eight_cards_keep_the_handwritten_values_geometry_references_and_original_bytes(prepared):
    observation = verifier.snapshot(prepared["edited"])
    assert len(observation["controls"]) == 8
    assert verifier.compare(prepared["edited"], prepared["spec"]) == []
    assert prepared["source"].read_text(encoding="ascii") == prepared["spec"]["source"]
    assert observation["references"]["dangling"] == 0
    assert prepared["spec"]["units"] and all(item["units"] == prepared["spec"]["units"] for item in prepared["spec"]["operations"])


def test_unset_native_fields_are_observed_without_blank_zero_normalization_or_oracle_backfill(prepared):
    actual = verifier.snapshot(prepared["edited"])
    before = copy.deepcopy(prepared["spec"])
    actual["controls"]["*CONTROL_TIMESTEP"]["fields"]["dtinit"] = 0.0
    assert verifier.projection_differences(actual, prepared["spec"]) == []
    assert actual["controls"]["*CONTROL_TIMESTEP"]["fields"]["dtinit"] == 0.0
    assert prepared["spec"] == before and "dtinit" not in before["expected"]["controls"]["*CONTROL_TIMESTEP"]


def test_wrong_caller_field_is_detected_without_using_actual_as_expected(prepared):
    actual = verifier.snapshot(prepared["edited"])
    before = copy.deepcopy(prepared["spec"])
    actual["controls"]["*CONTROL_TERMINATION"]["fields"]["endtim"] = 0.0
    assert any("endtim" in item["field"] for item in verifier.projection_differences(actual, prepared["spec"]))
    assert prepared["spec"] == before


def test_dirty_or_missing_sources_reject_before_configuration_or_native_io(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Source admission must precede configuration/native IO")

    monkeypatch.setattr(verifier, "profile_inputs_identity", forbidden)
    with pytest.raises(ValueError, match="clean actual Git"):
        verifier.verify_native({}, dict(actual_git_head="f" * 40, working_tree_dirty=True), {})
    identity = dict(actual_git_head="f" * 40, working_tree_dirty=False, source_files={})
    with pytest.raises(ValueError, match="required capture source"):
        verifier.verify_native({}, identity, {})


def test_fixture_is_a_handwritten_oracle_and_default_entry_point_is_offline(monkeypatch, tmp_path):
    data = verifier.fixture()
    assert data["expected"]["controls"]["*CONTROL_TERMINATION"]["endtim"] == 50e-6
    assert data["expected"]["controls"]["*DATABASE_BINARY_D3PLOT"]["dt"] == 1e-6
    assert all(data["expected"]["controls"]["*DATABASE_" + name]["dt"] == 1e-7 for name in ("GLSTAT", "MATSUM", "RCFORC"))
    monkeypatch.setattr(verifier, "verify_native", lambda *args, **kwargs: pytest.fail("Offline default must not start native"))
    monkeypatch.setattr("sys.argv", ["verify_p10_control_roundtrip.py", "--output", str(tmp_path / "offline")])
    pytest.importorskip("ansys.dyna.core")
    verifier.main()
    assert json.loads((tmp_path / "offline/offline.json").read_text(encoding="utf8"))["native_executed"] is False


@pytest.mark.parametrize("keyword,field,value", [
    ("*CONTROL_TERMINATION", "endtim", 0.00006), ("*CONTROL_TIMESTEP", "tssfac", .7),
    ("*CONTROL_HOURGLASS", "ihq", 1), ("*CONTROL_HOURGLASS", "qh", .04),
    ("*CONTROL_ENERGY", "hgen", 1), ("*DATABASE_BINARY_D3PLOT", "dt", .000002),
    ("*DATABASE_GLSTAT", "dt", .0000002), ("*DATABASE_MATSUM", "binary", 0),
    ("*DATABASE_RCFORC", "dt", .0000002),
])
def test_each_explicit_control_value_is_independently_checked(prepared, keyword, field, value):
    actual = verifier.snapshot(prepared["edited"])
    actual["controls"][keyword]["fields"][field] = value
    assert any(item["field"] == keyword + "." + field for item in verifier.projection_differences(actual, prepared["spec"]))


@pytest.mark.parametrize("group", ["nodes", "solids", "parts", "sections", "materials"])
def test_geometry_and_reference_definitions_cannot_be_replaced_by_control_echo(prepared, group):
    actual = verifier.snapshot(prepared["edited"])
    actual[group].pop(next(iter(actual[group])))
    assert verifier.projection_differences(actual, prepared["spec"])


def test_wrong_input_parameters_do_not_generate_the_expected_oracle(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    spec = verifier.fixture()
    spec["operations"][0]["params"]["endtim"] = .00006
    expected = copy.deepcopy(spec["expected"])
    with pytest.raises(ValueError, match="independent oracle"):
        verifier.prepare_case(tmp_path / "wrong", spec=spec)
    assert spec["expected"] == expected


def test_missing_units_rejects_before_creating_the_input_directory(tmp_path):
    spec = verifier.fixture()
    spec["units"] = ""
    with pytest.raises(ValueError, match="units"):
        verifier.prepare_case(tmp_path / "no-units", spec=spec)
    assert not (tmp_path / "no-units").exists()


@pytest.fixture
def simulated(prepared, tmp_path, monkeypatch):
    """Receipts below are synthetic contract controls, never evidence of actual native execution."""
    service = prepared["service"]
    prepared["creation_mode"] = "recipe"
    prepared["recipe_reference"] = "model:synthetic-p10-unit-bundle@" + "a" * 64
    prepared["creation"]["operation"] = "run_recipe"
    prepared["creation"]["data"]["recipe"] = dict(reference_policy="pinned", reference=prepared["recipe_reference"],
        requested_reference=prepared["recipe_reference"])
    executable, configuration = tmp_path / "owned-fake.exe", tmp_path / "owned-fake.cfg"
    executable.write_bytes(b"not executable; no process may be launched")
    configuration.write_bytes(b"owned fake configuration")
    monkeypatch.setenv("LSPP_CONFIG_SOURCE", str(configuration))
    identity = dict(actual_git_head="a" * 40, working_tree_dirty=False, git_diff_sha256="b" * 64,
                    source_snapshot_sha256="c" * 64)
    profiles = {version: dict(configuration=dict(sha256=verifier.shared.sha(configuration)),
                             executable=verifier.shared._file_identity(executable), profile=dict(version=version))
                for version in ("4.13", "4.10")}
    inputs = {"4.13": dict(executable=str(executable), source=str(configuration)),
              "4.10": dict(executable=str(tmp_path / "other-owned-fake.exe"), source=str(configuration))}
    monkeypatch.setattr(verifier, "source_identity", lambda value: {"synthetic_unit_source": {}})
    monkeypatch.setattr(verifier, "profile_inputs_identity", lambda value: copy.deepcopy(profiles))
    monkeypatch.setattr(verifier, "execution_identity", lambda root: dict(identity))
    monkeypatch.setattr(verifier, "native_processes", lambda: [])
    monkeypatch.setattr(verifier, "locate_config", lambda *args: configuration)
    monkeypatch.setattr(type(service.settings), "native_executable", lambda self: executable)
    manifests = {}
    original_get = service.jobs.get
    monkeypatch.setattr(service.jobs, "get", lambda job_id: manifests[job_id] if job_id in manifests else original_get(job_id))

    def job(number, action, native=True):
        job_id = f"{number:032x}"
        folder = service.jobs.root / job_id
        folder.mkdir(exist_ok=False)
        item = dict(job_id=job_id, action=action, status="succeeded")
        if native:
            item["executable"] = dict(path=str(executable), **verifier.shared._file_identity(executable))
            item["engine_result"] = dict(job_id=job_id, operation=action, backend="lsprepost", stage="execution",
                status="unverified", error=None, data=dict(pid=1000 + number, graphics=False,
                argv=[str(executable), "-nographics"], returncode=0, timed_out=False, process_isolation="windows_job",
                configuration=dict(source=str(configuration), source_sha256=verifier.shared.sha(configuration), source_modified=False)))
        manifests[job_id] = item
        return job_id, folder

    state = dict(fault=None, calls=[])

    def corrupt(job_id):
        if int(job_id, 16) != state.get("bad_job", 2):
            return
        manifest = manifests[job_id]
        if state["fault"] == "wrong_executable":
            manifest["engine_result"]["data"]["argv"][0] = str(tmp_path / "nonexistent-wrong.exe")
        elif state["fault"] == "wrong_manifest_executable":
            manifest["executable"]["path"] = str(tmp_path / "nonexistent-wrong.exe")
        elif state["fault"] == "wrong_native_role":
            manifest["action"] = manifest["engine_result"]["operation"] = "wrong_but_self_consistent_role"

    def save(model, **kwargs):
        state["calls"].append("save_model")
        assert Path(model) == prepared["edited"]
        assert kwargs == dict(expected_counts=dict(nodes=8, elements=1), expected_part_ids=[10])
        save_id, save_dir = job(1, "save_model", native=False)
        before_id, _ = job(2, "inspect_model")
        after_id, _ = job(3, "inspect_model")
        corrupt(before_id)
        corrupt(after_id)
        saved = save_dir / "deck/main.k"
        saved.parent.mkdir()
        saved.write_bytes(prepared["edited"].read_bytes())
        opened = dict(normalized=False, load_name=saved.name, cwd=str(saved.parent), resolved_main=str(saved))
        if state["fault"] == "wrong_saved_root":
            opened["resolved_main"] = str(prepared["edited"])
        if state["fault"] == "changed_saved_bytes":
            saved.write_bytes(saved.read_bytes() + b"$ changed\n")
        result = dict(job_id=save_id, status="succeeded", data=dict(main=str(saved), observations={
            "before_save": dict(job_id=before_id), "after_reopen": dict(job_id=after_id, input_open=opened)}))
        if state["fault"] == "save_failed":
            result["status"] = manifests[save_id]["status"] = "failed"
        if state["fault"] == "no_job_object":
            manifests[before_id]["engine_result"]["data"]["process_isolation"] = "none"
        return result

    def export(model):
        state["calls"].append("export_keyword")
        job_id, folder = job(4, "export_keyword")
        corrupt(job_id)
        staged, output = folder / "input_data", folder / "model.k"
        staged.write_bytes(Path(model).read_bytes())
        output.write_bytes(staged.read_bytes())
        (folder / "request.json").write_text(json.dumps(dict(model=str(staged))), encoding="utf8")
        if state["fault"] == "wrong_stage":
            staged.write_bytes(staged.read_bytes() + b"$ wrong stage\n")
        if state["fault"] == "raw_tree":
            manifests[job_id]["input_tree"] = {}
        if state["fault"] == "wrong_field":
            deck = KeywordDeck.load(output)
            deck.set(deck.blocks("*CONTROL_TERMINATION")[0], "endtim", .00006)
            output.write_text(deck.main.text(), encoding="utf8")
        if state["fault"] == "source_mutated":
            prepared["source"].write_bytes(prepared["source"].read_bytes() + b"$ unexpected source edit\n")
        if state["fault"] == "profile_mutated":
            profiles["4.10"]["configuration"]["sha256"] = "0" * 64
        artifacts = [dict(kind="keyword", path=str(output), sha256=verifier.shared.sha(output))]
        if state["fault"] == "wrong_output":
            artifacts[0]["path"] = str(staged)
        return dict(job_id=job_id, status="succeeded", artifacts=artifacts)

    monkeypatch.setattr(service, "save_model", save)
    monkeypatch.setattr(service, "export_keyword", export)
    return prepared, identity, inputs, state


@pytest.mark.parametrize("fault", [None, "save_failed", "wrong_saved_root", "changed_saved_bytes", "wrong_stage",
                                  "raw_tree", "wrong_field", "wrong_output", "source_mutated", "profile_mutated", "no_job_object"])
def test_simulated_existing_api_chain_fails_closed_and_preserves_failure_receipts(simulated, fault):
    prepared, identity, inputs, state = simulated
    state["fault"] = fault
    if fault is None:
        proof = verifier.verify_native(prepared, identity, inputs)
        assert proof["status"] == "passed" and proof["differences"] == []
        assert len(set(proof["native_job_ids"])) == 3
        assert proof["typed_control_recognition"] == "unverified" and proof["physical_response"] == "not_run"
        assert state["calls"] == ["save_model", "export_keyword"]
    else:
        with pytest.raises(ValueError):
            verifier.verify_native(prepared, identity, inputs)
        proof = json.loads((prepared["directory"] / "comparison.json").read_text(encoding="utf8"))
        assert proof["status"] == "failed"
        if fault in ("save_failed", "wrong_saved_root", "changed_saved_bytes", "no_job_object"):
            assert state["calls"] == ["save_model"]


@pytest.mark.parametrize("missing", ["src/ls_prepost_mcp/domain/model/controls.py",
    "tools/verify_p10_control_roundtrip.py", "tests/data/p10-control-roundtrip.json"])
def test_each_missing_product_producer_or_fixture_rejects_before_native_profile_io(monkeypatch, missing):
    identity = dict(actual_git_head="a" * 40, working_tree_dirty=False,
                    source_files={path: verifier.shared.sha(verifier.ROOT / path) for path in verifier.CAPTURE_SOURCE_PATHS})
    del identity["source_files"][missing]
    monkeypatch.setattr(verifier, "profile_inputs_identity", lambda *args: pytest.fail("Source admission must run first"))
    with pytest.raises(ValueError, match=missing):
        verifier.verify_native({}, identity, {})


def test_both_private_inputs_are_required_and_writable_origin_rejects_before_version_io(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="both"):
        verifier.profile_inputs_identity({})
    configuration = tmp_path / "writable.cfg"
    configuration.write_bytes(b"synthetic configuration")
    configuration.chmod(stat.S_IREAD | stat.S_IWRITE)
    monkeypatch.setattr(verifier, "require_installation", lambda *args, **kwargs: pytest.fail("Readonly admission precedes executable IO"))
    inputs = {version: dict(executable=str(tmp_path / (version + ".exe")), source=str(configuration)) for version in ("4.13", "4.10")}
    with pytest.raises(ValueError, match="readonly"):
        verifier.profile_inputs_identity(inputs)


def test_readonly_profile_inputs_keep_full_hash_stat_and_central_batch_policy(tmp_path, monkeypatch):
    inputs, calls = {}, []
    monkeypatch.setattr(verifier, "require_installation", lambda exe, version: dict(version=version, version_source="file_version_resource"))
    monkeypatch.setattr(verifier, "require_capability", lambda exe, name: calls.append(name))
    for version in ("4.13", "4.10"):
        directory = tmp_path / version
        directory.mkdir()
        executable, source = directory / "fake.exe", directory / "private.cfg"
        executable.write_bytes(b"not executable")
        source.write_bytes(b"owned readonly test input")
        source.chmod(stat.S_IREAD)
        inputs[version] = dict(executable=str(executable), source=str(source))
    try:
        captured = verifier.profile_inputs_identity(inputs)
        assert calls == ["batch", "batch"]
        assert set(captured) == {"4.13", "4.10"}
        assert all(row["readonly"] and row["configuration"]["sha256"] for row in captured.values())
        assert all(row["device"] and row["inode"] for row in captured.values())
    finally:
        for item in inputs.values():
            Path(item["source"]).chmod(stat.S_IREAD | stat.S_IWRITE)


def test_recipe_creation_uses_pinned_public_entry_and_handwritten_oracle(tmp_path, monkeypatch):
    pytest.importorskip("ansys.dyna.core")
    reference = "model:synthetic-p10-unit-bundle@" + "a" * 64
    values = dict(units=verifier.fixture()["units"], explicit_parameters="owned fake-adapter control")
    observed = []

    def recipe(service, selected, parameters, model, file_type):
        observed.append((selected, copy.deepcopy(parameters), file_type))
        result = service.edit_keywords(model, verifier.fixture()["operations"])
        result["operation"] = "run_recipe"
        result["data"]["recipe"] = dict(reference_policy="pinned", reference=selected, requested_reference=selected)
        return result

    monkeypatch.setattr(verifier.Service, "run_recipe", recipe)
    prepared = verifier.prepare_case(tmp_path / "recipe", creation_mode="recipe", recipe_reference=reference, recipe_parameters=values)
    assert prepared["creation_mode"] == "recipe" and prepared["recipe_reference"] == reference
    assert observed == [(reference, values, "keyword")]
    assert verifier.compare(prepared["edited"], prepared["spec"]) == []


def test_unpinned_recipe_and_base_native_mode_reject_before_execution(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="pinned"):
        verifier.prepare_case(tmp_path / "not-created", creation_mode="recipe", recipe_reference="model:unpinned", recipe_parameters={})
    assert not (tmp_path / "not-created").exists()
    monkeypatch.setattr(verifier, "source_identity", lambda identity: {})
    monkeypatch.setattr(verifier, "profile_inputs_identity", lambda inputs: pytest.fail("Recipe admission precedes profile IO"))
    with pytest.raises(ValueError, match="actual pinned run_recipe"):
        verifier.verify_native(dict(creation_mode="edit_keywords"), dict(actual_git_head="a" * 40, working_tree_dirty=False), {})


def test_recipe_pin_dependencies_and_shared_artifact_guards_are_explicit_capture_sources():
    assert len(verifier.PRODUCT_PATHS) == len(set(verifier.PRODUCT_PATHS))
    for path in ("model_recipes.py", "data/model_recipes.json", "automation/recipes.py", "core/validation.py",
                 "domain/model/materials.py", "domain/model/controls.py"):
        assert "src/ls_prepost_mcp/" + path in verifier.PRODUCT_PATHS
    assert "tools/verify_p05_boundary_roundtrip.py" in verifier.CAPTURE_SOURCE_PATHS
    assert "tests/data/p10-control-roundtrip.json" in verifier.CAPTURE_SOURCE_PATHS


@pytest.mark.parametrize("target", ["source", "edited"])
def test_changed_offline_input_rejects_before_any_native_action(simulated, target):
    prepared, identity, inputs, state = simulated
    path = prepared[target]
    path.write_bytes(path.read_bytes() + b"$ stale offline input\n")
    with pytest.raises(ValueError, match="Offline input namespace or bytes changed"):
        verifier.verify_native(prepared, identity, inputs)
    assert state["calls"] == []


@pytest.mark.parametrize("bad_job", [2, 3, 4])
@pytest.mark.parametrize("fault", ["wrong_executable", "wrong_manifest_executable", "wrong_native_role"])
def test_each_job_binds_selected_executable_and_expected_native_role(simulated, bad_job, fault):
    prepared, identity, inputs, state = simulated
    state.update(fault=fault, bad_job=bad_job)
    with pytest.raises(ValueError, match="executable|role"):
        verifier.verify_native(prepared, identity, inputs)


def test_recipe_parameter_factory_uses_explicit_fixture_inputs_not_native_observations():
    spec = verifier.fixture()
    before = copy.deepcopy(spec)
    values = verifier.recipe_parameters(spec)
    assert values == dict(units=spec["units"], termination=dict(endtim=50e-6), timestep=dict(tssfac=.8),
        hourglass=dict(ihq=6, qh=.03), energy=dict(hgen=2), d3plot=dict(dt=1e-6),
        ascii=dict(names=["glstat", "matsum", "rcforc"], dt=1e-7, binary=1))
    values["termination"]["endtim"] = 0
    assert spec == before
