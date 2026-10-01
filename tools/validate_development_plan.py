"""Validate planning traceability without launching native software or reading private data."""

import ast
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/ls_prepost_mcp/data"


def read_json(name):
    return json.loads((DATA / name).read_text(encoding="utf8"))


def unique(items, label):
    counts = Counter(items)
    duplicates = [item for item, count in counts.items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate {label}: {duplicates}")
    return set(counts)


def validate():
    plan = read_json("development_plan.json")
    if plan["schema_version"] != 1:
        raise ValueError("Unsupported development-plan schema")
    sources = unique((item["id"] for item in read_json("sources.json")), "source IDs")
    tree = ast.parse((ROOT / "src/ls_prepost_mcp/registry.py").read_text(encoding="utf8"))
    registry = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "SERVICE_TOOLS" for t in node.targets)
    )
    tools = unique(registry, "registered service tools")
    backlog = (ROOT / plan["backlog_document"]).read_text(encoding="utf8")
    backlog_ids = set(re.findall(r"^\| ([A-H]\d{2}) \|", backlog, re.M))
    if not backlog_ids or not (ROOT / plan["architecture_document"]).is_file():
        raise ValueError("Architecture/backlog document is missing")
    families = unique((item["id"] for item in plan["source_families"]), "source families")
    module_ids = unique((item["id"] for item in plan["modules"]), "modules")
    workflow_ids = unique((item["id"] for item in plan["workflows"]), "workflows")
    milestone_ids = unique((item["id"] for item in plan["milestones"]), "milestones")
    mapped_sources = set()

    def require_subset(values, expected, label):
        unknown = set(values) - expected
        if unknown:
            raise ValueError(f"Unknown {label}: {sorted(unknown)}")

    def check_backlog(item):
        require_subset(item.get("backlog_ids", []), backlog_ids, "backlog references")

    for family in plan["source_families"]:
        require_subset(family["source_ids"], sources, "source references")
        if not family["remaining"] or not family["review_status"] or not family["conversion_status"]:
            raise ValueError("Source families need review, conversion and remaining-scope fields")
        mapped_sources.update(family["source_ids"])
        check_backlog(family)
    if mapped_sources != sources:
        raise ValueError(f"Unassigned source records: {sorted(sources - mapped_sources)}")
    assigned = []
    for module in plan["modules"]:
        require_subset(module["source_families"], families, "module source families")
        require_subset(module["current_tools"], tools, "module service tools")
        check_backlog(module)
        assigned.extend(module["current_tools"])
        if not (ROOT / module["contract_doc"]).is_file():
            raise ValueError("Module contract document missing")
    if unique(assigned, "tool module ownership") != tools:
        raise ValueError(f"Unassigned service tools: {sorted(tools - set(assigned))}")
    knowledge = ast.parse((ROOT / "src/ls_prepost_mcp/knowledge.py").read_text(encoding="utf8"))
    knowledge_functions = {n.name for n in knowledge.body if isinstance(n, ast.FunctionDef)}
    require_subset(plan["knowledge_tools"], knowledge_functions, "knowledge tools")
    for workflow in plan["workflows"]:
        require_subset(workflow["modules"], module_ids, "workflow modules")
        require_subset(workflow["sources"], families, "workflow sources")
        require_subset(workflow["next_backlog"], backlog_ids, "workflow backlog")
        if not workflow["acceptance"] or not (ROOT / workflow["current_evidence"]).is_file():
            raise ValueError("Workflow needs exit criteria and current evidence document")
    for milestone in plan["milestones"]:
        require_subset(milestone["workflow_ids"], workflow_ids, "milestone workflows")
        check_backlog(milestone)
        if not milestone["exit_criteria"]:
            raise ValueError("Milestone lacks exit criteria")
    require_subset([plan["current_milestone"], plan["next_milestone"]], milestone_ids, "active milestones")
    tasks = {item["id"]: item for item in plan["work_items"]}
    unique((item["id"] for item in plan["work_items"]), "work items")
    for item in tasks.values():
        require_subset(item["modules"], module_ids, "work-item modules")
        require_subset(item["depends_on"], set(tasks), "work-item dependencies")
        require_subset([item["milestone"]], milestone_ids, "work-item milestones")
        check_backlog(item)
        if not item["acceptance"]:
            raise ValueError("Work item lacks acceptance criteria")
    done = set()

    def visit(key, active):
        if key in active:
            raise ValueError("Cycle in implementation dependencies: " + key)
        if key in done:
            return
        for dep in tasks[key]["depends_on"]:
            visit(dep, active | {key})
        done.add(key)

    for key in tasks:
        visit(key, set())
    capabilities = read_json("capabilities.json")["capabilities"]
    for capability in capabilities:
        require_subset(capability.get("sources", []), sources, "capability sources")
    return dict(
        source_records=len(sources),
        source_families=len(families),
        service_tools=len(tools),
        knowledge_tools=len(plan["knowledge_tools"]),
        modules=len(module_ids),
        workflows=len(workflow_ids),
        backlog_items=len(backlog_ids),
        work_items=len(tasks),
        note="Traceability validation only; not native or feature-completeness certification",
    )


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
