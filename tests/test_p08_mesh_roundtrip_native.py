"""Fake Service/jobs only: no native process and no schema SDK dependency."""
import copy
import hashlib
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import verify_p08_mesh_roundtrip as verifier


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf8")


@pytest.fixture
def native_case(tmp_path, monkeypatch):
    case = tmp_path / "case"
    case.mkdir()
    source, edited = case / "input.k", case / "edited.k"
    source.write_bytes(b"owned original")
    edited.write_bytes(b"owned edited")
    (case / "work/jobs").mkdir(parents=True)
    inputs, globals_ = {}, {}
    for version in ("4.13", "4.10"):
        folder = tmp_path / version
        folder.mkdir()
        exe, cfg, global_cfg = folder / "fake.exe", folder / "lsppconf", folder / "global.conf"
        exe.write_bytes(b"never executed")
        cfg.write_bytes(b"synthetic initialized preferences")
        cfg.chmod(stat.S_IREAD)
        global_cfg.write_bytes(b"passive global preferences")
        inputs[version] = dict(executable=str(exe), source=str(cfg), executable_sha256=verifier.shared.sha(exe),
                               source_sha256=verifier.shared.sha(cfg))
        globals_[version] = str(global_cfg)
    captured = {p: dict(captured_file_sha256=hashlib.sha256(b"admitted bridge").hexdigest())
                for p in verifier.BRIDGE_SOURCES.values()}
    monkeypatch.setattr(verifier, "source_identity", lambda *a, **kw: captured)
    monkeypatch.setattr(verifier, "require_installation", lambda *a, **kw: dict(version_source="file_version_resource"))
    monkeypatch.setattr(verifier, "require_capability", lambda *a: None)
    monkeypatch.setattr(verifier, "native_inventory", lambda *a: [], raising=False)
    context = SimpleNamespace(inputs=inputs, globals=globals_, calls=[], change=None, case=case,
                              reports=tmp_path / "reports", captured=captured)
    spec = verifier.case_spec("translate")
    observed = dict(nodes=copy.deepcopy(spec["expected"]["nodes"]),
        elements=[dict(type=e["kind"], id=e["id"], nodes=list(e["nodes"])) for e in spec["expected"]["elements"]],
        counts=dict(nodes=16, elements=2), part_ids=[13, 29], part_elements={"13": [11], "29": [22]})
    context.export_projection = copy.deepcopy(spec["expected"])
    context.real_snapshot = verifier.snapshot
    monkeypatch.setattr(verifier, "snapshot", lambda path: copy.deepcopy(context.export_projection))

    class FakeService:
        def __init__(self, settings):
            self.settings = settings
            self.jobs = SimpleNamespace(root=settings.workspace / "jobs", get=lambda uid: json.loads(
                (self.jobs.root / uid / "job.json").read_text(encoding="utf8")))
            self._native_context = SimpleNamespace(executor=None)

        def _native(self, action, parameters, *, model, graphics):
            assert action == "gui_mesh_state" and parameters == {} and model == str(edited) and graphics is False
            return self.job(action)

        def export_keyword(self, model):
            assert model == str(edited)
            return self.job("export_keyword")

        def job(self, action):
            context.calls.append(action)
            uid = ("1" if action == "gui_mesh_state" else "2") * 32
            directory = self.jobs.root / uid
            directory.mkdir()
            selected = next(row for row in verifier.profile_inputs_identity(inputs).values()
                            if row["executable_path"] == str(self.settings.executable))
            for name in verifier.BRIDGE_SOURCES:
                (directory / name).write_bytes(b"admitted bridge")
            (directory / "input_data").write_bytes(edited.read_bytes())
            request = dict(job_id=uid, action=action, file_type="keyword", job_directory=str(directory),
                           parameters={}, model=str(directory / "input_data"))
            process = dict(pid=1234, returncode=0, timed_out=False, graphics=False, launch_mode="c", process_isolation="windows_job",
                cwd=str(directory), argv=[selected["executable_path"], "c=commands.cfile", "-nographics"],
                configuration=dict(source=selected["source"], source_sha256=selected["configuration"]["sha256"], source_modified=False))
            manifest = dict(job_id=uid, action=action, status="succeeded", native_channel="embedded_python", execution_mode="nographics",
                executable=dict(path=selected["executable_path"], **selected["executable"]),
                input=dict(path=str(edited), sha256=verifier.shared.sha(edited)),
                engine_result=dict(job_id=uid, operation=action, backend="lsprepost", stage="execution", status="unverified",
                                   error=None, checks=[], data=process))
            result = dict(job_id=uid, status="succeeded", data=copy.deepcopy(observed), artifacts=[])
            if action == "export_keyword":
                output = directory / "model.k"
                output.write_bytes(b"synthetic retained projection")
                result["artifacts"] = [dict(path=str(output), kind="keyword", sha256=verifier.shared.sha(output))]
            manifest["artifacts"] = copy.deepcopy(result["artifacts"])
            write_json(directory / "request.json", request)
            write_json(directory / "job.json", manifest)
            if context.change:
                context.change(action, result, manifest, request, directory)
            return result

    monkeypatch.setattr(verifier, "Service", FakeService)
    context.prepared = dict(directory=case, source=source, edited=edited, spec=spec, source_bytes=source.read_bytes(),
        source_identity=verifier.shared._one_file(source), edited_identity=verifier.shared._one_file(edited))
    context.run = lambda: verifier.verify_native_case(context.prepared, {}, inputs, "4.13", globals_, context.reports)
    return context


