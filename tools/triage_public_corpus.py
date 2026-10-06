"""Summarize public-corpus failures without changing verdicts or inventing provenance."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def category(reason):
    """Preliminary symptom classification; not a diagnosis of the root cause."""
    if "No module named" in reason or re.search(r"(?m)^E\s+(?:ModuleNotFoundError|ImportError):", reason):
        return "dependency"
    if "Only plain *INCLUDE is supported" in reason:
        return "unsupported_include_variant"
    if "Native export of include-bearing models" in reason:
        return "legacy_include_export"
    if ("FileNotFoundError" in reason or "OSError" in reason) and "check_keyword_includes" in reason:
        return "missing_referenced_input"
    if "nonempty finite-element model" in reason:
        return "empty_native_model_needs_diagnosis"
    if "Empty *INCLUDE card" in reason or "Parameterized includes require" in reason:
        return "include_validation"
    if "state_count" in reason and "assert" in reason and "KeyError:" not in reason:
        return "backend_state_count_mismatch"
    if "Native batch failed" in reason and re.search(r"returncode=(?:-[1-9]\d*|[1-9]\d*)", reason):
        return "native_process_failure"
    if "allclose" in reason and "AssertionError" in reason:
        return "numerical_comparison"
    return "unclassified"


def summarize(report):
    report = Path(report).resolve(strict=True)
    data = json.loads(report.read_text(encoding="utf8"))
    context = data.get("execution_context")
    sidecar = report.parent / "execution-context.json"
    if context is None and sidecar.is_file():
        context = json.loads(sidecar.read_text(encoding="utf8"))
    context = context or {}
    rows = []
    for nodeid, row in data["cases"].items():
        if "test_public_corpus[" not in nodeid:
            continue
        match = re.search(r"\[([^]]+)\]$", nodeid)
        if not match:
            raise ValueError("Public-corpus case has no stable ID")
        status = row["status"]
        rows.append(dict(case=match[1], status=status,
                         triage=category(row.get("reason", "")) if status in ("failed", "error") else None))
    ids = {row["case"] for row in rows}
    if len(ids) != len(rows):
        raise ValueError("Duplicate public-corpus case IDs")
    preservation = Counter()
    seen_records = set()
    for path in report.parent.glob("*/public-case.json"):
        if not path.resolve().is_relative_to(report.parent):
            raise ValueError("Case evidence escapes the report directory")
        record = json.loads(path.read_text(encoding="utf8"))
        if record["case"] in ids:
            if record["case"] in seen_records:
                raise ValueError("Duplicate per-case preservation records")
            seen_records.add(record["case"])
            state = record.get("originals_unchanged")
            preservation["reported_unchanged" if state is True else "reported_changed" if state is False else "unknown"] += 1
    missing = []
    if not re.fullmatch(r"[0-9a-f]{40}", str(context.get("actual_git_head", ""))):
        missing.append("actual_git_head")
    if type(context.get("working_tree_dirty")) is not bool:
        missing.append("working_tree_dirty")
    if context.get("working_tree_dirty") is True and not re.fullmatch(r"[0-9a-f]{64}", str(context.get("git_diff_sha256", ""))):
        missing.append("git_diff_sha256")
    return dict(task="I04", report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
                actual_git_revision=context.get("actual_git_head"), working_tree_dirty=context.get("working_tree_dirty"),
                git_diff_sha256=context.get("git_diff_sha256"), source_snapshot_sha256=context.get("source_snapshot_sha256"),
                missing_provenance=missing, revision_binding_complete=not missing,
                outcomes=dict(Counter(row["status"] for row in rows)),
                preliminary_categories=dict(Counter(row["triage"] for row in rows if row["triage"])),
                input_preservation=dict(preservation), cases=rows,
                scope="Historical reported verdicts. Categories are preliminary symptoms, not code-defect counts. "
                      "Preservation covers only the inputs registered by that run, not an inferred full INCLUDE tree.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Corpus diagnostics must stay outside the repository")
    result = summarize(args.report)
    output.mkdir(parents=True, exist_ok=False)
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    lines = ["# I04 public-corpus triage", "", "Reported outcomes: " + json.dumps(result["outcomes"]),
             "Revision: " + str(result["actual_git_revision"]), "Missing provenance: " + str(result["missing_provenance"]),
             "", "| Preliminary symptom | Count |", "|---|---:|"]
    lines += [f"| {name} | {count} |" for name, count in result["preliminary_categories"].items()]
    lines += ["", result["scope"]]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf8")
    print(json.dumps(result["outcomes"]))


if __name__ == "__main__":
    main()
