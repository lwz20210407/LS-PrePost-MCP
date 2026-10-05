"""I06: build-time task catalog and actual MCP registry inspection (no native launch)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_catalog(path=None):
    return yaml.safe_load((path or ROOT / "tasks.yaml").read_text(encoding="utf-8"))


def registered_tools():
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.server import build_server

    # Server construction has no filesystem/native side effects. Read the actual
    # full MCP registration, including knowledge tools, instead of a second list.
    server = build_server(Settings(ROOT), tool_profile="full")
    return {tool.name: tool for tool in server._tool_manager.list_tools()}


def owners(catalog, name):
    return [task for task in catalog["tasks"] if name in task["existing"]]
