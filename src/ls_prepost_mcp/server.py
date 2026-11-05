"""Standard MCP stdio entrypoint; service construction has no native side effects."""
import os

from mcp.server.fastmcp import FastMCP

from . import knowledge
from .compact_server import CompactTools
from .config import Settings
from .knowledge_mcp import reference_tool
from .operation_registry import (
    KNOWLEDGE_TOOLS,
    MIGRATION_META_NAMESPACE,
    bind_alias,
    migration_description,
    migration_metadata,
)
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
            function = getattr(compact, name)
            server.tool(name=name)(reference_tool(function) if name == "lspp_run_operation" else function)
        return server
    for name in SERVICE_TOOLS:
        function = bind_alias(getattr(service, name), name)
        server.tool(name=name, description=migration_description(function, name),
                    meta={MIGRATION_META_NAMESPACE: migration_metadata(name)})(function)
    for name in KNOWLEDGE_TOOLS:
        function = bind_alias(getattr(knowledge, name), name)
        server.tool(name=name, description=migration_description(function, name),
                    meta={MIGRATION_META_NAMESPACE: migration_metadata(name)})(reference_tool(function))
    return server


def main():
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