@pytest.mark.parametrize("version", ["4.13", "4.10"])
def test_fake_native_case_runs_only_two_owned_roles(native_case, version):
    report = verifier.verify_native_case(native_case.prepared, {}, native_case.inputs, version, native_case.globals, native_case.reports)
    assert report["status"] == "passed_case" and report["L2_complete"] is False
    assert native_case.calls == ["gui_mesh_state", "export_keyword"]
    assert len(report["native_jobs"]) == 2
    assert (native_case.reports / "typed-result.json").is_file()


def test_caller_cannot_refill_expected_from_observed_geometry(native_case):
    native_case.prepared["spec"]["expected"]["nodes"][0][1] += .01
    with pytest.raises(ValueError, match="admitted handwritten fixture"):
        native_case.run()
    assert not native_case.calls and not native_case.reports.exists()


def test_failed_first_typed_api_never_exports(native_case):
    def change(action, result, *unused):
        result["status"] = "failed"
    native_case.change = change
    with pytest.raises(ValueError, match="Native API"):
        native_case.run()
    assert native_case.calls == ["gui_mesh_state"]
    assert (native_case.reports / "typed-result.json").is_file()


@pytest.mark.parametrize("failure", ["role", "exe", "uuid", "cwd", "bridge", "request", "request_action", "request_uuid", "request_cwd",
    "request_type", "request_model", "raw_tree", "stage", "input", "config", "rc_bool",
    "source", "private_config", "global", "global_disappears", "global_appears", "namespace", "edited", "third_job", "typed_projection", "live_process"])
