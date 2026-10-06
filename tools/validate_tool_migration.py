"""M0-6/I08: exact migration coverage and valid target task names."""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from task_catalog import ROOT, read_catalog, registered_tools  # noqa: E402

from ls_prepost_mcp.operation_registry import migration_map  # noqa: E402


def main():
    catalog = read_catalog()
    mapping = yaml.safe_load((ROOT / "tools/tool_migration_map.yaml").read_text(encoding="utf-8"))["tools"]
    registry = registered_tools()
    ids = {t["id"] for t in catalog["tasks"] + catalog["infrastructure"]}
    targets = {name for t in catalog["tasks"] for name in t["target_tools"]}
    errors = []
    if mapping != migration_map():
        errors.append("migration map differs from the runtime registry; run tools/gen_docs.py")
    if set(mapping) != set(registry):
        errors.append(
            f"registry mismatch: missing={set(registry) - set(mapping)}, extra={set(mapping) - set(registry)}"
        )
    for name, entry in mapping.items():
        if entry.get("target") not in targets | {"recipe", "alias", "deprecate"}:
            errors.append(f"{name}: unknown target")
        if entry.get("task_id") not in ids:
            errors.append(f"{name}: unknown task_id")
        if entry.get("legacy_until") != "v0.6" and not (entry.get("legacy_until") is None and entry.get("target") == name):
            errors.append(f"{name}: missing compatibility period")  # target tools themselves have none
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"migration map: exactly {len(registry)} registered tools; targets and task IDs OK")


if __name__ == "__main__":
    main()
