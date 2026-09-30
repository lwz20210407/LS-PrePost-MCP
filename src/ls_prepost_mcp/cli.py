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
            "inspect_d3plot_scl", "inspect_d3plot_database", "extract_d3plot_nodal", "inspect_keyword_deck",
            "create_elastic_material", "update_elastic_material", "inspect_lsreader", "extract_lsreader_nodal",
            "compute_stress_invariants", "inspect_result_fields", "extract_d3plot_field", "extract_d3plot_stress",
            "inspect_binout_variable", "extract_binout_table", "extract_ascii_curve", "process_curve",
            "extract_native_fields", "extract_native_stress", "extract_native_ascii_curve",
            "extract_native_binout_curve", "native_postprocess_case",
            "validate_model_references", "create_node_set_by_box", "create_tensile_shell_plate",
            "create_solid_box", "translate_mesh_nodes", "move_elements_to_part", "extrude_shell_part",
            "list_pydyna_keywords", "describe_pydyna_keyword", "compose_keyword_deck",
            "update_keyword_fields", "update_keyword_table_row"
        }:
            parser.error("Unknown action")
        result = getattr(service, args.action)(**params)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if isinstance(result, dict) and result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
