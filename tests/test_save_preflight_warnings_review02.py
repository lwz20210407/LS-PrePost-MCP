"""Review02 P11: successful counts cannot hide unresolved template comments."""
import json

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def test_placeholder_include_warning_survives_save_and_prevents_a_clean_pass(tmp_path, monkeypatch):
    main = tmp_path / "main.k"
    main.write_text("*KEYWORD\n*NODE\n1,0,0,0\n*INCLUDE\n${GEOMETRY}\n*END\n")
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    monkeypatch.setattr(service, "_native", lambda *a, **kw: dict(status="succeeded", job_id="native",
        data={"counts": {"nodes": 1, "elements": 0}, "part_ids": []}))
    result = service.save_model(str(main))
    assert any("placeholder" in warning.lower() for warning in result["warnings"])
    assert result["status"] == "partial"
    checks = {row["name"]: row["status"] for row in result["checks"]}
    assert checks["template_inputs_resolved"] == "missing"
    record = service.jobs.get(result["job_id"])
    assert record["result"] == result
    json.dumps(result, allow_nan=False)
