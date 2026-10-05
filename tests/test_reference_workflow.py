"""M0-3: exercise the actual checker through workflow dispatch and gates."""

import hashlib

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("material_id,valid", [(1, True), (99, False)])
def test_reference_verdict_controls_workflow(tmp_path, material_id, valid):
    pytest.importorskip("ansys.dyna.core")
    deck = tmp_path / "model.k"
    deck.write_text(
        "*KEYWORD\n*NODE\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n"
        f"*PART\np\n1,1,{material_id}\n*SECTION_SHELL\n1\n1.0\n"
        "*MAT_ELASTIC\n1,7.8e-9,2.1e5,0.3\n*ELEMENT_SHELL\n1,1,1,2,3,4\n*END\n",
        encoding="ascii",
    )
    before = hashlib.sha256(deck.read_bytes()).hexdigest()
    service = Service(Settings(tmp_path))
    direct = service.validate_model_references(str(deck))
    assert direct["status"] == "succeeded"
    assert direct["valid_within_scope"] is valid
    assert direct["data"]["valid_within_scope"] is valid
    workflow = service.create_workflow(
        "Reference check",
        [
            dict(id="check", action="validate_model_references", arguments=dict(model=str(deck))),
            dict(id="after", action="validate_model_references", arguments=dict(model=str(deck))),
        ],
    )["artifacts"][0]["path"]
    result = service.run_workflow(workflow)
    assert result["status"] == ("succeeded" if valid else "failed")
    assert result["data"]["completed_steps"] == (2 if valid else 0)
    if not valid:
        assert result["data"]["failure_phase"] == "quality_gate"
        assert result["data"]["skipped_steps"] == ["after"]
    assert hashlib.sha256(deck.read_bytes()).hexdigest() == before
