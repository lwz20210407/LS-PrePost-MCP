from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.dpf_tools import source_family
from ls_prepost_mcp.service import Service


def test_family_gap_and_mpp_shards_are_rejected(tmp_path):
    for name in ("d3plot", "d3plot01", "d3plot03", "binout0000", "binout0001"):
        (tmp_path / name).write_bytes(b"synthetic")
    settings = Settings(tmp_path)
    with pytest.raises(ValueError, match="interior"):
        source_family(settings, str(tmp_path / "d3plot"), "d3plot")
    with pytest.raises(ValueError, match="base"):
        source_family(settings, str(tmp_path / "d3plot01"), "d3plot")
    with pytest.raises(ValueError, match="MPP"):
        source_family(settings, str(tmp_path / "binout0000"), "binout")


@pytest.mark.parametrize("arguments", [
    dict(result="stress"), dict(result="erosion_flag", states=[True]),
    dict(result="displacement", states=[1, 2]),
    dict(result="global_total_energy", entity_ids=[3]),
    dict(result="erosion_flag", states=[1], label_filter={"idtype": True}),
])
def test_invalid_requests_fail_before_jobs_or_process(tmp_path, arguments):
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError):
        service.export_dpf_result("missing", "d3plot", units="raw", **arguments)
    assert not (tmp_path / "jobs").exists()


def test_export_stages_family_and_does_not_touch_original(tmp_path, monkeypatch):
    from ls_prepost_mcp import dpf_tools

    source = tmp_path / "d3plot"
    source.write_bytes(b"unchanged")
    (tmp_path / "d3plot01").write_bytes(b"second")
    def worker(directory, request, timeout):
        assert request["path"] != str(source)
        assert Path(request["path"]).read_bytes() == b"unchanged"
        assert Path(request["path"]).with_name("d3plot01").read_bytes() == b"second"
        return dict(ok=True, data=dict(backend="dpf"), rows=[
            ["erosion_flag", 0, '{"time":1}', "Elemental", 1, 0., 91, 0, 1., "", ""]])
    monkeypatch.setattr(dpf_tools, "run_worker", worker)
    result = Service(Settings(tmp_path)).export_dpf_result(str(source), "d3plot", "erosion_flag", "1", [1])
    assert result["status"] == "succeeded" and result["data"]["backend"] == "dpf"
    assert result["artifacts"][0]["row_count"] == 1 and source.read_bytes() == b"unchanged"


def test_failure_never_publishes_verified_values(tmp_path, monkeypatch):
    from ls_prepost_mcp import dpf_tools

    source = tmp_path / "binout"
    source.write_bytes(b"synthetic")
    def missing(*args):
        raise ValueError("No compatible DPF Server")
    monkeypatch.setattr(dpf_tools, "run_worker", missing)
    result = Service(Settings(tmp_path)).inspect_dpf_results(str(source), "binout")
    assert result["status"] == "failed" and not result.get("artifacts")
