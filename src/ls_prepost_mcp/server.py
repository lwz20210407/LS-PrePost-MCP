"""Standard MCP stdio entrypoint; service construction has no native side effects."""
import os

from mcp.server.fastmcp import FastMCP

from .compact_server import CompactTools
from .config import Settings
from .knowledge import list_capabilities, search_commands, search_knowledge, search_workflows
from .registry import SERVICE_TOOLS
from .service import Service


def build_server(settings: Settings | None = None, tool_profile: str | None = None) -> FastMCP:
    profile = tool_profile or os.environ.get("LSPP_TOOL_PROFILE", "full")
    if profile not in ("full", "compact"):
        raise ValueError("LSPP_TOOL_PROFILE must be full or compact")
    service = Service(settings or Settings.from_env())
    server = FastMCP("LS-PrePost-MCP")
    if profile == "compact":
        compact = CompactTools(service)
        for name in ("lspp_find_operations", "lspp_describe_operation", "lspp_run_operation"):
            server.tool(name=name)(getattr(compact, name))
        return server
    for name in SERVICE_TOOLS:
        server.tool(name=name)(getattr(service, name))
    server.tool()(search_knowledge)
    server.tool()(list_capabilities)
    server.tool()(search_commands)
    server.tool()(search_workflows)
    return server


def main():
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
