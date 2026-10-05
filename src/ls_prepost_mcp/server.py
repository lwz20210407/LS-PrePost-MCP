"""Standard MCP stdio entrypoint; service construction has no native side effects."""
import os

from mcp.server.fastmcp import FastMCP

from . import knowledge
from .compact_server import CompactTools
from .config import Settings
from .operation_registry import KNOWLEDGE_TOOLS, bind_alias
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
        server.tool(name=name)(bind_alias(getattr(service, name), name))
    for name in KNOWLEDGE_TOOLS:
        server.tool(name=name)(bind_alias(getattr(knowledge, name), name))
    return server


def main():
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
