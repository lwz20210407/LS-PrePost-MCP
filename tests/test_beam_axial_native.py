"""Q05 limited named DataCenter reference; product native_check remains unsupported."""
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.engine.environment import locate_config
from ls_prepost_mcp.native import commands as nc
from ls_prepost_mcp.native_results import stage
from ls_prepost_mcp.runner import run_batch
from ls_prepost_mcp.service import Service
from tests.test_save_model_native import installation as installation
from tools.fetch_corpus import entries, load_registry, plain_path, resolve
from tools.public_corpus_preflight import directory_snapshot

pytestmark = pytest.mark.native
REFERENCE = Path(__file__).parent / "native_scripts/beam_axial_reference.py"
CASES = [
    ("beamip", "result.open-lasso-python__lasso-python.test.test_data.d3plot_beamip", 1, 2, [1], {
        "d3plot": "6e045d3ea76de5457fd60098ef7bd60d1f55203e12f2725c86ee6ac9b80c80dc",
        "d3plot01": "3f5d768404a1de38fb063a2c30b98b3ffb9e335797fdbb441639025b80fbb9f9"}),
    ("ansys-beam", "result.ansys__example-data.result_files.d3plot_beam", 544, 12, [2312, 1769], {
        "d3plot": "ca50ba77db99a8e9325365a9660b021858ff90dc541b06a749c5c0661ce51ace",
        "d3plot01": "ee705bda637b907eb512cb69cc9d9021510b5037a315d7c6644e4faeb243d9de",
        "d3plot02": "c0b83ebf3e593f0ac4074de462652f612305218c3ea5a561313b6bd99308ae23"}),
]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_directory_bytes(paths):
    """Byte protection beyond the result family, including small adjacent metadata."""
    directories = {path.parent for path in paths}
    result = {}
    for directory in directories:
        for current, folders, files in os.walk(directory, followlinks=False):
            for name in [*folders, *files]:
                path = Path(current) / name
                if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
                    raise ValueError("Reference corpus directory must not contain links")
            for name in files:
                path = Path(current) / name
                result[path] = sha(path)
    return result


@pytest.mark.parametrize("label,corpus_id,beam_count,state_count,entity_ids,expected_family", CASES,
                         ids=["beamip", "ansys-beam"])
