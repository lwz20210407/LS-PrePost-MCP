"""Run L3 agent scenarios (tasks.yaml I09) and write results.json and summary.md.

Examples (from the repository root, inside the project environment):
    uv run --no-sync python tools/run_l3.py --agent oracle --domain pre --out <dir>
    uv run --no-sync python tools/run_l3.py --agent claude --domain pre --out <dir>
    uv run --no-sync python tools/run_l3.py --agent codex --scenario pre02_material_fields --out <dir>

Each scenario runs in a fresh workspace under ``<out>/<agent>/<scenario>/workspace``. Success means
every check passed on the final workspace state; the agent's own report is not trusted. The CLI
agents call real language models: network access, their own login and their usage limits apply.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.l3 import AGENTS, Context, grade, load_all  # noqa: E402
from tools.l3.agents import PREAMBLE  # noqa: E402
from tools.l3.scenario import Scenario, Workspace  # noqa: E402


def run_one(scenario: Scenario, agent: str, out: Path, profile: str = "full", command: str | None = None,
            model: str | None = None, attempt: int = 1, bare: bool = False) -> dict:
    folder = out / agent / (scenario.id if attempt == 1 else f"{scenario.id}.{attempt}")
    workspace = Workspace.create(folder / "workspace", scenario)
    options = {} if agent == "oracle" else {"command": command or agent, "model": model, "bare": bare}
    run = AGENTS[agent](scenario, workspace, profile, **options)
    checks = grade(Context(workspace, answer=run.answer), scenario.checks)
    failed = [c for c in checks if not c["ok"]]
    final = workspace.final_deck()
    result = {
        "scenario": scenario.id, "task_ids": scenario.task_ids, "agent": agent, "profile": profile, "model": model,
        "bare": bare, "preamble": None if agent == "oracle" else PREAMBLE,
        "attempt": attempt, "success": not failed, "checks": checks,
        "failure": failed[0]["check"] + ": " + failed[0]["detail"] if failed else None,
        "run_error": run.error, "mcp_tool_calls": run.mcp_calls, "other_tool_calls": run.other_calls,
        "tools": [c["tool"] for c in run.tool_calls], "failed_tool_calls": sum(1 for c in run.tool_calls if not c["ok"]),
        "turns": run.turns, "duration_s": run.duration_s, "cost_usd": run.cost_usd,
        "final_deck": str(final.relative_to(workspace.root)) if final else None,
        "answer": run.answer[-4000:], "transcript": run.transcript,
    }
    (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def summary(results: list[dict]) -> str:
    passed = sum(r["success"] for r in results)
    lines = [f"# L3 results ({time.strftime('%Y-%m-%d %H:%M')})", "",
             f"Success: {passed}/{len(results)}", "",
             "| Scenario | Agent | Success | MCP calls | Failed calls | Other tools | Turns | Time (s) | Failure |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        reason = (r["failure"] or "").replace("|", "/")[:160]
        if r["run_error"]:
            reason = (reason + " (run: " + r["run_error"].replace("|", "/")[:120] + ")").strip()
        lines.append(f"| {r['scenario']} | {r['agent']} | {'yes' if r['success'] else 'no'} | {r['mcp_tool_calls']} | "
                     f"{r['failed_tool_calls']} | {r['other_tool_calls']} | {r['turns'] if r['turns'] is not None else ''} | "
                     f"{r['duration_s']} | {reason} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", choices=sorted(AGENTS), required=True)
    parser.add_argument("--out", type=Path, required=True, help="empty or new directory outside the repository")
    parser.add_argument("--domain", choices=["pre", "post", "auto"])
    parser.add_argument("--scenario", action="append", default=[], help="scenario ID (repeatable)")
    parser.add_argument("--profile", choices=["full", "compact"], default="full")
    parser.add_argument("--command", help="CLI executable for claude/codex (default: the agent name on PATH)")
    parser.add_argument("--model", help="model passed to the CLI agent")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--bare", action="store_true",
                        help="claude --bare: no user memory/skills/hooks; needs ANTHROPIC_API_KEY")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if out.is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error("--out must be outside the repository")
    results = []
    for scenario in load_all(args.domain, tuple(args.scenario)):
        for attempt in range(1, args.repeat + 1):
            result = run_one(scenario, args.agent, out, args.profile, args.command, args.model, attempt, args.bare)
            results.append(result)
            print(f"{scenario.id} [{args.agent}] {'PASS' if result['success'] else 'FAIL'}"
                  f" calls={result['mcp_tool_calls']} {result['failure'] or ''}", flush=True)
    (out / args.agent).mkdir(parents=True, exist_ok=True)
    (out / args.agent / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / args.agent / "summary.md").write_text(summary(results), encoding="utf-8")
    print(f"{sum(r['success'] for r in results)}/{len(results)} succeeded; {out / args.agent / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
