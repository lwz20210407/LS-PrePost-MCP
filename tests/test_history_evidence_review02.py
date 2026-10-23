"""P1-7: zero displacement cannot certify native node-ID correspondence."""
import json
from pathlib import Path


def test_native_node_history_evidence_uses_two_distinct_nonzero_curves(pytestconfig):
    root = Path(pytestconfig.rootpath)
    evidence = json.loads((root / "docs/decisions/evidence/q05-history/evidence.json").read_text(encoding="utf-8"))
    if evidence.get("active_review02_evidence"):
        evidence = json.loads((root / evidence["active_review02_evidence"]).read_text(encoding="utf-8"))
        runs = [r for r in evidence["runs"] if r["validity"] == "current_for_recorded_product_blobs"]
    else:
        runs = evidence["runs"]
    nodes = [case for run in runs for case in run["cases"] if case["domain"] == "node"]
    assert nodes, "No native node comparison evidence"
    for case in nodes:
        oracle = case.get("nonzero_node_oracle")
        assert oracle, "Constant zero node histories do not establish an ID mapping oracle"
        assert len(set(case["entity_ids"])) == 2
        assert len(oracle["peaks"]) == 2 and min(oracle["peaks"]) > 0
        assert oracle["max_curve_separation"] > 1e-3 * max(oracle["peaks"])
        assert case["status"] == "succeeded" and case["source_unchanged"]
