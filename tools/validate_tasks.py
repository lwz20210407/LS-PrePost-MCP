"""I06: validate the sole planning source against the live MCP registry."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from task_catalog import read_catalog, registered_tools  # noqa: E402


def validate(catalog, tool_names):
    errors = []
    if not isinstance(catalog, dict):
        return ["catalog must be a mapping"]
    for field in ("schema_version", "tasks", "milestones", "infrastructure", "decisions", "status_values"):
        if field not in catalog:
            errors.append(f"missing catalog field: {field}")
    if errors:
        return errors
    ids = []
    for section in ("tasks", "infrastructure", "milestones"):
        if not isinstance(catalog[section], list):
            errors.append(f"{section} must be a list")
            continue
        for item in catalog[section]:
            required = {"id", "title", "milestone", "acceptance"}
            if section == "tasks":
                required |= {"group", "story", "ui_entry", "release", "layer", "target_tools", "status", "existing"}
            if section == "milestones":
                required = {"id", "name", "tasks", "infrastructure", "exit"}
            if not isinstance(item, dict):
                errors.append(f"{section}: entry must be a mapping")
                continue
            label = item.get("id", "<missing>")
            ids.append(label)
            for field in sorted(required - item.keys()):
                errors.append(f"{label}: missing {field}")
            for field in ("acceptance", "target_tools", "existing", "ui_entry", "depends_on", "tasks", "infrastructure", "exit"):
                if field in item and not isinstance(item[field], list):
                    errors.append(f"{label}: {field} must be a list")
            if section == "tasks" and item.get("status") not in catalog["status_values"]:
                errors.append(f"{label}: invalid status")
            if item.get("status") == "done" and not item.get("evidence"):
                errors.append(f"{label}: done requires evidence path")
    if len(ids) != len(set(ids)):
        errors.append("IDs must be globally unique")
    if errors:
        return errors
    task_ids = {x["id"] for x in catalog["tasks"]}
    infra_ids = {x["id"] for x in catalog["infrastructure"]}
    milestone_ids = {x["id"] for x in catalog["milestones"]}
    for section in ("tasks", "infrastructure"):
        for item in catalog[section]:
            label = item["id"]
            for dep in item.get("depends_on", []):
                if dep not in task_ids | infra_ids:
                    errors.append(f"{label}: unknown dependency {dep}")
            milestone = item.get("milestone")
            if milestone and any(m not in milestone_ids for m in milestone.split("-")):
                errors.append(f"{label}: unknown milestone {milestone}")
            for name in item.get("existing", []):
                if name not in tool_names:
                    errors.append(f"{label}: unregistered tool {name}")
    for milestone in catalog["milestones"]:
        for field, allowed in (("tasks", task_ids), ("infrastructure", infra_ids)):
            for ref in milestone[field]:
                if ref not in allowed:
                    errors.append(f"{milestone['id']}: invalid {field} reference {ref}")
        for task in catalog["tasks"]:
            if (task["id"] in milestone["tasks"]) != (task["milestone"] == milestone["id"]):
                errors.append(f"{task['id']}: inconsistent milestone membership")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path)
    args = parser.parse_args()
    errors = validate(read_catalog(args.catalog), registered_tools())
    if errors:
        print("\n".join(errors))
        return 1
    print("tasks.yaml: schema, IDs, references, evidence and registry OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
