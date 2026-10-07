"""Q01 result_info: JobResult/v1 overview on the shared LASSO reader, opt-in LS-PrePost cross-check."""
import asyncio
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.server import build_server
from ls_prepost_mcp.service import Service

pytest.importorskip("lasso")
from lasso.dyna import ArrayType, D3plot  # noqa: E402

CUBE = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
TIMES = [0.0, 1.0e-3, 2.0e-3]


def _write(folder: Path, deletion: bool = True) -> Path:
    """Two solids (IDs 10, 20) in parts 1 and 2; element 20 deleted in the last of three states."""
    folder.mkdir(parents=True, exist_ok=True)
    coords = np.vstack([CUBE, CUBE + [0, 0, 1]])
    plot = D3plot()
    a = plot.arrays
    a[ArrayType.node_coordinates] = coords
    a[ArrayType.node_ids] = np.arange(1, 17)
    a[ArrayType.element_solid_node_indexes] = np.array([np.arange(8), np.arange(8, 16)])
    a[ArrayType.element_solid_part_indexes] = np.array([0, 1])
    a[ArrayType.element_solid_ids] = np.array([10, 20])
    a[ArrayType.part_titles_ids] = np.array([1, 2])
    a[ArrayType.part_titles] = np.array([b"lower".ljust(72), b"upper".ljust(72)])
    a[ArrayType.global_timesteps] = np.array(TIMES)
    a[ArrayType.node_displacement] = np.repeat(coords[None], 3, axis=0)
    a[ArrayType.element_solid_stress] = np.zeros((3, 2, 1, 6))
    if deletion:
        a[ArrayType.element_solid_is_alive] = np.array([[1, 1], [1, 1], [1, 0]], dtype=float)
    plot.write_d3plot(str(folder / "d3plot"))
    (folder / "glstat").write_text("ascii glstat placeholder\n")
    return folder / "d3plot"


@pytest.fixture()
def service(tmp_path: Path) -> Service:
    _write(tmp_path / "run")
    return Service(Settings(tmp_path))


def _valid(result: dict) -> JobResult:
    return JobResult.model_validate(json.loads(json.dumps(result)), strict=False)


def _native(states: int, times: list[float], status: str = "succeeded") -> dict:
    job = {"job_id": "native-job", "status": status, "executable": {"path": "lsprepost"},
           "data": {"counts": {"nodes": 16, "elements": 2, "states": states}, "state_times": times}}
    if status != "succeeded":
        job.update(data=None, error={"type": "RuntimeError", "message": "native crashed"})
    return job


def test_overview_fields_and_job_record(service: Service, tmp_path: Path) -> None:
    result = _valid(service.result_info("run/d3plot"))
    assert result.status == "succeeded" and result.backend == "lasso" and result.check_status == "passed"
    data = result.data
    assert data["states"] == 3 and data["state_index_base"] == 1
    assert data["times"] == pytest.approx(TIMES) and data["time_range"] == pytest.approx([0.0, 2.0e-3])
    assert data["elements"]["solid"]["count"] == 2 and data["elements"]["solid"]["deleted_at_last_state"] == 1
    assert data["elements"]["solid"]["history_variables"] == 0
    assert data["elements"]["solid"]["header_extra_values_per_point"] == data["header"]["neiph_solid"] == 0
    assert data["parts"] == [{"id": 1, "title": "lower"}, {"id": 2, "title": "upper"}]
    assert "element_solid_stress" in data["variables"] and data["ascii_files"] == ["glstat"]
    assert data["binout"] == {"files": [], "databases": [], "entries": {}, "split_over_shards": {}}
    assert {c.name: c.status for c in result.checks} == {"lasso_overview": "passed", "backends_agree": "not_applicable"}
    record = json.loads((tmp_path / "jobs" / result.job_id / "job.json").read_text(encoding="utf-8"))
    assert record["status"] == "succeeded" and record["result"]["data"]["states"] == 3


