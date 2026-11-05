"""P12 public identity inputs must not silently select another body or Joint ID."""

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.joints import add_joint
from ls_prepost_mcp.service import Service
from tests.test_keyword_engine_joints import _deck

EXTRA = ("*CONTROL_RIGID\n         1\n"
         "*DEFINE_CURVE\n         1\n                 0.0                 2.0\n                 1.0                 2.0\n"
         "*DEFINE_CURVE\n        70\n                 0.0                 2.0\n                 1.0                 2.0\n")
CNRB = "*SET_NODE_LIST\n        50\n       205       206\n*CONSTRAINED_NODAL_RIGID_BODY\n        90         0        50\n"


def setup(tmp_path, mode="part"):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = _deck(source_dir, EXTRA + (CNRB if mode == "cnrb" else ""), deformable=True)
    service = Service(Settings(tmp_path / "work", allowed_roots=(source_dir,)))
    edit = dict(op="add_joint", kind="revolute", a=dict(part=1), b=dict(part=2),
                origin=[0, 0, 0], axis=[0, 0, 1], length=40., jid=901)
    if mode == "cnrb":
        edit["b"] = dict(nodal_rigid_body=90)
    elif mode == "nodes":
        edit["b"] = dict(nodes=[205, 206, 207, 208])
    elif mode == "motor":
        edit.update(kind="rotational_motor", motor=dict(curve=dict(lcid=70), type="velocity"))
    return service, source, edit


BAD = [
    ("jid", 901.75), ("jid", True), ("jid", False), ("jid", float("inf")),
    ("a.part", 1.75), ("a.part", True), ("b.part", 2.75),
    ("b.nodal_rigid_body", 90.75), ("b.nodal_rigid_body", True),
    ("b.nodes", 205.75), ("b.nodes", True), ("b.nodes", np.float32(205.5)),
    ("motor.curve.lcid", 70.75), ("motor.curve.lcid", True),
    ("local.raid", 1.75), ("local.raid", True), ("failure.cid", .75), ("failure.cid", True),
]


@pytest.mark.parametrize("field,value", BAD, ids=[f"{f}-{n}" for n, (f, _) in enumerate(BAD)])
def test_create_entities_rejects_ambiguous_joint_identity_atomically(tmp_path, field, value):
    mode = "cnrb" if "nodal_rigid_body" in field else "nodes" if field == "b.nodes" else "motor" if field.startswith("motor") else "part"
    service, source, edit = setup(tmp_path, mode)
    before, listing = source.read_bytes(), sorted(p.name for p in source.parent.iterdir())
    if field == "jid":
        edit["jid"] = value
    elif field == "b.nodes":
        edit["b"]["nodes"][0] = value
    elif field.startswith("motor"):
        edit["motor"]["curve"]["lcid"] = value
    else:
        parent, key = field.split(".")
        edit.setdefault(parent, {})[key] = value
    result = service.create_entities(str(source), [edit])
    assert result["status"] == "failed", "The requested identity was silently coerced"
    assert "integer identity" in result["error"]["message"], result["error"]
    assert not result["artifacts"] and source.read_bytes() == before
    assert sorted(p.name for p in source.parent.iterdir()) == listing


@pytest.mark.parametrize("mode", ["part", "cnrb", "nodes", "motor"])
@pytest.mark.parametrize("form", [int, float, str, np.int64, np.float32], ids=["int", "integral-float", "integer-text", "numpy-int", "numpy-integral-float"])
def test_existing_exact_integer_forms_keep_the_same_deck_bytes(tmp_path, mode, form):
    service, source, baseline = setup(tmp_path, mode)
    plain = service.create_entities(str(source), [baseline])
    assert plain["status"] == "succeeded", plain.get("error")
    edit = {**baseline, "jid": form(901), "a": dict(part=form(1)), "b": dict(baseline["b"])}
    if mode == "cnrb":
        edit["b"]["nodal_rigid_body"] = form(90)
    elif mode == "nodes":
        edit["b"]["nodes"] = [form(n) for n in (205, 206, 207, 208)]
    else:
        edit["b"]["part"] = form(2)
    if mode == "motor":
        edit["motor"] = dict(curve=dict(lcid=form(70)), type="velocity")
    result = service.create_entities(str(source), [edit])
    assert result["status"] == "succeeded", result.get("error")
    assert Path(result["data"]["main"]).read_bytes() == Path(plain["data"]["main"]).read_bytes()