def test_fatal_first_job_or_projection_stops_before_export(native_case, monkeypatch, failure):
    if failure == "global_appears":
        Path(native_case.globals["4.10"]).unlink()
    def change(action, result, manifest, request, directory):
        if failure == "role":
            manifest["action"] = "export_keyword"
        elif failure == "exe":
            manifest["executable"]["sha256"] = "0" * 64
        elif failure == "uuid":
            result["job_id"] = "3" * 32
        elif failure == "cwd":
            manifest["engine_result"]["data"]["cwd"] = str(native_case.case)
        elif failure == "bridge":
            (directory / "bridge.py").write_bytes(b"changed bridge")
        elif failure == "request":
            request["parameters"] = {"unexpected": True}
        elif failure.startswith("request_"):
            key, value = {"request_action": ("action", "inspect_model"), "request_uuid": ("job_id", "9" * 32),
                "request_cwd": ("job_directory", str(native_case.case)), "request_type": ("file_type", "d3plot"),
                "request_model": ("model", str(native_case.prepared["source"]))}[failure]
            request[key] = value
        elif failure == "raw_tree":
            request["raw_keyword_tree"] = True
        elif failure == "stage":
            (directory / "input_data").write_bytes(b"wrong staged input")
        elif failure == "input":
            manifest["input"]["sha256"] = "0" * 64
        elif failure == "config":
            manifest["engine_result"]["data"]["configuration"]["source_modified"] = True
        elif failure == "rc_bool":
            manifest["engine_result"]["data"]["returncode"] = False
        elif failure == "source":
            monkeypatch.setattr(verifier, "source_identity", lambda *a, **kw: (_ for _ in ()).throw(ValueError("changed source")))
        elif failure == "private_config":
            cfg = Path(native_case.inputs["4.10"]["source"])
            cfg.chmod(stat.S_IWRITE)
            cfg.write_bytes(b"changed private configuration")
            cfg.chmod(stat.S_IREAD)
        elif failure.startswith("global"):
            path = Path(native_case.globals["4.10"])
            if failure == "global_disappears":
                path.unlink()
            else:
                path.write_bytes(b"changed or newly appeared global preferences")
        elif failure == "namespace":
            (native_case.case / "unexpected.txt").write_bytes(b"outside work")
        elif failure == "edited":
            native_case.prepared["edited"].write_bytes(b"changed edited source")
        elif failure == "third_job":
            third = directory.parent / ("3" * 32)
            third.mkdir()
            extra = copy.deepcopy(manifest)
            extra["job_id"] = "3" * 32
            write_json(third / "job.json", extra)
        elif failure == "typed_projection":
            result["data"]["nodes"][0][1] += .01
        else:
            monkeypatch.setattr(verifier, "native_inventory", lambda *a: [dict(pid=1234, name="fake.exe")])
        write_json(directory / "job.json", manifest)
        write_json(directory / "request.json", request)
    native_case.change = change
    with pytest.raises((ValueError, FileNotFoundError)):
        native_case.run()
    assert native_case.calls == ["gui_mesh_state"]
    report = json.loads((native_case.reports / "native-proof.json").read_text(encoding="utf8"))
    assert report["status"] != "passed_case" and report["typed_geometry_verified"] is False
    assert report["overall_task_accepted"] is False and report["L2_complete"] is False
    if failure.startswith("global"):
        assert report["status"] == "needs_global_preference_investigation"


@pytest.mark.parametrize("failure", ["api", "duplicate_uuid", "artifact_path", "artifact_sha", "output_projection", "reference_projection", "first_job_tampered"])
def test_second_job_failure_or_wrong_output_never_claims_typed_verification(native_case, failure):
    expected = copy.deepcopy(native_case.prepared["spec"]["expected"])
    def change(action, result, manifest, request, directory):
        if action != "export_keyword":
            return
        if failure == "api":
            result["status"] = "failed"
        elif failure == "duplicate_uuid":
            result["job_id"] = "1" * 32
        elif failure == "artifact_path":
            result["artifacts"][0]["path"] = str(native_case.case / "wrong.k")
        elif failure == "artifact_sha":
            result["artifacts"][0]["sha256"] = "0" * 64
        elif failure == "output_projection":
            native_case.export_projection["nodes"][0][1] += .01
        elif failure == "reference_projection":
            native_case.export_projection["node_sets"].append(dict(id=999, members=[101]))
        else:
            (directory.parent / ("1" * 32) / "bridge.py").write_bytes(b"tampered first job")
    native_case.change = change
    with pytest.raises(ValueError):
        native_case.run()
    assert native_case.calls == ["gui_mesh_state", "export_keyword"]
    report = json.loads((native_case.reports / "native-proof.json").read_text(encoding="utf8"))
    assert report["status"] == "failed" and report["typed_geometry_verified"] is False
    assert native_case.prepared["spec"]["expected"] == expected


