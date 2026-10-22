"""Q12 public tool contracts, artifact contents, source confinement and shared reads."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.domain.results import energy_readers, lasso_backend
from ls_prepost_mcp.domain.results.lasso_backend import MissingComponentError
from ls_prepost_mcp.service import Service


def ascii_case(folder):
    source = folder / "glstat"
    source.write_text("time.... 0\ntotal energy.... 100\ninternal energy.... 100\nexternal work.... 0\n"
                      "time.... 1\ntotal energy.... 100\ninternal energy.... 100\nexternal work.... 0\n",
                      encoding="ascii")
    (folder / "matsum").write_text("time = 0\nmat.#= 10 inten= 40\nhgeng= 1\nmat.#= 90 inten= 60\n"
                                  "time = 1\nmat.#= 10 inten= 40\nhgeng= 2\nmat.#= 90 inten= 60\n",
                                  encoding="ascii")
    return source


def test_ascii_tool_with_parts_is_json_safe_and_exports_blanks(tmp_path, monkeypatch):
    source = ascii_case(tmp_path)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}
    service = Service(Settings(tmp_path / "jobs", allowed_roots=(tmp_path,)))
    monkeypatch.setattr(service, "_native", lambda *a, **kw: pytest.fail("Energy reader launched native"))
    raw = service.check_energy(str(source), "J", residual_ratio_limit=.01)
    result = JobResult.model_validate_json(json.dumps(raw, allow_nan=False))
    assert result.status == "succeeded", raw
    assert result.data["passed"] is True
    assert set(result.data["parts"]) == {"10", "90"}
    assert result.data["parts"]["90"]["energy_budget"]["final_hourglass_energy"] is None
    assert result.data["parts"]["90"]["missing_samples"]["hourglass_energy"] == 2
    assert any("MATSUM part 90" in warning for warning in result.warnings)
    csv_path = next(Path(a.path) for a in result.artifacts if Path(a.path).name == "energy_balance.csv")
    with csv_path.open() as stream:
        rows = list(csv.DictReader(stream))
    assert all(row["hourglass_energy"] == "" for row in rows)
    assert len(result.artifacts) == 3
    assert all(a.verification == "verified" for a in result.artifacts)
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before} == before


def test_missing_external_work_cannot_pass_requested_balance(tmp_path):
    source = ascii_case(tmp_path)
    source.write_text(source.read_text().replace("external work.... 0\n", ""))
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    result = JobResult.model_validate_json(json.dumps(service.check_energy(str(source), "J", residual_ratio_limit=.01)))
    assert result.status == "partial"
    assert result.data["passed"] is None and result.data["verdict"] == "incomplete"
    assert any("external_work" in warning for warning in result.warnings)
    assert json.loads((service.jobs.root / result.job_id / "job.json").read_text())["status"] == "partial"


def test_bad_table_returns_failed_jobresult_and_failed_manifest(tmp_path):
    source = tmp_path / "energies.txt"
    source.write_text("0 1 2 3 4 5 6 7\n1 1 2 3 4 5 6 7\n")
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    result = JobResult.model_validate_json(json.dumps(service.check_energy(str(source), "J")))
    assert result.status == "failed" and "glstat" in result.error["message"]
    assert not result.artifacts
    assert json.loads((service.jobs.root / result.job_id / "job.json").read_text())["status"] == "failed"


def test_reader_uses_shared_interface_and_never_substitutes_nonstandard_file(tmp_path, monkeypatch):
    called = []

    def shared(path, database, component):
        called.append((Path(path).name, database, component))
        if component == "time":
            return dict(time=[0., 1.], values=[0., 1.], ids=None)
        if component == "internal_energy":
            return dict(time=[0., 1.], values=[20., 21.], ids=None)
        raise MissingComponentError("not recorded")

    monkeypatch.setattr(lasso_backend, "binout_curves", shared)
    standard, nonstandard = tmp_path / "binout", tmp_path / "binout_other"
    standard.touch()
    nonstandard.touch()
    data = energy_readers.read_binout_glstat(standard)
    assert data["internal_energy"] == [20., 21.] and called
    called.clear()
    with pytest.raises(ValueError, match="Nonstandard"):
        energy_readers.read_binout_glstat(nonstandard)
    with pytest.raises(ValueError, match="Nonstandard"):
        energy_readers.read_binout_matsum(nonstandard)
    assert not called


def test_non_missing_shared_reader_error_is_not_swallowed(tmp_path, monkeypatch):
    def shared(path, database, component):
        raise lasso_backend.ResultsError("source identity conflict")

    monkeypatch.setattr(lasso_backend, "binout_curves", shared)
    with pytest.raises(ValueError, match="identity conflict"):
        energy_readers.read_binout_glstat(tmp_path / "binout")


def test_ascii_matsum_outside_allowed_root_is_rejected(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = ascii_case(allowed)
    forbidden = tmp_path / "outside"
    forbidden.write_text("do not read")
    service = Service(Settings(tmp_path / "work", allowed_roots=(allowed,)))
    result = service.check_energy(str(source), "J", matsum_path=str(forbidden))
    assert result["status"] == "failed"
    assert not service.jobs.root.exists()


def test_synthetic_binout_parts_roundtrip_through_public_tool(tmp_path):
    pytest.importorskip("lasso.dyna")
    from lasso.dyna.lsda_py3 import Lsda

    source = tmp_path / "binout"
    out = Lsda(str(source), "w")
    for database in ("glstat", "matsum"):
        out.cd(f"/{database}/metadata", 1)
        out.write("date", Lsda.I1, [1])
        if database == "matsum":
            out.write("ids", Lsda.I4, [10, 90])
        for index in (1, 2):
            out.cd(f"/{database}/d{index:06d}", 1)
            out.write("time", Lsda.R8, [float(index - 1)])
            out.write("internal_energy", Lsda.R8, [100.] if database == "glstat" else [40., 60.])
            if database == "glstat":
                out.write("total_energy", Lsda.R8, [100.])
                out.write("external_work", Lsda.R8, [0.])
    out.close()
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    result = JobResult.model_validate_json(json.dumps(service.check_energy(str(source), "J", residual_ratio_limit=.01)))
    assert result.status == "succeeded", result.error
    assert result.data["parts"]["10"]["energy_budget"]["final_internal_energy"] == 40.
    assert result.data["parts"]["90"]["energy_budget"]["final_hourglass_energy"] is None
    assert len(result.artifacts) == 3
