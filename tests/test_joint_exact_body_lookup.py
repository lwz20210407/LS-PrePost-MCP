"""P12 CNRB identities use exact IDs, not the generic physical-field tolerance."""

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.service import Service
from tests.test_keyword_engine_joints import _deck

PID = 1_000_000_000


def fixture(tmp_path, second=False):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    extra = ("*SET_NODE_LIST\n        50\n       205       206\n"
             f"*CONSTRAINED_NODAL_RIGID_BODY\n{PID:>10}{0:>10}{50:>10}\n")
    if second:
        extra += ("*SET_NODE_LIST\n        60\n       207       208\n"
                  f"*CONSTRAINED_NODAL_RIGID_BODY\n{PID+1:>10}{0:>10}{60:>10}\n")
    return _deck(source_dir, extra, deformable=True)


def edit(service, source, pid):
    return service.create_entities(str(source), [dict(op="add_joint", kind="revolute",
        a=dict(part=1), b=dict(nodal_rigid_body=pid), origin=[0, 0, 0], axis=[0, 0, 1], length=40., jid=901)])


@pytest.mark.parametrize("missing", [PID-1, PID+1])
def test_public_missing_large_cnrb_id_never_binds_a_nearby_existing_body(tmp_path, missing):
    source = fixture(tmp_path)
    before = source.read_bytes()
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    result = edit(service, source, missing)
    assert result["status"] == "failed", "Generic fuzzy lookup silently bound a different CNRB PID"
    assert "no *CONSTRAINED_NODAL_RIGID_BODY" in result["error"]["message"]
    assert not result["artifacts"] and source.read_bytes() == before


def _cnrb_sets(deck):
    result = {}
    for block in deck.iter_blocks():
        if block.name == "*CONSTRAINED_NODAL_RIGID_BODY":
            layout = deck.layout(block)
            for key in list(layout.rows) if layout.key else [None]:
                fields = {field.name: field.value for field in deck.fields(block, key)}
                result[fields["pid"]] = fields["nsid"]
    return result


def test_two_nearby_existing_large_ids_update_only_the_requested_body(tmp_path):
    source = fixture(tmp_path, second=True)
    before = source.read_bytes()
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    result = edit(service, source, PID+1)
    assert result["status"] == "succeeded", result.get("error")
    deck = KeywordDeck.load(result["data"]["main"])
    # Read the actual named rows exactly, without reusing the fuzzy find under test.
    bodies = _cnrb_sets(deck)
    assert bodies[PID] == 50
    assert bodies[PID+1] != 60
    selected_set = next(b for b in deck.iter_blocks() if b.name.startswith("*SET_NODE_LIST")
                        and deck.get(b, "sid").value == bodies[PID+1])
    assert deck.members(selected_set) == [207, 208, 211, 212]
    assert result["data"]["summaries"][0]["side_b"]["nodal_rigid_body"] == PID+1
    assert source.read_bytes() == before


def test_exact_large_identity_still_creates_a_joint(tmp_path):
    source = fixture(tmp_path)
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    result = edit(service, source, PID)
    assert result["status"] == "succeeded", result.get("error")
