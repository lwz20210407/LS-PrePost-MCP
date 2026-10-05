"""I06: deterministic task/tool docs; --check never writes files."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from task_catalog import ROOT, owners, read_catalog, registered_tools  # noqa: E402
from validate_tasks import validate  # noqa: E402


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def marked(text, name, content):
    begin, end = f"<!-- {name}:begin -->", f"<!-- {name}:end -->"
    replacement = f"{begin}\n{content.rstrip()}\n{end}"
    if begin not in text and end not in text:
        return text.rstrip() + "\n\n" + replacement + "\n"
    if text.count(begin) != 1 or text.count(end) != 1 or text.index(begin) > text.index(end):
        raise ValueError(f"invalid {name} marker pair")
    return text[: text.index(begin)] + replacement + text[text.index(end) + len(end) :]


def generate(catalog, registry):
    task_lines = ["# 任务目录", "", "由 `tools/gen_docs.py` 从 `tasks.yaml` 生成，请修改源数据。", ""]
    labels = {"pre": "前处理", "post": "后处理", "auto": "自动化", "general": "通用"}
    for group, title in labels.items():
        task_lines += [f"## {title}", ""]
        for t in catalog["tasks"]:
            if t["group"] != group:
                continue
            task_lines += [
                f"### {t['id']} {t['title']}",
                "",
                f"状态：{t['status']}；版本：{t['release']}；里程碑：{t['milestone'] or '待排期'}；层：{t['layer']}",
                "",
                t["story"],
                "",
                "验收：",
                "",
            ]
            task_lines += [f"- {a}" for a in t["acceptance"]]
            task_lines += ["", "现有入口：" + (", ".join(f"`{n}`" for n in t["existing"]) or "无"), ""]
            if t.get("gaps"):
                task_lines += ["缺口：", ""] + [f"- {a}" for a in t["gaps"]] + [""]
    task_lines += ["## 基础设施", ""]
    for t in catalog["infrastructure"]:
        ownership = ["负责人：" + t["owner"], ""] if t.get("owner") else []
        integration = ["集成约束：" + t["integration"], ""] if t.get("integration") else []
        completion = (
            ["状态：" + t["status"] + "；验证：" + t.get("verification_level", "待记录"), ""]
            if t.get("status")
            else []
        )
        evidence = (
            ["证据：" + ", ".join(f"[{path}](../{path})" for path in t["evidence"]), ""]
            if t.get("evidence")
            else []
        )
        task_lines += (
            [f"### {t['id']} {t['title']}", "", f"里程碑：{t['milestone']}", ""]
            + ownership
            + integration
            + completion
            + evidence
            + [f"- {a}" for a in t["acceptance"]]
            + [""]
        )
    tool_lines = [
        "# 当前 MCP 工具",
        "",
        "由实际 full profile registry 生成。目标工具是迁移设计，不表示已经注册。未列入任务 existing 的工具标注基础设施迁移 I08。",
        "",
        "| 工具 | 所属任务 | 参数摘要（* 必填） |",
        "|---|---|---|",
    ]
    for name, tool in sorted(registry.items()):
        schema = tool.parameters
        params = [
            f"{key}{'*' if key in schema.get('required', []) else ''}: {v.get('type', 'union/ref')}"
            for key, v in schema.get("properties", {}).items()
        ]
        task_ids = ", ".join(t["id"] for t in owners(catalog, name)) or "I08"
        tool_lines.append(f"| `{name}` | {task_ids} | {cell('; '.join(params) or '无')} |")
    rows = ["| 类别 | 任务 | 当前状态 | 目标版本 |", "|---|---|---|---|"]
    for t in catalog["tasks"]:
        state = {"partial": "部分实现", "todo": "待实现", "done": "已验收"}[t["status"]]
        rows.append(f"| {labels[t['group']]} | {t['id']} {t['title']} | {state} | {t['release']} |")
    policy_rows = ["## 目标版本策略（自动生成）", "", "| 版本 | D3 验收策略 |", "|---|---|"]
    for clause in catalog["decisions"]["D3"].split("；"):
        version = re.search(r"\d+\.\d+", clause)
        if version:
            policy_rows.append(f"| {version[0]} | {clause.strip().rstrip('。')} |")
    policy = "\n".join(policy_rows) + "\n\n此表是验收目标；前文历史证据保留其原始范围。"
    return {
        ROOT / "docs/TASKS.md": "\n".join(task_lines).rstrip() + "\n",
        ROOT / "docs/TOOLS.md": "\n".join(tool_lines) + "\n",
        ROOT / "README.md": marked(
            (ROOT / "README.md").read_text(encoding="utf-8"), "tasks", "\n".join(rows)
        ),
        ROOT / "docs/COMPATIBILITY.md": marked(
            (ROOT / "docs/COMPATIBILITY.md").read_text(encoding="utf-8"), "versions", policy
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    catalog, registry = read_catalog(), registered_tools()
    errors = validate(catalog, registry)
    if errors:
        raise SystemExit("\n".join(errors))
    stale = []
    for path, content in generate(catalog, registry).items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            stale.append(path.relative_to(ROOT).as_posix())
            if not args.check:
                path.write_text(content, encoding="utf-8", newline="\n")
    if args.check and stale:
        raise SystemExit("stale generated docs: " + ", ".join(stale))
    print("generated docs: OK" if args.check else "generated docs updated")


if __name__ == "__main__":
    main()
