"""Curated source and capability records, never treated as executable code."""
import csv
import json
import os
from pathlib import Path


def records() -> list[dict]:
    return json.loads(Path(__file__).with_name("data").joinpath("sources.json").read_text(encoding="utf-8"))


def search_knowledge(query: str, limit: int = 10, include_private: bool = False, category: str | None = None) -> list[dict]:
    """Search LSPP_KNOWLEDGE_INDEX when configured; private records require explicit opt-in."""
    if not query.strip() or not 1 <= limit <= 50:
        raise ValueError("Provide a query and limit 1..50")
    configured = os.environ.get("LSPP_KNOWLEDGE_INDEX")
    if configured:
        from .knowledge_index import search_index
        return search_index(configured, query, limit=limit, include_private=include_private, category=category)
    if include_private or category is not None:
        raise ValueError("Configure LSPP_KNOWLEDGE_INDEX for categorized/private document search")
    words = query.casefold().split()
    ranked = []
    for record in records():
        haystack = json.dumps(record, ensure_ascii=False).casefold()
        score = sum(word in haystack for word in words)
        if score:
            ranked.append((score, record))
    return [r for _, r in sorted(ranked, key=lambda row: row[0], reverse=True)[:limit]]


def list_capabilities() -> dict:
    return json.loads(Path(__file__).with_name("data").joinpath("capabilities.json").read_text(encoding="utf-8"))


def search_commands(query: str, limit: int = 20) -> list[dict]:
    """Search the attributed Apache-2.0 command catalog; rows are not executable validation."""
    if not query.strip() or not 1 <= limit <= 100:
        raise ValueError("Provide a query and limit 1..100")
    path = Path(__file__).with_name("data") / "commands.tsv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    tokens = query.casefold().split()
    scored = []
    for row in rows:
        score = sum(t in " ".join(str(v) for v in row.values()).casefold() for t in tokens)
        if score:
            scored.append((score, {**row, "status": "reference_unverified", "source": "library-cfile-support"}))
    return [row for _, row in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]


def search_workflows(query: str, limit: int = 10) -> list[dict]:
    """Find authored tutorial acceptance cases; these are not completed automation recipes."""
    if not query.strip() or not 1 <= limit <= 50:
        raise ValueError("Provide a query and limit 1..50")
    items = json.loads(Path(__file__).with_name("data").joinpath("workflows.json").read_text(encoding="utf-8"))
    tokens = query.casefold().split()
    ranked = [(sum(t in json.dumps(r, ensure_ascii=False).casefold() for t in tokens), r) for r in items]
    return [r for score, r in sorted(ranked, key=lambda p: p[0], reverse=True) if score][:limit]


def search_docs(query: str, category: str | None = None, limit: int = 10, include_private: bool = False) -> list[dict]:
    """Search command/API/keyword/guide/recipe/known-issue references in LSPP_KNOWLEDGE_INDEX; return source, version and scoped evidence level. Private text requires explicit opt-in."""
    from .knowledge_index import search_index

    configured=os.environ.get("LSPP_KNOWLEDGE_INDEX")
    if not configured:
        raise ValueError("Set LSPP_KNOWLEDGE_INDEX to an external schema-v2 reference index")
    if not isinstance(query,str) or not query.strip():
        raise ValueError("Provide a nonempty document query")
    results=search_index(configured,query,category=category,limit=limit,include_private=include_private)
    for row in results:
        row["query_expansion"]=[]
        row["evidence_level"]="source_example" if row["category"] in ("command","recipe") else "documented"
        row["evidence_scope"]="Reference content; not an execution result"
        recipe=row.get("recipe_verification",{})
        verified=recipe.get("versions_verified",[])
        modes=recipe.get("execution_modes",{})
        if verified and recipe.get("l2_case") and any(
                state=="verified" and version in verified for values in modes.values()
                for version,state in values.items()):
            row["evidence_level"]="native_verified"
            row["evidence_scope"]="Recipe-reported verification only for listed versions and modes; not a current run"
            row["verification_attribution"]=row["source_id"]
        proof=row.get("keyword_field",{}).get("solver_status",{})
        if proof.get("evidence")=="verified":
            row["evidence_level"]="native_verified"
            row["evidence_scope"]="Provider-reported keyword/card solver acceptance, not verification of every field effect"
            row["verification_attribution"]=proof.get("attribution")
    return results


def keyword_fields(keyword: str, field: str | None = None, limit: int = 20, include_private: bool = False) -> list[dict]:
    """Find indexed provider fields with card/option/columns/help/references/manual provenance; keyword prefixes and recorded field aliases are supported."""
    key=keyword.strip().upper()
    if not key.startswith("*"):
        key="*"+key
    if not key[1:] or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-/" for c in key[1:]):
        raise ValueError("Provide a keyword name or prefix")
    if field is not None and (not field.strip() or not all(c.isalnum() or c=="_" for c in field)):
        raise ValueError("Provide a field name")
    results=search_docs(key+(" "+field if field else ""),category="keyword",limit=limit,include_private=include_private)
    return [row for row in results if row.get("keyword_field",{}).get("entity_key","").startswith(key)
            and (field is None or field.casefold() in [row["keyword_field"]["field"].casefold(),
                                                      *[alias.casefold() for alias in row["keyword_field"].get("aliases",[])]])]


def command_help(command: str, limit: int = 5) -> list[dict]:
    """Retrieve attributed command syntax/examples; documentation alone does not certify a native version."""
    return search_docs(command,category="command",limit=limit)
