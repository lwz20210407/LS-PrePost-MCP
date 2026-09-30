"""CLI sharing the exact same service as MCP. Parameters are JSON, not shell code."""
import argparse
import json

from .config import Settings
from .knowledge import list_capabilities, search_knowledge
from .service import Service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action")
    parser.add_argument("--json", default="{}", help="JSON parameters")
    args = parser.parse_args()
    params = json.loads(args.json)
    if args.action == "capabilities":
        result = list_capabilities()
    elif args.action == "search":
        result = search_knowledge(**params)
    else:
        service = Service(Settings.from_env())
        if args.action.startswith("_") or args.action not in {
            "list_installations", "run_on_version", "probe_environment", "probe_scl", "inspect_model", "list_nodes", "list_parts", "get_element_connectivity",
            "create_shell_plate", "export_keyword", "extract_nodal_results", "extract_node_history",
            "render_snapshot", "measure_parts", "read_job", "list_jobs", "inspect_binout", "extract_binout_curve",
            "inspect_d3plot_database", "extract_d3plot_nodal", "inspect_keyword_deck",
            "create_elastic_material", "update_elastic_material", "inspect_lsreader", "extract_lsreader_nodal"
        }:
            parser.error("Unknown action")
        result = getattr(service, args.action)(**params)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if isinstance(result, dict) and result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
