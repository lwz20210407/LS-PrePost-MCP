"""A10 frozen-case top-three retrieval replay; no private excerpts exported."""

import argparse
import hashlib
import json
import math
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
        returned=[]
        for index,row in enumerate(results):
            item=dict(id=row["id"],source_id=row["source_id"],version=row["version"],
                      evidence_level=row["evidence_level"],position=index+1,score=float(row["rank"]),
                      matched_expected=expected_match(case,row))
            if "text" in case:
                item["text_match"]=case["text"].casefold() in (row["title"]+" "+row["snippet"]).casefold()
            if not row.get("private",False):
                item["reference"]={key:row[key] for key in ("source_id","category","title","locator")}
                item["text_sha256"]=row.get("sha256")
                if "keyword_field" in row:
                    item["field"]=row["keyword_field"]["field"]
            returned.append(item)
        rows.append(dict(id=case["id"],category=case["category"],query=case["query"],hit_at_3=bool(hits),
                         first_correct_rank=hits[0] if hits else None,
                         returned=returned))
    report=dict(queries=len(rows),hits_at_3=sum(row["hit_at_3"] for row in rows),results=rows,
                include_private=include_private,
                scope="Fixed source-location/field/text matching; not an Agent answer-faithfulness or native-execution evaluation")
    validate_evaluation(report,cases)
    return report


def validate_evaluation(report,cases):
    """Check counts/identities, without treating cached metadata as a fresh query."""
    if type(report["queries"]) is not int or report["queries"]!=len(cases) or len(report["results"])!=len(cases):
        raise ValueError("Evaluation/query count mismatch")
    if len({case["id"] for case in cases})!=len(cases):
        raise ValueError("Query IDs must be unique")
    for case,row in zip(cases,report["results"]):
        if any(row[key]!=case[key] for key in ("id","category","query")):
            raise ValueError("Evaluation query identity/order mismatch")
        returned=row["returned"]
        if len(returned)>3 or len({item["id"] for item in returned})!=len(returned):
            raise ValueError("Evaluation must contain at most three unique references")
        for rank,item in enumerate(returned,1):
            if (item["position"]!=rank or type(item["score"]) not in (int,float)
                    or not math.isfinite(item["score"]) or type(item["matched_expected"]) is not bool):
                raise ValueError("Invalid reference rank/score/match marker")
            reference=item.get("reference")
            if not report.get("include_private",False) and not reference:
                raise ValueError("Public evaluation needs stable reference metadata")
            if reference:
                if reference["source_id"]!=item["source_id"] or reference["category"]!=case["category"]:
                    raise ValueError("Reference provenance disagrees with the query/result")
                checks=[case[key].casefold() in reference[key].casefold() for key in ("title","locator") if key in case]
                if "field" in case:
                    checks.append(item.get("field")==case["field"])
                if "text" in case:
                    if type(item.get("text_match")) is not bool:
                        raise ValueError("Text matching needs its original query observation")
                    checks.append(item["text_match"])
                if item["matched_expected"]!=(bool(checks) and all(checks)):
                    raise ValueError("Match marker disagrees with the frozen reference selectors")
        correct=[item["position"] for item in returned if item["matched_expected"]]
        if type(row["hit_at_3"]) is not bool or row["hit_at_3"]!=bool(correct) or row["first_correct_rank"]!=(correct[0] if correct else None):
            raise ValueError("Evaluation score disagrees with per-reference matches")
    if report["hits_at_3"]!=sum(row["hit_at_3"] for row in report["results"]):
        raise ValueError("Evaluation total disagrees with per-query scores")


def stable_reference(item):
    """Prefer semantic locations to content-derived IDs for historical comparison."""
    reference=item.get("reference")
    if reference:
        return tuple(reference.get(key) for key in ("category","source_id","locator","title"))
    return None


