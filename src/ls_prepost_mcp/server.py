"""Standard MCP stdio entrypoint; service construction has no native side effects."""
from mcp.server.fastmcp import FastMCP

from .config import Settings
from .knowledge import list_capabilities, search_commands, search_knowledge, search_workflows
from .registry import SERVICE_TOOLS
from .service import Service


def build_server(settings: Settings | None = None) -> FastMCP:
    service = Service(settings or Settings.from_env())
    server = FastMCP("LS-PrePost-MCP")
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