def test_environment_restored_and_reports_never_touch_input_namespace(native_case, monkeypatch):
    monkeypatch.setenv("LSPP_CONFIG_SOURCE", "original environment value")
    before = verifier._namespace(native_case.case)
    native_case.run()
    assert verifier.os.environ["LSPP_CONFIG_SOURCE"] == "original environment value"
    assert verifier._namespace(native_case.case) == before
    assert native_case.reports.parent == native_case.case.parent


def test_source_rejection_precedes_private_read_and_report_creation(native_case, monkeypatch):
    def refused(*a, **kw):
        raise ValueError("source refused")
    monkeypatch.setattr(verifier, "source_identity", refused)
    monkeypatch.setattr(verifier, "profile_inputs_identity", lambda *a: pytest.fail("private inputs read"))
    with pytest.raises(ValueError, match="source refused"):
        native_case.run()
    assert not native_case.reports.exists() and not native_case.calls


@pytest.mark.parametrize("when", ["before", "during"])
def test_private_mapping_file_sha_is_bound_before_and_after_call(native_case, when):
    path = native_case.case.parent / "profiles.json"
    path.write_bytes(b"admitted mapping bytes")
    expected = {str(path): verifier.shared.sha(path)}
    if when == "before":
        path.write_bytes(b"changed before verification")
    else:
        native_case.change = lambda *a: path.write_bytes(b"changed during native call")
    with pytest.raises(ValueError):
        verifier.verify_native_case(native_case.prepared, {}, native_case.inputs, "4.13", native_case.globals,
                                    native_case.reports, control_files=expected)
    assert native_case.calls == ([] if when == "before" else ["gui_mesh_state"])


def test_cli_explicit_optin_connects_only_the_one_case_plan(native_case, monkeypatch):
    base = native_case.case.parent
    monkeypatch.setattr(verifier, "ROOT", base / "checkout")
    monkeypatch.setattr(verifier, "execution_identity", lambda *a: {})
    profiles, globals_ = base / "profiles.json", base / "globals.json"
    write_json(profiles, native_case.inputs)
    write_json(globals_, native_case.globals)
    def prepare(path, case, identity):
        assert path == base / "output/case-translate" and case == "translate"
        return native_case.prepared
    monkeypatch.setattr(verifier, "prepare_case", prepare)
    verifier.main(["--output", str(base / "output"), "--case", "translate", "--expected-head", "a" * 40,
        "--expected-source-snapshot", "b" * 64, "--run-native", "--profile", "4.13", "--profiles", str(profiles),
        "--global-preferences", str(globals_)])
    assert native_case.calls == ["gui_mesh_state", "export_keyword"]
    report = json.loads((base / "output/reports/native-proof.json").read_text(encoding="utf8"))
    assert report["status"] == "passed_case" and report["typed_geometry_verified"] is True
    assert report["verified_scope"]["case"] == "translate"
    assert report["overall_task_accepted"] is False


@pytest.mark.parametrize("failure", ["reparse", "size", "read_limit", "missing_key"])
def test_global_preferences_admission_is_bounded_regular_and_explicit(native_case, monkeypatch, failure):
    if failure == "missing_key":
        native_case.globals.pop("4.10")
    elif failure == "read_limit":
        Path(native_case.globals["4.10"]).write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    else:
        target = Path(native_case.globals["4.10"])
        original = Path.lstat
        info = target.lstat()
        fake = SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400 if failure == "reparse" else 0,
                               st_size=info.st_size if failure == "reparse" else 11 * 1024 * 1024)
        monkeypatch.setattr(Path, "lstat", lambda path: fake if path == target else original(path))
    with pytest.raises(ValueError):
        native_case.run()
    assert not native_case.calls and not native_case.reports.exists()