def test_nonidentity_flags_and_continuous_values_are_not_reinterpreted(tmp_path):
    service, source, edit = setup(tmp_path)
    edit.update(local=dict(raid=1., lst=True), failure=dict(cid=0., tfail=.25), rps=.75, damp=.125)
    result = service.create_entities(str(source), [edit])
    assert result["status"] == "succeeded", result.get("error")
    deck = KeywordDeck.load(result["data"]["main"])
    joint = next(b for b in deck.iter_blocks() if b.name.startswith("*CONSTRAINED_JOINT_REVOLUTE_ID"))
    assert {key: deck.get(joint, key).value for key in ("raid", "lst", "cid", "tfail", "rps", "damp")} == {
        "raid": 1, "lst": 1, "cid": 0, "tfail": .25, "rps": .75, "damp": .125}


def test_invalid_joint_id_is_rejected_before_mutating_an_in_memory_deck(tmp_path):
    _, source, edit = setup(tmp_path)
    deck = KeywordDeck.load(source)
    original = source.read_bytes()
    blocks = len(list(deck.iter_blocks()))
    with pytest.raises(ValueError, match="integer identity"):
        add_joint(deck, "revolute", dict(part=1), dict(part=2), [0, 0, 0], axis=[0, 0, 1], length=40., jid=901.75)
    assert len(list(deck.iter_blocks())) == blocks and source.read_bytes() == original


@pytest.mark.parametrize("value", [3.75, True])
def test_legacy_selection_part_identity_is_checked_before_geometry(tmp_path, monkeypatch, value):
    from ls_prepost_mcp.domain.model import geometry

    service, source, edit = setup(tmp_path)
    edit["b"] = dict(select=dict(parts=[value]))
    monkeypatch.setattr(geometry, "select_nodes", lambda *a, **kw: pytest.fail("Ambiguous identity reached geometry"))
    result = service.create_entities(str(source), [edit])
    assert result["status"] == "failed" and "integer identity" in result["error"]["message"]
    assert not result["artifacts"]


def test_exact_legacy_selection_and_original_nested_identity_inputs_are_preserved(tmp_path):
    service, source, edit = setup(tmp_path)
    edit.update(b=dict(select=dict(parts=[3.])), local=dict(raid="1", lst=True), failure=dict(cid=0.))
    result = service.create_entities(str(source), [edit])
    assert result["status"] == "succeeded", result.get("error")
    assert edit["b"]["select"]["parts"] == [3.]
    assert type(edit["b"]["select"]["parts"][0]) is float
    assert edit["local"]["raid"] == "1" and type(edit["failure"]["cid"]) is float


def test_characterize_valid_integer_output_without_solver_or_native(tmp_path):
    outputs = {}
    for mode in ("part", "cnrb", "nodes", "motor"):
        directory = tmp_path / mode
        directory.mkdir()
        service, source, edit = setup(directory, mode)
        value = service.create_entities(str(source), [edit])
        assert value["status"] == "succeeded", value.get("error")
        data = Path(value["data"]["main"]).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        outputs[mode] = hashlib.sha256(data).hexdigest()
    capture = os.environ.get("LSPP_P12_CHARACTERIZATION")
    if capture:
        with Path(capture).open("x", encoding="utf8") as stream:
            json.dump(dict(scope="valid integer input output characterization, not physical/native evidence",
                           newline_policy="CRLF/CR normalized to LF before SHA256", outputs=outputs), stream)
    expected = Path(__file__).parent / "data/p12-valid-identity-output.json"
    if expected.is_file():
        assert outputs == json.loads(expected.read_text(encoding="utf8"))["outputs"]
