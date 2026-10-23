"""Release status must not outrun advertised history coverage or retained gaps."""

import json
from pathlib import Path

import yaml


def catalog():
    return {row["id"]: row for row in yaml.safe_load(Path("tasks.yaml").read_text(encoding="utf8"))["tasks"]}


def test_done_q01_has_no_unresolved_gaps_and_an_explicit_native_level():
    task = catalog()["Q01"]
    if task["status"] == "done":
        assert not task.get("gaps"), "Q01 retains unresolved identity/native gaps"
        assert task.get("verification_level") == "L2"


def test_done_q05_has_native_d3plot_coverage_for_advertised_domains():
    task = catalog()["Q05"]
    if task["status"] == "done":
        evidence = json.loads(
            Path("docs/decisions/evidence/q05-history/evidence.json").read_text(encoding="utf8")
        )
        covered = {
            (case["source_kind"], case["domain"])
            for run in evidence["runs"]
            for case in run["cases"]
            if case.get("status") == "succeeded"
        }
        required = {
            ("d3plot", domain) for domain in ("node", "solid", "shell", "tshell", "beam", "part", "global")
        }
        assert required <= covered, f"Missing native default-source coverage: {sorted(required - covered)}"
        assert not task.get("gaps")
