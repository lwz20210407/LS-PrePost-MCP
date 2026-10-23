"""Review02 Q01: failed native jobs are not malformed observations; large clocks are artifacts."""
import hashlib
import json

import pytest

from ls_prepost_mcp.domain.results import lasso_backend as lb
from tests.test_result_overview_validity import service as service


def test_failed_native_job_keeps_execution_diagnostic_without_observation_noise(service, monkeypatch):
    monkeypatch.setattr(service, "inspect_model", lambda *a: dict(status="failed", job_id="native-failed",
        data={"state_times": [float("nan")]}, error={"message": "native process crashed"}))
    result = service.result_info("d3plot", native_check=True)
    assert result["status"] == "partial" and "native process crashed" in result["error"]["message"]
    assert "observation_errors" not in result["data"]["lsprepost"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("native_check", [False, True])
def test_long_reader_and_native_clocks_move_to_a_verified_artifact(service, monkeypatch, native_check):
    previous = lb.overview
    times = [i * .001 for i in range(10001)]
    monkeypatch.setattr(lb, "overview", lambda path: {**previous(path), "states": len(times), "times": times,
                                                    "time_range": [times[0], times[-1]]})
    monkeypatch.setattr(service, "inspect_model", lambda *a: dict(status="succeeded", job_id="native",
        data={"counts": {"states": len(times)}, "state_times": times}))
    result = service.result_info("d3plot", native_check=native_check)
    assert result["status"] == "succeeded"
    assert result["data"]["times"] is None and result["data"]["times_storage"] == "artifact"
    artifact, = result["artifacts"]
    output = service.settings.input_path(artifact["path"])
    assert hashlib.sha256(output.read_bytes()).hexdigest() == artifact["sha256"]
    full = json.loads(output.read_text(encoding="utf8"))
    assert full["reader_times"] == times and full["state_index_base"] == 1
    if native_check:
        assert full["native_times"] == times and result["data"]["lsprepost"]["times"] is None
        assert result["data"]["comparison"]["times_equal"]
    assert len(json.dumps(result)) < 20000


def test_time_artifact_write_failure_returns_a_bounded_failed_job(service, monkeypatch):
    import ls_prepost_mcp.result_overview as module

    previous = lb.overview
    monkeypatch.setattr(lb, "overview", lambda path: {**previous(path), "times": [0.] * 10001, "states": 10001})
    write = module.atomic_json

    def fail_artifact(path, payload):
        if path.name == "state-times.json":
            raise OSError("owned artifact cannot be written")
        return write(path, payload)

    monkeypatch.setattr(module, "atomic_json", fail_artifact)
    result = service.result_info("d3plot", native_check=False)
    assert result["status"] == "failed" and "cannot be written" in result["error"]["message"]
    assert result["data"]["times"] is None and not result["artifacts"]
