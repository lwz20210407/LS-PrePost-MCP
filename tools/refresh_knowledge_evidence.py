"""A10: replay unchanged historical questions against one public-only index."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path

from tools.evaluate_knowledge import check_artifacts, compare_replays, evaluate, markdown_report
from tools.native_regression import execution_identity

ROOT = Path(__file__).resolve().parents[1]
SETS = {
    "legacy_20": ("knowledge_queries.json", "historical_tuning"),
    "dev": ("knowledge_dev_queries.json", "historical_tuning"),
    "holdout_24": ("knowledge_holdout_queries.json", "previously_exposed_historical_evaluation"),
    "holdout_b": ("knowledge_holdout_b_queries.json", "independence_unproven_historical_evaluation"),
}
PRODUCT_PATHS = [
    "src/ls_prepost_mcp/knowledge_index.py", "src/ls_prepost_mcp/knowledge.py",
    "src/ls_prepost_mcp/knowledge_results.py", "src/ls_prepost_mcp/keyword_documentation.py",
    "src/ls_prepost_mcp/domain/model/keyword_docs.py", "src/ls_prepost_mcp/data/search_glossary.json",
]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def check_active_product_sources(evidence, root=ROOT):
    """An active replay becomes stale after product edits, even if old blobs still exist."""
    identities = {item["path"]: item for item in evidence["product_source_identity"]}
    if set(identities) != set(PRODUCT_PATHS):
        raise ValueError("Active A10 replay must bind every retrieval product source")
    for relative, identity in identities.items():
        raw = (root / relative).read_bytes()
        if sha256(raw.replace(b"\r\n", b"\n")) != identity["sha256_lf"]:
            raise ValueError("Active A10 replay is stale after product source change: " + relative)


def file_identity(relative, revision):
    """Git blobs and normalized LF hashes are portable across Windows/Linux checkouts."""
    data = subprocess.check_output(["git", "show", f"{revision}:{relative}"], cwd=ROOT, timeout=15)
    blob = subprocess.check_output(["git", "rev-parse", f"{revision}:{relative}"], cwd=ROOT,
                                   text=True, timeout=15).strip()
    return dict(path=relative, git_blob=blob, sha256_lf=sha256(data.replace(b"\r\n", b"\n")))


def index_metadata(path):
    """Read one SQLite snapshot; publish no text, private references or absolute paths."""
    lookup = {}
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("BEGIN")
        visibility = dict(db.execute("SELECT visibility,count(*) FROM documents GROUP BY visibility"))
        if set(visibility) != {"public"}:
            raise ValueError("A10 formal evidence requires a public-only index")
        if db.execute("SELECT count(*) FROM documents WHERE license NOT IN ('MIT','Apache-2.0')").fetchone()[0]:
            raise ValueError("Index contains a source outside the permitted public reference licenses")
        categories = dict(db.execute("SELECT category,count(*) FROM documents GROUP BY category"))
        if categories.get("api", 0):
            raise ValueError("Register and review a real public API source before changing this evidence scope")
        text_rows, source_rows = [], []
        for ident, source, category, locator, title, version, license_, digest in db.execute(
            "SELECT id,source_id,category,locator,title,version,license,sha256 FROM documents ORDER BY source_id,locator,id"
        ):
            reference = dict(source_id=source, category=category, locator=locator, title=title)
            lookup[ident] = reference
            text_rows.append([source, category, locator, title, digest])
            source_rows.append([source, category, locator, title, version, license_, digest])
        versions = [dict(category=category, version=version, license=license_, documents=count)
                    for category, version, license_, count in db.execute(
                        "SELECT category,version,license,count(*) FROM documents GROUP BY category,version,license ORDER BY category,version,license")]
        schema, tokenization = db.execute("SELECT * FROM metadata").fetchone()
    with path.open("rb") as stream:
        index_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    def canonical(rows):
        return b"".join((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode() for row in rows)
    return dict(sha256=index_hash, bytes=path.stat().st_size, categories=categories,
                visibility=visibility, schema_version=schema, api_tokenization=tokenization,
                stable_text_manifest_sha256=sha256(canonical(sorted(text_rows))),
                source_and_text_manifest_sha256=sha256(canonical(source_rows)), source_versions=versions), lookup


def suite_markdown(evidence):
    lines = ["# A10 当前公开索引重放（L1）", "", "题集原样保留；这不是新独立留出集，也不是原生或工程正确性验证。", "",
             "| 题集 | 性质 | f04843a 历史命中 | 本次命中 | API 命中 | 有效性 |",
             "|---|---|---:|---:|---:|---|"]
    for key, record in evidence["sets"].items():
        run, old = record["run"], record["historical"]
        api = [row for row in run["results"] if row["category"] == "api"]
        lines.append(f"| {key} | {record['role']} | {old['hits_at_3']}/{old['queries']} | "
                     f"{run['hits_at_3']}/{run['queries']} | {sum(row['hit_at_3'] for row in api)}/{len(api)} | 登记修订/索引有效 |")
    lines += ["", "## 评分变化", "",
              "| 题集/题号 | 历史命中→当前命中 | 首个正确名次变化 | 稳定引用比较 | 有效性 |",
              "|---|---|---|---|---|"]
    for key, record in evidence["sets"].items():
        old = {row["id"]: row for row in record["historical"]["results"]}
        fresh = {row["id"]: row for row in record["run"]["results"]}
        for change in record["comparison"]:
            if change["hit_changed"] or change["first_correct_rank_changed"]:
                ident = change["id"]
                stable = "历史位置缺失，无法断言" if change["stable_top3_changed"] is None else str(change["stable_top3_changed"])
                lines.append(f"| {key}/{ident} | {old[ident]['hit_at_3']}→{fresh[ident]['hit_at_3']} | "
                             f"{old[ident]['first_correct_rank']}→{fresh[ident]['first_correct_rank']} | {stable} | 历史对比 |")
    return "\n".join(lines) + "\n"


def validate_suite(evidence, markdown, tables, root=ROOT):
    """Check artifacts against frozen questions, not hard-coded expected hit counts."""
    if set(evidence["sets"]) != set(SETS) or evidence["include_private"] or evidence["native_executed"]:
        raise ValueError("Unexpected evidence scope")
    check_active_product_sources(evidence, root)
    for key, (name, role) in SETS.items():
        record = evidence["sets"][key]
        raw = (root / "tests/data" / name).read_bytes()
        if record["role"] != role or record["independent_holdout"] is not False:
            raise ValueError("Historical sets cannot be relabelled independent")
        if record["questions"]["sha256_lf"] != sha256(raw.replace(b"\r\n", b"\n")):
            raise ValueError("Frozen questions changed")
        check_artifacts(record["run"], json.loads(raw), tables[key])
        resolved = record["historical_reference_lookup"]
        if compare_replays(record["historical"], record["run"], resolved) != record["comparison"]:
            raise ValueError("Historical comparison disagrees with returned references")
    if suite_markdown(evidence) != markdown:
        raise ValueError("Summary Markdown disagrees with evidence")


def refresh(index, build_report, destination):
    identity = execution_identity(ROOT)
    if identity["working_tree_dirty"] is not False:
        raise ValueError("Commit evaluation tooling first; run from a clean checkout")
    if destination.exists():
        raise ValueError("Use a fresh output directory; never overwrite historical evidence")
    revision = identity["actual_git_head"]
    build = json.loads(build_report.read_text(encoding="utf8"))
    index_info, lookup = index_metadata(index)
    if (index_info["sha256"] != build["index_sha256"] or build["working_tree_dirty"]
            or index_info["source_and_text_manifest_sha256"] != build["document_text_manifest_sha256"]):
        raise ValueError("Index bytes/build identity mismatch")
    os.environ["LSPP_KNOWLEDGE_INDEX"] = str(index.resolve())
    history_path = "docs/decisions/evidence/a10-cross-language/evidence.json"
    history = json.loads((ROOT / history_path).read_text(encoding="utf8"))
    evidence = dict(schema_version=1, actual_git_revision=revision,
        working_tree_dirty=False, git_diff_sha256=identity["git_diff_sha256"],
        git_diff_scope=identity["git_diff_scope"], include_private=False, native_executed=False,
        verification_level="L1", status="partial", identity_hash_convention="Git blobs / SHA256 after CRLF to LF normalization",
        product_source_identity=[file_identity(path, revision) for path in PRODUCT_PATHS],
        runner_source_identity=[file_identity(path, revision) for path in (
            "tools/evaluate_knowledge.py", "tools/refresh_knowledge_evidence.py")],
        test_source_identity=[file_identity(path, revision) for path in (
            "tests/test_knowledge_evaluation_artifacts.py", "tests/test_knowledge_regular_word_families.py",
            "tests/test_a10_current_replay_evidence.py")],
        index=index_info, historical_source=dict(path=history_path, revision=history["actual_git_revision"]),
        sets={})
    build_revision = build["actual_git_revision"]
    input_paths = ["src/ls_prepost_mcp/data/commands.tsv", "src/ls_prepost_mcp/native/commands.py",
                   "docs/KNOWN_ISSUES.md", "docs/INSTALL.md", "src/ls_prepost_mcp/data/keyword_fieldless_review.json", "uv.lock"]
    input_paths += [path.relative_to(ROOT).as_posix() for folder, pattern in (
        ("examples/workflows", "*.json"), ("src/ls_prepost_mcp/native/recipes", "**/recipe.yaml"))
        for path in sorted((ROOT / folder).glob(pattern))]
    provider = importlib.metadata.distribution("ansys-dyna-core")
    evidence["index"]["build"] = dict(actual_git_revision=build_revision, working_tree_dirty=False,
        command="python -B tools/build_knowledge_index.py --all-keywords --output <public-index.sqlite>",
        execution="Public-only library calls repository_documents/keyword_fields/fieldless/build_index; command above is the equivalent CLI",
        private_manual_environment_disabled=True, external_sources=False,
        provider=dict(package="ansys-dyna-core", version=provider.version,
                      package_metadata_sha256=sha256(provider.read_text("METADATA").encode())),
        keyword_coverage={key: build["keyword_coverage"][key] for key in ("requested_keywords", "completed_keywords", "field_records", "without_fields")},
        input_source_identity=[file_identity(path, build_revision) for path in input_paths])
    tables = {}
    for key, (name, role) in SETS.items():
        relative = "tests/data/" + name
        cases = json.loads((ROOT / relative).read_text(encoding="utf8"))
        run = evaluate(cases)
        old = history["sets"][key]["runs"]["public"]
        resolved = {item["id"]: lookup[item["id"]] for row in old["results"]
                    for item in row["returned"] if item["id"] in lookup}
        evidence["sets"][key] = dict(role=role, independent_holdout=False,
            questions=file_identity(relative, revision), run=run, historical=old,
            historical_reference_lookup=resolved, comparison=compare_replays(old, run, resolved),
            category_totals={category: dict(queries=sum(row["category"] == category for row in run["results"]),
                hits_at_3=sum(row["category"] == category and row["hit_at_3"] for row in run["results"]))
                for category in sorted(Counter(row["category"] for row in run["results"]))})
        tables[key] = markdown_report(run)
    markdown = suite_markdown(evidence)
    validate_suite(evidence, markdown, tables)
    destination.mkdir(parents=True)
    (destination / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf8")
    (destination / "summary.md").write_text(markdown, encoding="utf8", newline="\n")
    for key, table in tables.items():
        (destination / (key + "-top3.md")).write_text(table, encoding="utf8", newline="\n")
    print(json.dumps({key: dict(queries=value["run"]["queries"], hits_at_3=value["run"]["hits_at_3"])
                      for key, value in evidence["sets"].items()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-build-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    refresh(args.index, args.index_build_report, args.output_dir)
