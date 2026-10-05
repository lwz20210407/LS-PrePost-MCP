"""I05: build a local reference index; never download or execute its sources."""

import argparse
import json
from pathlib import Path

from ls_prepost_mcp.knowledge_index import build_index, chunks, keyword_documents, repository_documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--external-sources", type=Path, help="Private local JSON manifest of text references")
    parser.add_argument("--pydyna-root", type=Path, help="Installed/versioned keyword_classes source directory")
    parser.add_argument("--pydyna-version", default="0.12.1")
    args = parser.parse_args()
    documents = list(repository_documents())
    if args.pydyna_root:
        documents.extend(keyword_documents(args.pydyna_root, args.pydyna_version))
    if args.external_sources:
        rows = json.loads(args.external_sources.read_text(encoding="utf8"))
        if not isinstance(rows, list):
            raise ValueError("External sources must be a list")
        for row in rows:
            if set(row) - {"id", "category", "path", "license", "version"}:
                raise ValueError("External sources are always private; unsupported metadata")
            documents.extend(chunks(row["path"], source_id=row["id"], category=row["category"],
                                    license=row["license"], version=row.get("version", "unspecified")))
    print(json.dumps(build_index(args.output, documents), ensure_ascii=False))


if __name__ == "__main__":
    main()
