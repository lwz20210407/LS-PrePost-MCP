"""A10 fixed twenty-query top-three retrieval evaluation; no private excerpts exported."""

import argparse
import hashlib
import json
from pathlib import Path

from ls_prepost_mcp.knowledge import search_docs

ROOT=Path(__file__).resolve().parents[1]


def expected_match(case,row):
    checks=[]
    for key in ("title","locator"):
        if key in case:
            checks.append(case[key].casefold() in row[key].casefold())
    if "text" in case:
        checks.append(case["text"].casefold() in (row["title"]+" "+row["snippet"]).casefold())
    if "field" in case:
        checks.append(row.get("keyword_field",{}).get("field")==case["field"])
    return bool(checks) and all(checks)


def evaluate(cases,include_private=False):
    rows=[]
    for case in cases:
        results=search_docs(case["query"],category=case["category"],limit=3,include_private=include_private)
        hits=[index+1 for index,row in enumerate(results) if expected_match(case,row)]
        rows.append(dict(id=case["id"],category=case["category"],query=case["query"],hit_at_3=bool(hits),
                         first_correct_rank=hits[0] if hits else None,
                         returned=[dict(id=row["id"],source_id=row["source_id"],version=row["version"],evidence_level=row["evidence_level"]) for row in results]))
    return dict(queries=len(rows),hits_at_3=sum(row["hit_at_3"] for row in rows),results=rows,
                scope="Fixed source-location/field/text matching; not an Agent answer-faithfulness or native-execution evaluation")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--cases",type=Path,default=ROOT/"tests/data/knowledge_queries.json")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--include-private",action="store_true")
    args=parser.parse_args()
    raw=args.cases.read_bytes()
    report=evaluate(json.loads(raw),args.include_private)
    report["queries_sha256"]=hashlib.sha256(raw).hexdigest()
    with args.output.open("x",encoding="utf8") as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(hits_at_3=report["hits_at_3"],queries=report["queries"])))
