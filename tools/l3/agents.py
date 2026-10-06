"""Agents that attempt an L3 scenario: the reference solution (oracle), Claude Code and Codex CLI.

Every agent works in a fresh workspace and talks to the MCP server named ``lspp`` started with
``LSPP_WORKSPACE`` set to that workspace. The CLI agents get only the MCP tools where the CLI allows
it (Claude: built-in tools disabled); calls to any other tool are counted and reported.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .scenario import Scenario, Workspace

SERVER = "lspp"
PREAMBLE = "你已连接 LS-PrePost MCP 服务器 lspp，请用它的工具完成下面的任务。\n\n"


@dataclass
class Run:
    agent: str
    answer: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # {"tool", "ok", "mcp"}
    turns: int | None = None
    duration_s: float = 0.0
    cost_usd: float | None = None
    error: str | None = None
    transcript: str | None = None

    @property
    def mcp_calls(self) -> int:
        return sum(1 for c in self.tool_calls if c["mcp"])

    @property
    def other_calls(self) -> int:
        return sum(1 for c in self.tool_calls if not c["mcp"])


def server_env(workspace: Workspace, profile: str) -> dict[str, str]:
    env = {"LSPP_WORKSPACE": str(workspace.root), "LSPP_TOOL_PROFILE": profile}
    for name in ("LSPP_EXECUTABLE", "LSPP_EXECUTABLES", "LSPP_TIMEOUT", "LSPP_DPF_PATH"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    return env


def _payload(result: object) -> object:
    """JSON payload of a FastMCP ``call_tool`` result (content blocks, optionally with structured data)."""
    blocks = result[0] if isinstance(result, tuple) else result
    texts = [getattr(b, "text", "") for b in blocks]
    try:
        return json.loads("".join(texts))
    except ValueError:
        return "".join(texts)


def _fill(value: object, last: str | None) -> object:
    if isinstance(value, str) and "{last}" in value:
        if last is None:
            raise ValueError("{last} used before any step wrote a deck")
        return value.replace("{last}", last)
    if isinstance(value, dict):
        return {k: _fill(v, last) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, last) for v in value]
    return value


def run_oracle(scenario: Scenario, workspace: Workspace, profile: str = "full") -> Run:
    """Replay the reference tool calls in-process through the MCP server (no language model)."""
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.server import build_server

    run, start, last = Run("oracle", answer=scenario.oracle_answer), time.monotonic(), None
    server = build_server(Settings(workspace.root), profile)
    for step in scenario.oracle:
        try:
            payload = _payload(asyncio.run(server.call_tool(step.tool, _fill(step.args, last))))
        except Exception as error:  # noqa: BLE001 - recorded as a failed run
            run.tool_calls.append({"tool": step.tool, "ok": False, "mcp": True})
            run.error = f"{step.tool}: {type(error).__name__}: {error}"
            break
        ok = isinstance(payload, dict) and payload.get("status") == "succeeded"
        run.tool_calls.append({"tool": step.tool, "ok": ok, "mcp": True})
        if not ok:
            run.error = f"{step.tool} returned {str(payload)[:500]}"
            break
        main = (payload.get("data") or {}).get("main")
        last = str(Path(main).relative_to(workspace.root)) if main else last
    run.duration_s = round(time.monotonic() - start, 2)
    return run


def _mcp_config(workspace: Workspace, profile: str) -> dict:
    return {"command": sys.executable, "args": ["-m", "ls_prepost_mcp.server"], "env": server_env(workspace, profile)}


def parse_claude_stream(lines: list[str], run: Run) -> None:
    """Fill ``run`` from ``claude -p --output-format stream-json --verbose`` lines."""
    pending: dict[str, dict] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        content = (event.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_use":
                call = {"tool": block.get("name", ""), "ok": True,
                        "mcp": block.get("name", "").startswith(f"mcp__{SERVER}__")}
                pending[block.get("id", "")] = call
                run.tool_calls.append(call)
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                pending[block["tool_use_id"]]["ok"] = not block.get("is_error", False)
        if event.get("type") == "result":
            run.answer = str(event.get("result") or "")
            run.turns = event.get("num_turns")
            run.cost_usd = event.get("total_cost_usd")
            if event.get("is_error") or event.get("subtype") not in (None, "success"):
                run.error = f"claude {event.get('subtype')}: {run.answer[:300]}"
    for call in run.tool_calls:
        call["tool"] = call["tool"].removeprefix(f"mcp__{SERVER}__")


def prompt(scenario: Scenario) -> str:
    """What the CLI agents receive: the same preamble (the user has configured the server), then the task."""
    return PREAMBLE + scenario.prompt


def run_claude(scenario: Scenario, workspace: Workspace, profile: str, command: str = "claude",
               model: str | None = None, bare: bool = False) -> Run:
    """``bare``: no user memory, skills, hooks or CLAUDE.md; needs ANTHROPIC_API_KEY (no OAuth login)."""
    config = workspace.root.parent / f"{workspace.root.name}.mcp.json"
    config.write_text(json.dumps({"mcpServers": {SERVER: _mcp_config(workspace, profile)}}), encoding="utf-8")
    args = [*resolve_command(command), "-p", prompt(scenario), "--output-format", "stream-json", "--verbose",
            "--mcp-config", str(config), "--strict-mcp-config", "--tools", "",
            "--allowedTools", f"mcp__{SERVER}", "--max-turns", str(scenario.limits.max_turns),
            "--no-session-persistence", "--setting-sources", ""]
    if bare:
        args.append("--bare")
    if model:
        args += ["--model", model]
    return _execute("claude", args, workspace, scenario, parse_claude_stream)


def parse_codex_stream(lines: list[str], run: Run) -> None:
    """Fill ``run`` from ``codex exec --json`` events (item.completed for tool calls and messages)."""
    messages = []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        item = event.get("item") or {}
        if event.get("type") != "item.completed":
            if event.get("type") in ("turn.failed", "error"):
                run.error = str(event.get("error") or event.get("message"))[:500]
            continue
        kind = item.get("type")
        if kind == "mcp_tool_call":
            run.tool_calls.append({"tool": item.get("tool", ""), "ok": item.get("status") == "completed"
                                   and not (item.get("error") or (item.get("result") or {}).get("is_error")),
                                   "mcp": item.get("server") == SERVER})
        elif kind in ("command_execution", "file_change", "web_search"):
            run.tool_calls.append({"tool": kind, "ok": item.get("status") != "failed", "mcp": False})
        elif kind == "agent_message":
            messages.append(str(item.get("text") or ""))
    run.answer = messages[-1] if messages else ""
    run.turns = len(messages) or None


def run_codex(scenario: Scenario, workspace: Workspace, profile: str, command: str = "codex",
              model: str | None = None, bare: bool = False) -> Run:
    """Read-only sandbox (files change only through the MCP server); the user's config.toml (other MCP
    servers, settings), apps and plugins are not loaded; ``bare`` has no further effect for Codex."""
    server = _mcp_config(workspace, profile)
    env_table = "{" + ",".join(f"{k}={json.dumps(v)}" for k, v in server["env"].items()) + "}"
    args = [*resolve_command(command), "exec", "--json", "--ephemeral", "--skip-git-repo-check", "-C", str(workspace.root),
            "--ignore-user-config", "--disable", "apps", "--disable", "plugins", "-s", "read-only",
            "-c", f"mcp_servers.{SERVER}.command={json.dumps(server['command'])}",
            "-c", f"mcp_servers.{SERVER}.args={json.dumps(server['args'])}",
            "-c", f"mcp_servers.{SERVER}.env={env_table}",
            "-c", f'mcp_servers.{SERVER}.default_tools_approval_mode="approve"',  # exec cannot ask
            "-c", f"mcp_servers.{SERVER}.startup_timeout_sec=120",
            "-c", f"mcp_servers.{SERVER}.tool_timeout_sec=600"]
    if model:
        args += ["-m", model]
    return _execute("codex", args + [prompt(scenario)], workspace, scenario, parse_codex_stream)


def resolve_command(command: str) -> list[str]:
    """Executable argv for ``command``; npm ``.cmd`` shims become ``node <script>`` (no cmd.exe quoting)."""
    path = shutil.which(command) or command
    if Path(path).suffix.lower() not in (".cmd", ".bat"):
        return [path]
    shim = Path(path).read_text(encoding="utf-8", errors="replace")
    match = re.search(r'%dp0%\\(node_modules\\[^"]+?\.js)', shim)
    node = shutil.which("node")
    if not match or not node:
        raise ValueError(f"{path} is a batch shim; pass the real executable instead")
    return [node, str(Path(path).parent / match.group(1))]


def _execute(agent: str, args: list[str], workspace: Workspace, scenario: Scenario, parse) -> Run:
    run, start = Run(agent), time.monotonic()
    transcript = workspace.root.parent / f"{workspace.root.name}.{agent}.jsonl"
    # a CLI started from inside a Claude Code session must not inherit that session's host variables
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_") and k != "CLAUDECODE"}
    try:
        done = subprocess.run(args, cwd=workspace.root, capture_output=True, text=True, encoding="utf-8", env=env,
                              errors="replace", timeout=scenario.limits.timeout_s, stdin=subprocess.DEVNULL)
        output, code, stderr = done.stdout, done.returncode, done.stderr
    except subprocess.TimeoutExpired as error:
        output = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else error.stdout or ""
        code, stderr, run.error = None, "", f"timeout after {scenario.limits.timeout_s} s"
    except OSError as error:
        output, code, stderr, run.error = "", None, "", f"{agent} could not start: {error}"
    transcript.write_text(output + ("\n" + stderr if stderr else ""), encoding="utf-8")
    run.transcript = str(transcript)
    parse(output.splitlines(), run)
    if code not in (0, None) and run.error is None:
        run.error = f"{agent} exited with {code}: {stderr.strip()[-500:]}"
    run.duration_s = round(time.monotonic() - start, 2)
    return run


AGENTS = {"oracle": run_oracle, "claude": run_claude, "codex": run_codex}

__all__ = ["AGENTS", "Run", "parse_claude_stream", "parse_codex_stream", "run_claude", "run_codex", "run_oracle",
           "server_env"]