def test_missing_deletion_data_is_null_not_zero(tmp_path: Path) -> None:
    _write(tmp_path / "run", deletion=False)
    result = _valid(Service(Settings(tmp_path)).result_info("run/d3plot"))
    assert result.status == "succeeded" and result.data["elements"]["solid"]["deleted_at_last_state"] is None
    assert any("no element deletion data" in w for w in result.warnings)


def test_native_check_agrees(service: Service, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(service, "inspect_model", lambda path, file_type: calls.append((path, file_type))
                        or _native(3, [t * (1 + 1e-8) for t in TIMES]))
    result = _valid(service.result_info("run/d3plot", native_check=True))
    assert calls == [("run/d3plot", "d3plot")]
    assert result.status == "succeeded" and result.backend == "lasso+lsprepost"
    assert {c.name: c.status for c in result.checks}["backends_agree"] == "passed"
    comparison = result.data["comparison"]
    assert comparison["state_counts_equal"] and comparison["times_equal"]
    assert result.data["lsprepost"]["job_id"] == "native-job"


@pytest.mark.parametrize("states, times", [(2, TIMES[:2]), (3, [0.0, 1.0e-3, 2.1e-3])])
def test_native_check_reports_disagreement(service: Service, monkeypatch: pytest.MonkeyPatch, states, times) -> None:
    monkeypatch.setattr(service, "inspect_model", lambda path, file_type: _native(states, times))
    result = _valid(service.result_info("run/d3plot", native_check=True))
    assert result.status == "succeeded" and result.check_status == "failed"
    assert not (result.data["comparison"]["state_counts_equal"] and result.data["comparison"]["times_equal"])


def test_native_failure_is_partial_not_hidden(service: Service, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "inspect_model", lambda path, file_type: _native(0, [], status="failed"))
    result = _valid(service.result_info("run/d3plot", native_check=True))
    assert result.status == "partial" and "native crashed" in result.error["message"]
    assert {c.name: c.status for c in result.checks}["backends_agree"] == "missing"
    assert result.data["states"] == 3


def test_unconfigured_native_backend_is_partial(service: Service) -> None:
    result = _valid(service.result_info("run/d3plot", native_check=True))
    assert result.status == "partial" and result.error["message"]
    assert result.data["lsprepost"] == {"status": "failed", "job_id": None}


def test_unreadable_result_fails_with_error(service: Service, tmp_path: Path) -> None:
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "d3plot").write_bytes(b"not a d3plot")
    result = _valid(service.result_info("bad/d3plot"))
    assert result.status == "failed" and result.error["message"]
    with pytest.raises(ValueError, match="native_check"):
        service.result_info("run/d3plot", native_check="yes")


def test_registered_as_target_tool(service: Service) -> None:
    names = {t.name for t in asyncio.run(build_server(service.settings, "full").list_tools())}
    assert {"result_info", "inspect_d3plot_database", "inspect_d3plot_scl", "inspect_binout"} <= names


CORPUS = os.environ.get("LSPP_CORPUS_DIR")
MPP_CASE = "public-results/hu-shuhan__editOpeniGame/test/Format Validation Test/lsdyna/Bolt_B_Explicit"


@pytest.mark.skipif(not CORPUS or not (Path(CORPUS or ".") / MPP_CASE).is_dir(), reason="LSPP_CORPUS_DIR case absent")
def test_corpus_mpp_shards_and_ascii(tmp_path: Path) -> None:
    folder = Path(CORPUS) / MPP_CASE
    result = _valid(Service(Settings(tmp_path, allowed_roots=(folder,))).result_info(str(folder / "d3plot")))
    assert result.status == "succeeded", result.error
    assert result.data["states"] == 102 and len(result.data["times"]) == 102
    assert result.data["binout"]["files"] == ["binout0000", "binout0004", "binout0005", "binout0007"]
    assert {"glstat", "nodout", "matsum"} <= set(result.data["binout"]["databases"])
    assert "glstat" in result.data["ascii_files"]
