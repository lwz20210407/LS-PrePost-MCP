"""M3 target tools on the keyword engine: JobResult/v1 results, job-directory outputs, MCP registration."""
import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.server import build_server
from ls_prepost_mcp.service import Service

pytest.importorskip("ansys.dyna.core")

TOOLS = ("model_info", "edit_keywords", "create_entities", "mesh_ops", "check_model")
CORNERS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]


def _deck(root: Path) -> Path:
    lines = ["*KEYWORD", "*NODE"]
    lines += [f"{i + 1:>8}{float(x):>16}{float(y):>16}{float(z):>16}" for i, (x, y, z) in enumerate(CORNERS)]
    lines += ["*ELEMENT_SOLID", f"{1:>8}{1:>8}" + "".join(f"{n:>8}" for n in range(1, 9)),
              "*PART", "cube", f"{1:>10}{1:>10}{1:>10}",
              "*SECTION_SOLID", f"{1:>10}{1:>10}",
              "*MAT_ELASTIC", f"{1:>10}{7.8e-9:>10}{210000.0:>10}{0.3:>10}", "*END"]
    path = root / "cube.k"
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.fixture()
def service(tmp_path: Path) -> Service:
    _deck(tmp_path)
    return Service(Settings(tmp_path))


def _valid(result: dict) -> JobResult:
    return JobResult.model_validate(json.loads(json.dumps(result)), strict=False)


def test_model_info_and_check_model(service: Service) -> None:
    info = _valid(service.model_info("cube.k"))
    assert info.status == "succeeded" and info.backend == "keyword-engine"
    assert info.data["elements"]["*ELEMENT_SOLID"] == 1
    checked = _valid(service.check_model("cube.k"))
    assert checked.status == "succeeded" and checked.check_status == "passed"


def test_check_model_reports_defects_as_checks(service: Service, tmp_path: Path) -> None:
    text = (tmp_path / "cube.k").read_text().replace(f"{1:>10}{1:>10}{1:>10}", f"{1:>10}{9:>10}{1:>10}")
    (tmp_path / "broken.k").write_text(text)  # part 1 now refers to section 9, which does not exist
    checked = _valid(service.check_model("broken.k"))
    assert checked.status == "succeeded" and checked.check_status == "failed"
    assert {c.name for c in checked.checks} >= {"objective_defects", "defect:dangling_references"}


def test_edit_keywords_writes_a_verified_copy_and_keeps_the_input(service: Service, tmp_path: Path) -> None:
    before = (tmp_path / "cube.k").read_bytes()
    result = _valid(service.edit_keywords("cube.k", [
        {"op": "set", "keyword": "*MAT_ELASTIC", "field": "e", "value": 200000.0},
        {"op": "add_material", "units": "mm-t-s", "recipe": "elastic", "params": {"ro": 2.7e-9, "e": 70000.0, "pr": 0.33}},
    ]))
    assert result.status == "succeeded" and result.check_status == "passed"
    assert (tmp_path / "cube.k").read_bytes() == before
    artifact = result.artifacts[0]
    written = Path(artifact.path)
    assert artifact.verification == "verified" and hashlib.sha256(written.read_bytes()).hexdigest() == artifact.sha256
    assert written.is_relative_to(tmp_path / "jobs" / result.job_id)
    assert "200000.0" in written.read_text()
    job = json.loads((tmp_path / "jobs" / result.job_id / "job.json").read_text())
    assert job["status"] == "succeeded" and job["result"]["operation"] == "edit_keywords"


def test_scoped_tools_and_selectors(service: Service) -> None:
    top = {"entity_type": "node", "predicate": {"kind": "plane", "origin": [0, 0, 1], "normal": [0, 0, 1],
                                                 "tolerance": 1e-9}}
    created = _valid(service.create_entities("cube.k", [
        {"op": "add_boundary", "kind": "spc", "units": "mm-t-s", "dofs": "all", "target": {"selector": top}}]))
    assert created.status == "succeeded"
    moved = _valid(service.mesh_ops("cube.k", [{"op": "transform_nodes", "translate": [0, 0, 1.0], "selector": top}]))
    assert moved.status == "succeeded" and moved.data["summaries"][0]["nodes"] == 4
    control = _valid(service.edit_keywords("cube.k", [{"op": "set_control", "recipe": "termination",
                                                       "params": {"endtim": 1e-3}}]))
    assert control.status == "succeeded" and "*CONTROL_TERMINATION" in Path(control.artifacts[0].path).read_text()
    with pytest.raises(ValueError, match="does not run"):
        service.mesh_ops("cube.k", [{"op": "add_material", "units": "mm-t-s", "recipe": "elastic", "params": {}}])


def test_failed_edits_return_failed_results_and_write_nothing(service: Service, tmp_path: Path) -> None:
    result = _valid(service.edit_keywords("cube.k", [{"op": "set", "keyword": "*MAT_ELASTIC", "field": "nope",
                                                      "value": 1.0}]))
    assert result.status == "failed" and result.error["message"]
    assert not list((tmp_path / "jobs" / result.job_id).glob("deck/*"))


def test_wrongly_typed_values_return_failed_results(service: Service, tmp_path: Path) -> None:
    # e.g. "4.77e8" sent as a string: a failed JobResult, not an exception through the MCP layer
    result = _valid(service.edit_keywords("cube.k", [
        {"op": "add_material", "units": "mm-t-s", "recipe": "elastic", "params": {"ro": "2.7e-9", "e": 1.0, "pr": 0.3}}]))
    assert result.status == "failed" and "TypeError" in result.error["message"]
    assert not list((tmp_path / "jobs" / result.job_id).glob("deck/*"))


def test_tools_are_registered_on_the_mcp_server(service: Service) -> None:
    names = {t.name for t in asyncio.run(build_server(service.settings, "full").list_tools())}
    assert set(TOOLS) <= names
