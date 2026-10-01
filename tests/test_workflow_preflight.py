import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.workflow_runtime import compile_workflow


def definition(*steps, **extra):
    return dict(schema_version=1, name="Preflight regression", steps=list(steps), **extra)


def step(ident, action="inspect_model", **arguments):
    return dict(id=ident, action=action, arguments=arguments)


@pytest.mark.parametrize(
    "bad",
    [
        step("later", model={"$param": "missing"}),
        step("later", model={"$artifact": "future"}),
        step("later", model={"$artifact": "first", "index": True}),
        step("later", model={"$result": "first", "path": [True]}),
        step("later", model={"$result": "later", "path": ["data"]}),
        step("later", model={"$unknown": "x"}),
        step("later", model="source.k", typo=1),
        step("later"),
        step("later", model=True),
        step("later", "select_gui_entities", entity_type="node"),
    ],
)
def test_later_errors_prevent_initial_open_and_all_operations(tmp_path, monkeypatch, bad):
    service = Service(Settings(tmp_path))
    calls = []
    monkeypatch.setattr(service, "_native", lambda *a, **kw: calls.append(a))
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(definition(step("first", model="source.k"), bad)))
    preview = service.inspect_workflow(str(path))
    assert not preview["ready"] and not preview["executed"]
    assert preview["errors"][0]["step_id"] == "later"
    with pytest.raises(ValueError, match="preflight"):
        service.run_workflow(str(path))
    assert not calls and not (tmp_path / "jobs").exists()


def test_preview_has_actual_module_routes_and_deferred_dependencies_without_native_access(tmp_path):
    service = Service(Settings(tmp_path))
    workflow = definition(
        step("select", "select_gui_entities", entity_type="solid", entity_ids=[101]),
        step(
            "stress",
            "extract_native_stress",
            element_type="solid",
            element_ids={"$result": "select", "path": ["verification", "selected_ids"]},
            states=[1, 2],
            integration_point="mid",
            units="MPa",
        ),
    )
    report = compile_workflow(service, workflow, session_id="not-a-live-session")
    assert report["ready"], report
    assert [s["module"] for s in report["steps"]] == ["selection", "results"]
    assert [s["route"] for s in report["steps"]] == ["session", "session_native"]
    assert report["steps"][1]["dependencies"] == ["select"]
    assert report["steps"][1]["deferred_bindings"][0]["argument_path"] == ["element_ids"]
    assert "session_liveness_and_model_state" in report["not_checked"]
    assert not list(tmp_path.iterdir())


def test_static_arguments_of_later_step_validate_before_recorded_initial_model(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    calls = []
    monkeypatch.setattr(service, "open_in_gui_session", lambda *a, **kw: calls.append("open"))
    path = tmp_path / "recipe.json"
    path.write_text(
        json.dumps(
            definition(
                step(
                    "bad",
                    "extract_node_history",
                    quantity="displacement",
                    node_ids=[True],
                    states=[1],
                    units="mm",
                ),
                initial_model="initial.k",
            )
        )
    )
    with pytest.raises(ValueError, match="preflight"):
        service.run_workflow(str(path), session_id="session")
    assert not calls and not (tmp_path / "jobs").exists()


@pytest.mark.parametrize(
    "action,arguments",
    [
        ("checkpoint", {"ignored": "formerly silently discarded"}),
        ("inspect_model", {"model": "different.k"}),
        ("inspect_model", {"file_type": "d3plot"}),
        ("extract_native_stress", {"path": "different.d3plot"}),
        ("select_gui_entities", {"session_id": "other"}),
    ],
)
def test_context_cannot_be_overridden_per_step(tmp_path, action, arguments):
    report = compile_workflow(
        Service(Settings(tmp_path)), definition(step("x", action, **arguments)), session_id="s"
    )
    assert not report["ready"]


def test_dynamic_type_is_rechecked_before_native_dispatch(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    calls = []
    monkeypatch.setattr(service, "gui_session_action", lambda *a: calls.append(a))
    monkeypatch.setattr(
        service, "select_gui_entities", lambda **kw: dict(status="succeeded", data={"ids": [True]})
    )
    recipe = service.create_workflow(
        "bad dynamic IDs",
        [
            step("select", "select_gui_entities"),
            step(
                "history",
                "extract_node_history",
                node_ids={"$result": "select", "path": ["data", "ids"]},
                states=[1],
                quantity="displacement",
                units="mm",
            ),
        ],
    )
    path = recipe["artifacts"][0]["path"]
    assert service.inspect_workflow(path, session_id="s")["ready"]
    result = service.run_workflow(path, session_id="s")
    assert result["status"] == "failed" and not calls
    assert result["data"]["completed_steps"] == 1
    assert result["data"]["failed_step"] == "history"
    assert Path(result["job_directory"], "preflight.json").is_file()


def test_all_shipped_recipes_have_valid_action_signatures(tmp_path):
    service = Service(Settings(tmp_path))
    root = Path(__file__).resolve().parents[1] / "examples/workflows"
    # Supply missing parameters from a deferred prior result to exercise signatures,
    # rather than inventing engineering values in this structural test.
    for path in root.glob("*.json"):
        workflow = json.loads(path.read_text())
        defaults = workflow.get("defaults", {})

        def unbound(value):
            if isinstance(value, dict):
                if "$param" in value and value["$param"] not in defaults:
                    return {"$result": "preflight_source", "path": ["data", value["$param"]]}
                return {k: unbound(v) for k, v in value.items()}
            return [unbound(v) for v in value] if isinstance(value, list) else value

        for item in workflow["steps"]:
            item["arguments"] = unbound(item.get("arguments", {}))
        workflow["steps"].insert(0, step("preflight_source", model="dummy.k"))
        # This source action runs against the GUI in GUI recipes.
        session_id = "s" if path.name.startswith("visible_gui") else None
        if session_id:
            workflow["steps"][0]["arguments"] = {}
        report = compile_workflow(service, workflow, session_id=session_id)
        # Unknown check parameters are intentionally not fabricated.
        assert all(
            "required argument" not in e["message"] and "unexpected keyword" not in e["message"]
            for e in report["errors"]
        ), (path.name, report)
