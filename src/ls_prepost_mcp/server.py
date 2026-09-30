"""Standard MCP stdio entrypoint; service construction has no native side effects."""
from mcp.server.fastmcp import FastMCP

from .config import Settings
from .knowledge import list_capabilities, search_commands, search_knowledge, search_workflows
from .service import Service


def build_server(settings: Settings | None = None) -> FastMCP:
    service = Service(settings or Settings.from_env())
    server = FastMCP("LS-PrePost-MCP")
    for name in ("list_installations", "run_on_version", "probe_environment", "probe_scl", "inspect_model", "list_nodes", "list_parts", "get_element_connectivity",
                 "create_shell_plate", "export_keyword", "extract_nodal_results", "extract_node_history",
                 "render_snapshot", "measure_parts", "read_job", "list_jobs", "inspect_binout", "extract_binout_curve",
                 "inspect_d3plot_scl", "inspect_d3plot_database", "extract_d3plot_nodal", "inspect_keyword_deck",
                 "create_elastic_material", "update_elastic_material", "inspect_lsreader", "extract_lsreader_nodal"):
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
