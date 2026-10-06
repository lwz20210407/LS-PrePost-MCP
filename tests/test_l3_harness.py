"""I09 L3 harness: scenarios are valid, solvable with the current tools (oracle) and graded strictly.

The language-model agents are not run here; their stream parsers are checked on recorded event shapes.
"""
import asyncio
import json
from pathlib import Path

import pytest
import yaml

from tools.l3 import CHECKS, Context, grade, load_all
from tools.l3.agents import Run, parse_claude_stream, parse_codex_stream, run_oracle
from tools.l3.fixtures import FIXTURES, fixture_texts
from tools.l3.scenario import OracleStep, Workspace

pytest.importorskip("ansys.dyna.core")

SCENARIOS = load_all()
IDS = [s.id for s in SCENARIOS]
ROOT = Path(__file__).resolve().parents[1]


def _solve(scenario, root: Path, oracle=None) -> tuple[Run, list[dict]]:
    workspace = Workspace.create(root, scenario)
    if oracle is not None:
        scenario = scenario.model_copy(update={"oracle": oracle})
    run = run_oracle(scenario, workspace)
    return run, grade(Context(workspace, answer=run.answer), scenario.checks)


def test_scenarios_reference_known_checks_tools_and_tasks() -> None:
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.server import build_server

    tasks = yaml.safe_load((ROOT / "tasks.yaml").read_text(encoding="utf-8"))
    known = {t["id"] for t in tasks["tasks"]} | {t["id"] for t in tasks["infrastructure"]}
    tools = {t.name for t in asyncio.run(build_server(Settings(ROOT), "full").list_tools())}
    assert len(SCENARIOS) >= 8 and len([s for s in SCENARIOS if s.domain == "pre"]) == 8
    for scenario in SCENARIOS:
        assert set(scenario.task_ids) <= known, scenario.id
        assert {c.check for c in scenario.checks} <= set(CHECKS), scenario.id
        assert {step.tool for step in scenario.oracle} <= tools, scenario.id
        assert scenario.oracle, f"{scenario.id} needs a reference solution"


def test_fixtures_are_reproducible() -> None:
    for name, text in fixture_texts().items():
        assert (FIXTURES / name).read_bytes() == text.encode("ascii"), name


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_reference_solution_passes_every_check(scenario, tmp_path: Path) -> None:
    run, checks = _solve(scenario, tmp_path / "ws")
    assert run.error is None, run.error
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_doing_nothing_fails(scenario, tmp_path: Path) -> None:
    workspace = Workspace.create(tmp_path / "ws", scenario)
    checks = grade(Context(workspace, answer=""), scenario.checks)
    assert not all(c["ok"] for c in checks)


def _replace(scenario_id: str, old: object, new: object) -> list[OracleStep]:
    """The reference steps with one value replaced (a typical unit mistake)."""
    steps = next(s for s in SCENARIOS if s.id == scenario_id).oracle
    text = json.dumps([s.model_dump() for s in steps]).replace(json.dumps(old), json.dumps(new))
    assert json.dumps(new) in text
    return [OracleStep.model_validate(s) for s in json.loads(text)]


@pytest.mark.parametrize("scenario_id, old, new", [
    ("pre02_material_fields", 70000.0, 70.0),  # GPa not converted to MPa
    ("pre03_jc_material", 4.57e6, 4570.0),  # m/s not converted to mm/s
    ("pre05_boundary_velocity", -1.0e5, -100.0),  # m/s not converted to mm/s
    ("pre07_mesh_array", 15.0, 10.0),  # wrong spacing
    ("pre08_check_and_controls", 2.0e-4, 0.2),  # ms not converted to s
])
def test_unit_and_value_mistakes_fail(scenario_id: str, old: object, new: object, tmp_path: Path) -> None:
    scenario = next(s for s in SCENARIOS if s.id == scenario_id)
    _, checks = _solve(scenario, tmp_path / "ws", _replace(scenario_id, old, new))
    assert not all(c["ok"] for c in checks)


def test_claude_stream_is_parsed() -> None:
    lines = [json.dumps(e) for e in (
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "mcp__lspp__model_info", "input": {}},
            {"type": "tool_use", "id": "b", "name": "Bash", "input": {}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a"},
                                                 {"type": "tool_result", "tool_use_id": "b", "is_error": True}]}},
        {"type": "result", "subtype": "success", "result": "two parts", "num_turns": 3, "total_cost_usd": 0.1},
    )] + ["not json"]
    run = Run("claude")
    parse_claude_stream(lines, run)
    assert (run.answer, run.turns, run.mcp_calls, run.other_calls) == ("two parts", 3, 1, 1)
    assert [c["tool"] for c in run.tool_calls] == ["model_info", "Bash"] and not run.tool_calls[1]["ok"]


def test_codex_stream_is_parsed() -> None:
    lines = [json.dumps(e) for e in (
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "lspp", "tool": "edit_keywords",
                                            "status": "completed"}},
        {"type": "item.completed", "item": {"type": "command_execution", "status": "completed"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}},
    )]
    run = Run("codex")
    parse_codex_stream(lines, run)
    assert (run.answer, run.mcp_calls, run.other_calls) == ("done", 1, 1)
