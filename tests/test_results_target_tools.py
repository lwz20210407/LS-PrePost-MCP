"""Q06 extract_database target tool: JobResult/v1 over the shared binout / MPP-shard backend.

Shards are written with lasso's own LSDA writer (synthetic data, no network, no LS-PrePost), the
same way as tests/test_results_mpp_shards.py.
"""
import asyncio
import csv
import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("lasso.dyna")

from lasso.dyna.lsda_py3 import Lsda  # noqa: E402

from ls_prepost_mcp.config import Settings  # noqa: E402
from ls_prepost_mcp.core.contracts import JobResult  # noqa: E402
from ls_prepost_mcp.server import build_server  # noqa: E402
from ls_prepost_mcp.service import Service  # noqa: E402

# tasks.yaml Q06 acceptance: one case per database.
DATABASES = ["glstat", "matsum", "rcforc", "secforc", "nodout", "elout", "sleout", "nodfor",
             "spcforc", "rbdout", "ncforc", "deforc"]


def _shard(path: Path, database: str, times: list[float], *, ids: list[int] | None = None,
           branch: str | None = None, component: str = "x_force", scale: float = 1.0, first: int = 1,
           side: list[int] | None = None) -> None:
    """One database (or branch): component of entity i at time t is scale * t * (i + 1); a database
    written without ``ids`` is a scalar whose component at time t is scale * t."""
    f = Lsda(str(path), "w")
    root = f"/{database}" + (f"/{branch}" if branch else "")
    f.cd(root + "/metadata", 1)  # real binout always carries a metadata directory; lasso needs it to aggregate states
    f.write("date", Lsda.I1, [ord(c) for c in "synthetic"])
    if ids is not None:
        f.write("ids", Lsda.I4, ids)
    if side is not None:
        f.write("side", Lsda.I4, side)
    for k, t in enumerate(times, start=first):
        f.cd(f"{root}/d{k:06d}", 1)
        f.write("time", Lsda.R8, [t])
        values = [scale * t] if ids is None else [scale * t * (i + 1) for i in range(len(ids))]
        f.write(component, Lsda.R8, values)
    f.close()


def _valid(result: dict) -> JobResult:
    return JobResult.model_validate(json.loads(json.dumps(result)), strict=False)


def _service(tmp_path: Path) -> Service:
    return Service(Settings(tmp_path))


@pytest.mark.parametrize("database", DATABASES)
def test_each_database_is_read_by_component_name(tmp_path: Path, database: str) -> None:
    _shard(tmp_path / "binout0000", database, [0.0, 1.0, 2.0], ids=[11, 22])
    result = _valid(_service(tmp_path).extract_database(str(tmp_path / "binout0000"), database, "x_force", "N"))
    assert result.status == "succeeded" and result.backend.startswith("lasso-python")
    assert result.data["database"] == database and result.data["column_name"] == "x_force"
    assert result.data["units"] == "N" and result.data["ids"] == [11, 22]
    assert result.data["shards"] == ["binout0000"] and result.data["row_count"] == 6
    rows = _rows(result)
    assert rows[0] == ["time", "entity_id", "x_force"]
    assert [float(r[2]) for r in rows[1:] if int(r[1]) == 22] == pytest.approx([0.0, 2.0, 4.0])


def test_scalar_database_has_no_entity_axis(tmp_path: Path) -> None:
    _shard(tmp_path / "binout", "glstat", [0.0, 0.5, 1.0], component="kinetic_energy", scale=10.0)
    service = _service(tmp_path)
    result = _valid(service.extract_database(str(tmp_path / "binout"), "glstat", "kinetic_energy", "mJ"))
    assert result.status == "succeeded" and result.data["ids"] is None and result.data["entity_count"] == 0
    rows = _rows(result)
    assert rows[0] == ["time", "kinetic_energy"]
    assert [float(r[1]) for r in rows[1:]] == pytest.approx([0.0, 5.0, 10.0])
    # A scalar column rejects an entity selection instead of guessing one.
    rejected = _valid(service.extract_database(str(tmp_path / "binout"), "glstat", "kinetic_energy", "mJ",
                                               entity_ids=[1]))
    assert rejected.status == "failed" and "scalar" in rejected.error["message"]