def test_preexisting_native_process_blocks_without_starting_any_call(native_case, monkeypatch):
    monkeypatch.setattr(verifier, "native_inventory", lambda *a: [dict(pid=4567, name="fake.exe")])
    with pytest.raises(ValueError, match="Existing native processes"):
        native_case.run()
    assert not native_case.calls and not native_case.reports.exists()


def test_dangling_keyword_reference_is_rejected_by_existing_reader(native_case, monkeypatch):
    pytest.importorskip("ansys.dyna.core")
    monkeypatch.setattr(verifier, "snapshot", native_case.real_snapshot)
    def change(action, result, manifest, request, directory):
        if action != "export_keyword":
            return
        data = copy.deepcopy(native_case.prepared["spec"]["expected"])
        data["node_sets"].append(dict(id=999, members=[999999]))
        output = directory / "model.k"
        output.write_text(verifier.source_text(data), encoding="ascii")
        result["artifacts"][0]["sha256"] = verifier.shared.sha(output)
        manifest["artifacts"] = copy.deepcopy(result["artifacts"])
        write_json(directory / "job.json", manifest)
    native_case.change = change
    with pytest.raises(ValueError, match="reference coverage"):
        native_case.run()
    report = json.loads((native_case.reports / "native-proof.json").read_text(encoding="utf8"))
    assert report["typed_geometry_verified"] is False and report["status"] == "failed"


def test_process_inventory_is_passive_and_scoped_to_declared_binary_paths_names(monkeypatch):
    profiles = {"4.13": dict(executable_path=str(Path("primary.exe").absolute())),
                "4.10": dict(executable_path=str(Path("legacy.exe").absolute()))}
    records = [dict(pid=1, name="unrelated.exe", exe="unrelated.exe"), dict(pid=2, name="PRIMARY.EXE", exe=None),
               dict(pid=3, name="renamed", exe=profiles["4.10"]["executable_path"])]
    monkeypatch.setattr(verifier.psutil, "process_iter", lambda *a: [SimpleNamespace(info=r) for r in records])
    assert [row["pid"] for row in verifier.native_inventory(profiles)] == [2, 3]


@pytest.mark.parametrize("value", [r"\\server\share\x", "//server/share/x", r"\/server/share/x", r"\\?\C:\x", r"\\.\C:\x", "NUL"])
@pytest.mark.parametrize("entry", ["profiles", "global_preferences", "reports", "cli_output", "mapping_json"])
def test_unsafe_path_strings_are_refused_before_filesystem(native_case, monkeypatch, value, entry):
    if entry == "profiles":
        native_case.inputs["4.10"]["source"] = value
        def call():
            return verifier.profile_inputs_identity(native_case.inputs)
    elif entry == "global_preferences":
        native_case.globals["4.10"] = value
        def call():
            return verifier.global_preferences_identity(native_case.globals)
    elif entry == "reports":
        def call():
            return verifier.verify_native_case(native_case.prepared, {}, native_case.inputs, "4.13", native_case.globals, value)
    elif entry == "mapping_json":
        def call():
            return verifier._json_file(value)
    else:
        monkeypatch.setattr(verifier, "execution_identity", lambda *a: {})
        def call():
            return verifier.main(["--output", value, "--expected-head", "a" * 40, "--expected-source-snapshot", "b" * 64])
    def forbidden(*a, **kw):
        pytest.fail("unsafe path reached a filesystem method")
    with monkeypatch.context() as patch:
        for name in ("resolve", "stat", "lstat", "open", "mkdir"):
            patch.setattr(Path, name, forbidden)
        with pytest.raises(ValueError, match="Network and device"):
            call()
