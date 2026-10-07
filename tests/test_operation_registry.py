import ast
import inspect
from pathlib import Path

import pytest

from ls_prepost_mcp.compact_server import CompactTools
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.operation_registry import OPERATIONS, bind_alias, resolve_operation
from ls_prepost_mcp.service import Service


def test_legacy_and_canonical_names_execute_the_same_typed_operation(tmp_path):
    compact = CompactTools(Service(Settings(tmp_path)))
    record = resolve_operation("compute_stress_invariants")
    args = dict(stresses=[[1., 2., 3., 0., 0., 0.]], units="Pa")
    legacy = compact.lspp_run_operation(record.name, args, "direct")
    canonical = compact.lspp_run_operation(record.operation_id, args, "direct")
    assert legacy == canonical
    assert legacy


def test_alias_keeps_signature_and_calls_original_once(tmp_path):
    service = Service(Settings(tmp_path))
    function = service.list_jobs
    alias = bind_alias(function, "list_jobs")
    assert inspect.signature(alias) == inspect.signature(function)
    assert alias.operation_id == resolve_operation("list_jobs").operation_id
    assert alias.legacy_until == "v0.6"
    assert alias(limit=1) == []
    with pytest.raises(TypeError):
        alias(invented=True)


def test_operation_discovery_and_workflow_planning_do_not_read_planning_files(tmp_path, monkeypatch):
    read_text = Path.read_text

    def guarded(path, *args, **kwargs):
        if path.name in ("development_plan.json", "tasks.yaml", "tool_migration_map.yaml"):
            pytest.fail("Runtime read a planning file")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    service = Service(Settings(tmp_path))
    compact = CompactTools(service)
    assert compact.lspp_find_operations("inspect_model")["operations"]
    result = service.create_workflow("file check", [dict(id="check", action="validate_model_references",
                                                         arguments=dict(model="model.k"))])
    assert result["status"] in ("succeeded", "prepared")
    assert service.inspect_workflow(result["artifacts"][0]["path"])


def test_no_function_local_service_import_remains():
    root = Path(inspect.getfile(Service)).parent
    offenders = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if isinstance(child, ast.ImportFrom) and child.module in ("service", "ls_prepost_mcp.service"):
                        offenders.append((path.name, child.lineno))
    assert offenders == []


def test_every_legacy_operation_has_a_unique_runtime_id_and_compatibility_period():
    assert len({r.operation_id for r in OPERATIONS}) == len(OPERATIONS)
    assert all((r.legacy_until == "v0.6" or r.legacy_until is None and r.name == r.target)
               and r.task_id and r.target for r in OPERATIONS)
    # legacy operations keep their alias until v0.6; the target tools themselves (name == target) have none
    assert {r.name for r in OPERATIONS if r.legacy_until is None} == {
        "run_script", "find_recipe", "run_recipe", "search_docs", "keyword_fields", "command_help",
        "model_info", "edit_keywords", "create_entities", "mesh_ops", "check_model", "curve_ops"}
    with pytest.raises(ValueError):
        resolve_operation("__dict__")


def test_batch_postprocess_receives_renderer_without_constructing_another_service(tmp_path, monkeypatch):
    source = tmp_path / "d3plot"
    source.write_bytes(b"input placeholder")
    service = Service(Settings(tmp_path))
    calls = []

    def runner(settings, jobs, path, units, *, renderer):
        calls.append((path, renderer.__self__, renderer.__func__))
        return dict(status="unverified")

    monkeypatch.setattr("ls_prepost_mcp.native_batch.run_case", runner)
    assert service.native_postprocess_case(str(source), "source_units")["status"] == "unverified"
    assert calls == [(source, service, Service.render_snapshot)]
