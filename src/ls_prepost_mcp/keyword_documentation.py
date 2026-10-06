"""I05 adapter for Claude's keyword_docs provider; no field parser lives here."""

import argparse
import importlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from dataclasses import field as data_field
from pathlib import Path


@dataclass(frozen=True)
class KeywordField:
    entity_key: str
    option: str | None
    card: int | str
    field: str
    offset: int
    width: int
    help: str
    links: list
    manual_ref: dict | None
    solver_status: dict
    license: str
    version: str
    aliases: list[str] = data_field(default_factory=list)

    @property
    def visibility(self):
        return "private" if self.manual_ref else "public"

    def __post_init__(self):
        if not self.entity_key.startswith("*") or not self.field or type(self.offset) is not int or type(self.width) is not int:
            raise ValueError("Invalid keyword field identity/layout")
        if self.offset < 0 or self.width < 1 or not self.version:
            raise ValueError("Invalid keyword field columns/version")
        if self.manual_ref and self.license == "MIT":
            raise ValueError("Manual content cannot be marked MIT")


def documentation_provider():
    try:
        return importlib.import_module("ls_prepost_mcp.domain.model.keyword_docs")
    except ImportError as exc:
        raise RuntimeError("keyword_docs provider is unavailable; install its dependencies or specify an authorized provider checkout") from exc


def keyword_names(provider=None):
    """Enumerate the provider's public catalog, retaining older checkout support."""
    provider = documentation_provider() if provider is None else provider
    public_keywords = getattr(provider, "keywords", None)
    if public_keywords is not None:
        return public_keywords()
    public_catalog = getattr(provider, "catalog", None)
    if public_catalog is not None:
        return sorted({row["keyword"] for row in public_catalog()})
    legacy_catalog = getattr(provider, "_catalog", None)
    if legacy_catalog is None:
        raise RuntimeError("keyword_docs provider exposes no keyword catalog")
    return sorted({row[0] for row in legacy_catalog()})


def keyword_fields(keywords=None, provider=None, *, coverage=None):
    """Yield every field; optional coverage records enumeration, never solver proof.

    Provider exceptions propagate. An all-keyword build must not silently publish
    a partial catalog. Keywords with no returned fields are listed explicitly.
    """
    if provider is None:
        provider = documentation_provider()
    if keywords is None:
        keywords = keyword_names(provider)
    keywords = list(dict.fromkeys(keywords))
    if coverage is not None:
        coverage.update(requested_keywords=len(keywords), completed_keywords=0,
                        field_records=0, without_fields=[])
    for keyword in keywords:
        doc = provider.keyword_doc(keyword)
        field_count = 0
        for card in doc["cards"]:
            for field in card["fields"]:
                columns = re.fullmatch(r"(\d+)-(\d+)", field["columns"])
                if not columns:
                    raise ValueError("Provider did not supply a field column range")
                manual_text = provider.manual_field_text(doc["keyword"], field["name"])
                manual = dict(section=doc.get("manual"), field_text=manual_text) if doc.get("manual") or manual_text else None
                aliases = [other for old,new in getattr(provider,"CONTACT_RENAMES",{}).items()
                           for name,other in ((old,new),(new,old)) if name == field["name"]]
                links = [row for row in doc["references"] if row["field"] in {field["name"], *aliases}]
                field_count += 1
                yield KeywordField(doc["keyword"], card["option"], card["card"], field["name"],
                                   int(columns[1])-1, int(columns[2])-int(columns[1])+1, field.get("help", ""),
                                   links, manual, dict(evidence=doc["evidence"], detail=doc.get("engine_verified"),
                                                       attribution="Claude keyword_docs provider"),
                                   "MIT+restricted_manual" if manual else "MIT", doc["source"]["fields"], aliases)
        if coverage is not None:
            coverage["completed_keywords"] += 1
            coverage["field_records"] += field_count
            if not field_count:
                coverage["without_fields"].append(keyword)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-root", type=Path)
    parser.add_argument("--keyword", action="append")
    parser.add_argument("--with-coverage", action="store_true")
    args = parser.parse_args()
    if args.provider_root:
        source = args.provider_root.resolve() / "src"
        if not (source / "ls_prepost_mcp/domain/model/keyword_docs.py").is_file():
            raise ValueError("Provider checkout has no keyword_docs module")
        sys.path.insert(0, str(source))
    coverage = {}
    fields = [asdict(row) for row in keyword_fields(args.keyword, coverage=coverage)]
    print(json.dumps(dict(fields=fields, coverage=coverage) if args.with_coverage else fields,
                     ensure_ascii=True, allow_nan=False))