def test_mpp_shards_are_merged_and_match_the_shared_backend(tmp_path: Path) -> None:
    _shard(tmp_path / "binout0000", "rcforc", [0.0, 0.1, 0.2, 0.3], ids=[2, 5])
    _shard(tmp_path / "binout0003", "rcforc", [0.4, 0.5], ids=[2, 5])
    result = _valid(_service(tmp_path).extract_database(str(tmp_path / "binout0000"), "rcforc", "x_force", "N"))
    assert result.status == "succeeded"
    assert result.data["shards"] == ["binout0000", "binout0003"]
    assert result.data["state_count"] == 6 and result.data["repeated_times_dropped"] == 0
    from ls_prepost_mcp.domain.results.lasso_backend import binout_curves
    backend = binout_curves(tmp_path / "binout0000", "rcforc", "x_force")
    times = [float(r[0]) for r in _rows(result)[1:] if int(r[1]) == 2]
    assert times == pytest.approx(backend["time"])


def test_entity_subselection_branch_and_single_shard(tmp_path: Path) -> None:
    _shard(tmp_path / "binout0000", "elout", [0.0, 1.0], ids=[11, 12, 13], branch="shell")
    _shard(tmp_path / "binout0001", "elout", [0.0, 1.0], ids=[99], branch="beam")
    service = _service(tmp_path)
    picked = _valid(service.extract_database(str(tmp_path / "binout0000"), "elout", "x_force", "N",
                                             branch="shell", entity_ids=[13, 11]))
    assert picked.status == "succeeded" and picked.data["ids"] == [13, 11]
    assert {int(r[1]) for r in _rows(picked)[1:]} == {11, 13}
    one = _valid(service.extract_database(str(tmp_path / "binout0000"), "elout", "x_force", "N",
                                          branch="beam", shard="binout0001"))
    assert one.status == "succeeded" and one.data["ids"] == [99] and one.data["shards"] == ["binout0001"]


def test_bad_requests_and_missing_component_fail_closed(tmp_path: Path) -> None:
    _shard(tmp_path / "binout0000", "secforc", [0.0, 1.0], ids=[1])
    service = _service(tmp_path)
    missing = _valid(service.extract_database(str(tmp_path / "binout0000"), "secforc", "nope", "N"))
    assert missing.status == "failed" and "nope" in missing.error["message"]
    bad_units = _valid(service.extract_database(str(tmp_path / "binout0000"), "secforc", "x_force", "  "))
    assert bad_units.status == "failed" and "unit" in bad_units.error["message"].lower()
    bad_id = _valid(service.extract_database(str(tmp_path / "binout0000"), "secforc", "x_force", "N",
                                             entity_ids=[7]))
    assert bad_id.status == "failed" and "7" in bad_id.error["message"]


def test_result_is_a_verified_csv_in_a_job_directory(tmp_path: Path) -> None:
    _shard(tmp_path / "binout0000", "nodfor", [0.0, 1.0], ids=[3, 4])
    result = _valid(_service(tmp_path).extract_database(str(tmp_path / "binout0000"), "nodfor", "x_force", "N"))
    assert result.status == "succeeded"
    artifact = result.artifacts[0]
    written = Path(artifact.path)
    assert artifact.verification == "verified"
    assert hashlib.sha256(written.read_bytes()).hexdigest() == artifact.sha256
    assert written.is_relative_to(tmp_path / "jobs" / result.job_id)
    job = json.loads((tmp_path / "jobs" / result.job_id / "job.json").read_text())
    assert job["status"] == "succeeded" and job["result"]["operation"] == "extract_database"


