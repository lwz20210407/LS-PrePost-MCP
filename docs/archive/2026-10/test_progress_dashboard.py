import copy
import importlib.util
import json
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / "tools/progress_dashboard.py"
spec = importlib.util.spec_from_file_location("progress_dashboard", path)
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


def test_progress_counts_only_passed_gates_and_links_valid_evidence(tmp_path):
    data = dashboard.read_progress()
    assert len(data["gates"]) == 36
    assert data["passed"] == sum(g["state"] == "passed" for g in data["gates"])
    gate = next(g for g in data["gates"] if g["state"] == "passed")
    gate["state"] = "partial"
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert dashboard.read_progress(path)["passed"] == data["passed"] - 1


@pytest.mark.parametrize("defect", ["missing_evidence", "duplicate", "denominator"])
def test_invalid_ledger_cannot_publish_progress(tmp_path, defect):
    data = copy.deepcopy(dashboard.read_progress())
    if defect == "missing_evidence":
        next(g for g in data["gates"] if g["state"] == "passed")["evidence"] = []
    elif defect == "duplicate":
        data["gates"][1]["id"] = data["gates"][0]["id"]
    else:
        data["gates"].pop()
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        dashboard.read_progress(path)


def test_dashboard_escapes_status_text():
    data = dashboard.read_progress()
    data["current_task"] = "<script>alert(1)</script>"
    rendered = dashboard.render(data)
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
