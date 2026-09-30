"""Curated source and capability records, never treated as executable code."""
import csv
import json
from pathlib import Path


def records() -> list[dict]:
    return json.loads(Path(__file__).with_name("data").joinpath("sources.json").read_text(encoding="utf-8"))


def search_knowledge(query: str, limit: int = 10) -> list[dict]:
    if not query.strip() or not 1 <= limit <= 50:
        raise ValueError("Provide a query and limit 1..50")
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