def test_beam_axial_named_reference(installation, pytestconfig, label, corpus_id, beam_count,
                                    state_count, entity_ids, expected_family):
    executable, binary, config_sha = installation
    if binary["version"] != "4.13":
        pytest.fail("This limited named beam reference is registered only for explicit 4.13 runs")
    if label != "beamip" and not getattr(pytestconfig, "_beam_axial_reference_seed_passed", False):
        pytest.skip("The two-state beamip reference must pass before the larger named reference")
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        unavailable = pytest.fail if pytestconfig.getoption("--native-strict") else pytest.skip
        unavailable("Set LSPP_CORPUS_DIR for the two registered small public beam sources")
    corpus = plain_path(Path(location))
    source = plain_path(resolve(entries(load_registry())[corpus_id], corpus)) / "d3plot"
    root = pytestconfig._native_root / label
    root.mkdir()
    service = Service(Settings(root, executable, (corpus,), timeout=60))
    config = locate_config(executable, os.environ)
    assert config is not None and sha(config) == config_sha
    with service._guard():
        family = service._result_family(str(source))
        original = {path.name: sha(path) for path in family}
        assert original == expected_family
        listing = directory_snapshot(family)
        directory_bytes = source_directory_bytes(family)
    identity = pytestconfig._native_identity
    proof = dict(actual_git_revision=identity["actual_git_head"], working_tree_dirty=identity["working_tree_dirty"],
        git_diff_sha256=identity["git_diff_sha256"], git_diff_scope=identity["git_diff_scope"],
        corpus_id=corpus_id, executable=binary, source_config_sha256=config_sha,
        reference_script_sha256=sha(REFERENCE), field="axial_force", entity_ids=entity_ids,
        requested_states=list(range(1, state_count + 1)), graphics=False,
        ipt="binding default; semantics not independently identified", this_test_uses_product_native_check=False,
        native_executed=False, status="failed", original_family_sha256=original)
    try:
        with service._guard():
            stage(service.settings, source, root, family=True)
        staged = {name: sha(root / name) for name in original}
        assert staged == original
        proof["staged_family_sha256"] = staged
        expected = service.extract_history(str(source), "beam", "axial_force", entity_ids,
            units="caller_force_units", time_units="caller_time_units", native_check=False)
        assert expected["status"] == "succeeded", expected.get("error")
        curves = {}
        for artifact in expected["artifacts"]:
            with Path(artifact["path"]).open(newline="", encoding="utf8") as stream:
                rows = list(csv.DictReader(stream))
            values = np.asarray([float(row["value"]) for row in rows])
            assert len(values) == state_count
            curves[artifact["metadata"]["entity_id"]] = dict(
                time=np.asarray([float(row["time"]) for row in rows]), values=values)
        assert set(curves) == set(entity_ids)
        assert any(np.any(curve["values"] != 0) for curve in curves.values())
        (root / "expected-plan.json").write_text(json.dumps(dict(beam_count=beam_count,
            state_count=state_count, states=proof["requested_states"], entity_ids=entity_ids)), encoding="utf8")
        shutil.copyfile(REFERENCE, root / "reference.py")
        assert sha(root / "reference.py") == proof["reference_script_sha256"]
        nc.write_cfile(root / "commands.cfile", ["new", nc.open_model("d3plot", "d3plot", openc=True),
            nc.run_script("reference.py", "python"), "exit"])
        execution = run_batch(executable, root / "commands.cfile", root, timeout=60, graphics=False,
                              operation="q05_beam_axial_named_reference")
        proof["native_executed"] = execution.data.get("pid") is not None
        (root / "engine-result.json").write_text(execution.model_dump_json(), encoding="utf8")
        assert execution.status == "unverified" and execution.error is None, execution.error
        marker = json.loads((root / "native-beam-marker.json").read_text(encoding="utf8"))
        proof["marker"] = marker
        assert marker["complete"] and marker["rows"] == state_count * len(entity_ids)
        with (root / "native-beam.csv").open(newline="", encoding="utf8") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == state_count * len(entity_ids)
        seen, errors, time_error = set(), {uid: 0. for uid in entity_ids}, 0.
        atol = {uid: 1e-6 * float(np.max(np.abs(curve["values"]))) for uid, curve in curves.items()}
        for row in rows:
            state, uid = int(row["state"]), int(row["entity_id"])
            value, time = float(row["axial_force"]), float(row["time"])
            assert (state, uid) not in seen and uid in curves and 1 <= state <= state_count
            seen.add((state, uid))
            wanted_time, wanted_value = curves[uid]["time"][state - 1], curves[uid]["values"][state - 1]
            assert np.isfinite(value) and np.isfinite(time)
            assert np.isclose(time, wanted_time, rtol=1e-6, atol=0)
            assert np.isclose(value, wanted_value, rtol=2e-5, atol=atol[uid]), (state, uid, value, wanted_value)
            errors[uid] = max(errors[uid], abs(value - float(wanted_value)))
            time_error = max(time_error, abs(time - float(wanted_time)))
        assert seen == {(state, uid) for state in proof["requested_states"] for uid in entity_ids}
        proof.update(status="passed", total_samples=len(rows), max_absolute_error_by_id=errors,
            max_time_absolute_error=time_error, value_atol_by_id=atol,
            tolerances=dict(time_rtol=1e-6, time_atol=0., value_rtol=2e-5,
                            value_atol_rule="1e-6*reference curve peak; zero curve atol=0"),
            native_csv_sha256=sha(root / "native-beam.csv"))
    except Exception as error:
        proof["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        guards = {
            "input_family_unchanged": lambda: {p.name: sha(p) for p in service._result_family(str(source))} == original,
            "source_directory_unchanged": lambda: directory_snapshot(family) == listing
                and source_directory_bytes(family) == directory_bytes,
            "staged_family_unchanged": lambda: all((root / name).is_file() and sha(root / name) == value
                                                  for name, value in original.items()),
            "configuration_unchanged": lambda: sha(config) == config_sha,
            "binary_unchanged": lambda: sha(executable) == binary["sha256"],
        }
        for name, check in guards.items():
            try:
                if name in {"input_family_unchanged", "source_directory_unchanged", "staged_family_unchanged"}:
                    with service._guard():
                        proof[name] = bool(check())
                else:
                    # Installation/config identities are explicit host inputs,
                    # outside the model-file confinement used above.
                    proof[name] = bool(check())
            except Exception as guard_error:
                proof[name] = False
                proof.setdefault("guard_errors", {})[name] = str(guard_error)
        if not all(proof[key] for key in guards):
            proof["status"] = "failed"
        (root / "comparison.json").write_text(json.dumps(proof, separators=(",", ":")) + "\n", encoding="utf8")
        if "error" not in proof:
            assert all(proof[key] for key in guards)
    if label == "beamip":
        pytestconfig._beam_axial_reference_seed_passed = True