def compare_replays(previous,current,reference_lookup=None):
    """Report independent score, stable-reference and raw-ID changes, including unknowns."""
    reference_lookup=reference_lookup or {}
    old={row["id"]:row for row in previous["results"]}
    if len(old)!=len(previous["results"]) or set(old)!={row["id"] for row in current["results"]}:
        raise ValueError("Cannot compare different query sets")
    changes=[]
    for row in current["results"]:
        before=old[row["id"]]
        if any(before[key]!=row[key] for key in ("query","category")):
            raise ValueError("Cannot compare changed question identities")
        old_refs=[item if item.get("reference") else {**item,"reference":reference_lookup.get(item["id"])}
                  for item in before["returned"]]
        unresolved=sum(stable_reference(item) is None for item in old_refs)
        stable_changed=None if unresolved else ([stable_reference(item) for item in old_refs]
            !=[stable_reference(item) for item in row["returned"]])
        has_scores=all("score" in item for item in before["returned"])
        score_changed=None if not has_scores else (len(before["returned"])!=len(row["returned"]) or any(
            not math.isclose(a["score"],b["score"],rel_tol=1e-12,abs_tol=1e-12)
            for a,b in zip(before["returned"],row["returned"])))
        changes.append(dict(id=row["id"],hit_changed=before["hit_at_3"]!=row["hit_at_3"],
            first_correct_rank_changed=before["first_correct_rank"]!=row["first_correct_rank"],
            stable_top3_changed=stable_changed,historical_references_unresolved=unresolved,
            score_changed=score_changed,
            raw_doc_ids_changed=[x["id"] for x in before["returned"]]!=[x["id"] for x in row["returned"]],
            source_sequence_changed=[x["source_id"] for x in before["returned"]]!=[x["source_id"] for x in row["returned"]]))
    return changes


def check_replay(stored,current):
    """A cached score with different returned references is stale even if totals agree."""
    changes=compare_replays(stored,current)
    if any(change["hit_changed"] or change["first_correct_rank_changed"]
           or change["stable_top3_changed"] or change["raw_doc_ids_changed"] or change["score_changed"] for change in changes):
        raise ValueError("Stored top-three replay is stale")
    for old,new in zip(stored["results"],current["results"]):
        if any(any(a.get(key)!=b.get(key) for key in ("source_id","version","evidence_level","matched_expected","position"))
               for a,b in zip(old["returned"],new["returned"])):
            raise ValueError("Stored reference provenance is stale")


def markdown_report(report):
    lines=["# A10 frozen-case replay", "", f"Top-3 hits: {report['hits_at_3']}/{report['queries']}", "",
           "| Query ID | Category | Hit | First correct rank | Top-three public references (BM25 score) | 有效性 |",
           "|---|---|---|---:|---|---|"]
    for row in report["results"]:
        refs=[]
        for item in row["returned"]:
            ref=item.get("reference",{})
            label=ref.get("title",item["source_id"])
            label=label.replace("|","\\|").replace("\n"," ")
            refs.append(f"{item['position']}. {label} ({item['score']:.10g})")
        lines.append(f"| {row['id']} | {row['category']} | {str(row['hit_at_3']).lower()} | "
                     f"{row['first_correct_rank'] or '-'} | {'<br>'.join(refs) or '-'} | 登记修订/索引有效 |")
    return "\n".join(lines)+"\n"


def check_artifacts(report,cases,markdown):
    validate_evaluation(report,cases)
    if markdown!=markdown_report(report):
        raise ValueError("Markdown report disagrees with evaluation JSON")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--cases",type=Path,default=ROOT/"tests/data/knowledge_queries.json")
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output",type=Path)
    action.add_argument("--check-report",type=Path,help="Validate saved JSON and optional Markdown; replay using the configured index")
    parser.add_argument("--markdown",type=Path,help="Write/read a matching Markdown table")
    parser.add_argument("--include-private",action="store_true")
    args=parser.parse_args()
    raw=args.cases.read_bytes()
    cases=json.loads(raw)
    report=evaluate(cases,args.include_private)
    report["queries_sha256"]=hashlib.sha256(raw.replace(b"\r\n",b"\n")).hexdigest()
    report["queries_sha256_raw_execution"]=hashlib.sha256(raw).hexdigest()
    if args.check_report:
        stored=json.loads(args.check_report.read_text(encoding="utf8"))
        validate_evaluation(stored,cases)
        if stored.get("include_private")!=args.include_private:
            raise ValueError("Private/public evaluation modes differ")
        if stored["queries_sha256"]!=report["queries_sha256"]:
            raise ValueError("Question file identity differs from the stored replay")
        check_replay(stored,report)
        if args.markdown:
            check_artifacts(stored,cases,args.markdown.read_text(encoding="utf8"))
    else:
        with args.output.open("x",encoding="utf8") as stream:
            json.dump(report,stream,ensure_ascii=False,separators=(",", ":"))
            stream.write("\n")
        if args.markdown:
            with args.markdown.open("x",encoding="utf8",newline="\n") as stream:
                stream.write(markdown_report(report))
    print(json.dumps(dict(hits_at_3=report["hits_at_3"],queries=report["queries"])))
