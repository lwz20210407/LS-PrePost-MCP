"""I05: build a local reference index; never download or execute its sources."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from ls_prepost_mcp import keyword_documentation
from ls_prepost_mcp.keyword_documentation import KeywordField, KeywordWithoutFields, keyword_fields
from ls_prepost_mcp.knowledge_index import build_index, chunks, repository_documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--external-sources", type=Path, help="Private local JSON manifest of text references")
    parser.add_argument("--keyword-provider-root", type=Path, help="Authorized external provider checkout; optional now that keyword_docs is integrated")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--keyword", action="append", help="Keyword to index through keyword_docs; repeat as needed")
    selection.add_argument("--all-keywords", action="store_true", help="Index the integrated provider's complete keyword catalog; requires the pydyna extra")
    args = parser.parse_args()
    documents = list(repository_documents())
    fields = []
    coverage = {}
    if args.keyword_provider_root:
        root = args.keyword_provider_root.resolve(strict=True)
        argv = [sys.executable, "-B", keyword_documentation.__file__, "--provider-root", str(root), "--with-coverage"]
        for keyword in args.keyword or []:
            argv += ["--keyword", keyword]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        result = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, encoding="utf8", timeout=600)
        if result.returncode:
            raise RuntimeError("keyword_docs provider failed: " + result.stderr[-4000:])
        payload = json.loads(result.stdout)
        fields = [KeywordField(**row) for row in payload["fields"]]
        coverage = payload["coverage"]
    elif args.keyword or args.all_keywords:
        fields = list(keyword_fields(args.keyword, coverage=coverage))
    if args.external_sources:
        rows = json.loads(args.external_sources.read_text(encoding="utf8"))
        if not isinstance(rows, list):
            raise ValueError("External sources must be a list")
        for row in rows:
            if set(row) - {"id", "category", "path", "license", "version"}:
                raise ValueError("External sources are always private; unsupported metadata")
            documents.extend(chunks(row["path"], source_id=row["id"], category=row["category"],
                                    license=row["license"], version=row.get("version", "unspecified"),
                                    locator="local://" + row["id"]))
    fieldless = [KeywordWithoutFields(**row) for row in coverage.get("without_fields_detail", [])]
    result = build_index(args.output, documents, fields, fieldless)
    if coverage:
        result["keyword_coverage"] = coverage
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