def test_repeated_ids_keep_both_rcforc_sides(tmp_path: Path) -> None:
    # RCFORC stores each interface twice under one ID: side 0 (secondary) and side 1 (main). An
    # ID-keyed map would write the main column twice and drop the secondary one.
    _shard(tmp_path / "binout0000", "rcforc", [0.0, 1.0, 2.0], ids=[2, 2, 7, 7], side=[0, 1, 0, 1])
    service = _service(tmp_path)
    result = _valid(service.extract_database(str(tmp_path / "binout0000"), "rcforc", "x_force", "N"))
    assert result.status == "succeeded"
    assert result.data["ids"] == [2, 2, 7, 7] and result.data["stored_columns"] == [0, 1, 2, 3]
    assert result.data["column_key"] == ["entity_id", "side"]
    rows = _rows(result)
    assert rows[0] == ["time", "entity_id", "side", "x_force"]
    at_two = {(int(r[1]), int(r[2])): float(r[3]) for r in rows[1:] if float(r[0]) == 2.0}
    # component of stored column i at time t is t * (i + 1)
    assert at_two == pytest.approx({(2, 0): 2.0, (2, 1): 4.0, (7, 0): 6.0, (7, 1): 8.0})
    picked = _valid(service.extract_database(str(tmp_path / "binout0000"), "rcforc", "x_force", "N",
                                             entity_ids=[7]))
    assert picked.status == "succeeded" and picked.data["stored_columns"] == [2, 3]
    assert {(int(r[1]), int(r[2])) for r in _rows(picked)[1:]} == {(7, 0), (7, 1)}


def test_repeated_ids_without_side_are_keyed_by_stored_column(tmp_path: Path) -> None:
    _shard(tmp_path / "binout0000", "deforc", [0.0, 1.0], ids=[5, 5])
    result = _valid(_service(tmp_path).extract_database(str(tmp_path / "binout0000"), "deforc", "x_force", "N"))
    assert result.status == "succeeded" and result.data["column_key"] == ["entity_id", "column"]
    rows = _rows(result)
    assert rows[0] == ["time", "entity_id", "column", "x_force"]
    assert {(int(r[2]), float(r[3])) for r in rows[1:] if float(r[0]) == 1.0} == {(0, 1.0), (1, 2.0)}


def test_glob_characters_in_the_path_never_read_another_folder(tmp_path: Path) -> None:
    # lasso globs the file name: case[1]/binout would match case1/binout. The tool must refuse
    # instead of returning the other folder's data as a verified CSV.
    (tmp_path / "case[1]").mkdir()
    (tmp_path / "case1").mkdir()
    _shard(tmp_path / "case[1]" / "binout", "glstat", [0.0, 1.0], component="kinetic_energy", scale=10.0)
    _shard(tmp_path / "case1" / "binout", "glstat", [0.0, 1.0], component="kinetic_energy", scale=999.0)
    result = _valid(_service(tmp_path).extract_database(str(tmp_path / "case[1]" / "binout"), "glstat",
                                                        "kinetic_energy", "mJ"))
    assert result.status == "failed" and "glob" in result.error["message"]
    assert not result.artifacts


def test_ascii_entry_is_not_swapped_for_a_binout_beside_it(tmp_path: Path) -> None:
    _shard(tmp_path / "binout", "glstat", [0.0, 1.0], component="kinetic_energy")
    (tmp_path / "glstat").write_text(" ascii glstat placeholder\n", encoding="utf-8")
    result = _valid(_service(tmp_path).extract_database(str(tmp_path / "glstat"), "glstat",
                                                        "kinetic_energy", "mJ"))
    assert result.status == "failed" and "binout" in result.error["message"]
    assert result.job_id is None


def test_a_linked_shard_outside_the_allowed_roots_is_refused(tmp_path: Path) -> None:
    workspace, outside = tmp_path / "ws", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    _shard(workspace / "binout0000", "rcforc", [0.0, 1.0], ids=[1])
    _shard(outside / "binout0001", "rcforc", [2.0, 3.0], ids=[1])
    try:
        (workspace / "binout0001").symlink_to(outside / "binout0001")
    except OSError:
        pytest.skip("symbolic links are not permitted on this host")
    result = _valid(Service(Settings(workspace)).extract_database(str(workspace / "binout0000"), "rcforc",
                                                                  "x_force", "N"))
    assert result.status == "failed" and "allowed roots" in result.error["message"]


def test_tool_is_registered_on_the_mcp_server(tmp_path: Path) -> None:
    names = {t.name for t in asyncio.run(build_server(Settings(tmp_path), "full").list_tools())}
    assert "extract_database" in names


def _rows(result: JobResult) -> list[list[str]]:
    with open(result.artifacts[0].path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))
