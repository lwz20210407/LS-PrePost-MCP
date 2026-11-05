"""P05 public identity inputs must not select a different curve, set, part or node."""

import copy
import hashlib
import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck, loads
from ls_prepost_mcp.domain.model.fields import FieldError
from ls_prepost_mcp.service import Service
from tests.test_keyword_engine_setup import _model
from tests.test_keyword_engine_setup import test_p05_story_and_all_nine_kinds as _nine_kind_story


def source_model(directory, *, cnrb=False, rigid=False):
    directory.mkdir()
    path = _model(directory)
    text = path.read_text(encoding="ascii")
    if cnrb:
        text = text.replace("block\n         1         1         1\n", "block\n        10         1         1\n")
        text = text.replace("       1       1       1       2", "       1      10       1       2")
    if rigid:
        text = text.replace("*MAT_ELASTIC", "*MAT_RIGID")
    extra = ("*SET_NODE_LIST\n         1\n         1         2\n"
             "*SET_SEGMENT\n         1\n         1         2         3         4\n"
             "*SET_PART_LIST\n         1\n" + ("        10\n" if cnrb else "         1\n") +
             "*DEFINE_CURVE\n         1\n                 0.0                 0.0\n"
             "                 1.0                 1.0\n"
             "*DEFINE_COORDINATE_SYSTEM\n1,0,0,0,1,0,0\n0,1,0\n")
    path.write_text(text.replace("*END\n", extra + "*END\n"), encoding="ascii", newline="\n")
    return path


def operation(case, bad):
    spec = {"op": "add_boundary", "units": "mm-ms-kg"}
    if case == "curve_lcid":
        spec.update(kind="nodal_load", target={"node_set": 1}, dof="z", curve={"lcid": bad})
    elif case in ("pressure_segment_sid", "non_reflecting_segment_sid"):
        spec.update(kind="pressure" if case.startswith("pressure") else "non_reflecting",
                    target={"segment_set": bad})
        if spec["kind"] == "pressure":
            spec["curve"] = {"lcid": 1}
    elif case == "prescribed_rigid_pid":
        spec.update(kind="prescribed_motion", target={"rigid_part": bad}, dof="x",
                    motion="displacement", curve={"lcid": 1})
    elif case in ("initial_part_pid", "initial_partset_sid"):
        spec.update(kind="initial_velocity", velocity=[0., 0., 1.],
                    target={"part" if case == "initial_part_pid" else "part_set": bad})
    elif case == "cnrb_pid":
        spec.update(kind="cnrb", pid=bad, target={"nodes": [1, 2]})
    elif case == "legacy_select_parts":
        spec.update(kind="spc", dofs="all", target={"select": {"parts": [bad]}})
    elif case == "exterior_parts":
        spec.update(kind="pressure", target={"exterior": {"parts": [bad], "direction": [0, 0, 1]}},
                    curve={"lcid": 1})
    elif case == "segment_member_nid":
        spec.update(kind="non_reflecting", target={"segments": [[bad, 2, 3, 4]]})
    elif case == "spc_cid":
        spec.update(kind="spc", dofs="all", cid=bad, target={"node_set": 1})
    else:
        raise AssertionError(case)
    return spec


CASES = ("curve_lcid", "pressure_segment_sid", "non_reflecting_segment_sid", "prescribed_rigid_pid",
         "initial_part_pid", "initial_partset_sid", "cnrb_pid", "legacy_select_parts", "exterior_parts",
         "segment_member_nid", "spc_cid")


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("value", [1.75, True])
def test_public_ambiguous_boundary_identity_is_rejected_without_publishing(tmp_path, case, value):
    bad = 9.75 if case == "cnrb_pid" and value is not True else value
    source = source_model(tmp_path / "source", cnrb=case == "cnrb_pid", rigid=case == "prescribed_rigid_pid")
    before = source.read_bytes()
    names = sorted(p.name for p in source.parent.iterdir())
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    result = service.create_entities(str(source), [operation(case, bad)])
    assert result["status"] == "failed", "An identity must not silently bind to another entity"
    assert not result["artifacts"] and source.read_bytes() == before
    assert sorted(p.name for p in source.parent.iterdir()) == names


@pytest.mark.parametrize("target", [{"node_set": 1.75}, {"node_set": True}, {"nodes": [1.75]},
                                    {"nodes": [True]}, {"selector": {"entity_type": "node",
                                     "predicate": {"kind": "ids", "ids": [True]}}}])
def test_existing_strict_node_target_paths_stay_rejected(tmp_path, target):
    source = source_model(tmp_path / "source")
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    result = service.create_entities(str(source), [dict(op="add_boundary", kind="spc", units="mm-ms-kg",
                                                      dofs="all", target=copy.deepcopy(target))])
    assert result["status"] == "failed" and not result["artifacts"]


@pytest.mark.parametrize("case", ["prescribed_rigid_pid", "pressure_segment_sid", "cnrb_pid", "spc_cid"])
def test_invalid_scalar_identity_cannot_leave_sets_or_curves_in_memory(tmp_path, case):
    source = source_model(tmp_path / "source", cnrb=case == "cnrb_pid", rigid=case == "prescribed_rigid_pid")
    deck = KeywordDeck.load(source)
    before = deck.main.text(), list(deck.changes), deck.modified_files()
    spec = operation(case, 9.75 if case == "cnrb_pid" else 1.75)
    if case in ("prescribed_rigid_pid", "pressure_segment_sid"):
        spec["curve"] = {"points": [[0., 0.], [1., 1.]]}
    if case == "spc_cid":
        spec["target"] = {"nodes": [1, 2]}
    params = {k: v for k, v in spec.items() if k not in ("op", "kind", "units")}
    with pytest.raises((FieldError, ValueError)):
        loads.KINDS[spec["kind"]](deck, **params)
    assert (deck.main.text(), deck.changes, deck.modified_files()) == before


@pytest.mark.parametrize("value", [1, 1., "1", "+1", np.int64(1), np.float32(1), Decimal("1"), Fraction(1, 1)])
def test_valid_integral_curve_reference_forms_remain_exact(tmp_path, value):
    deck = KeywordDeck.load(source_model(tmp_path / "source"))
    result = loads.add_nodal_load(deck, {"node_set": 1}, "z", {"lcid": value}, sf=-2.)
    block = deck.blocks("*LOAD_NODE_SET")[0]
    assert result["lcid"] == deck.get(block, "lcid").value == 1
    assert deck.get(block, "sf").value == -2.


def test_dof_control_flags_and_global_or_all_node_zero_values_are_preserved(tmp_path):
    deck = KeywordDeck.load(source_model(tmp_path / "source"))
    loads.add_spc(deck, {"node_set": 1}, ["x", "rz"], cid=0)
    spc = deck.blocks("*BOUNDARY_SPC_SET")[0]
    assert deck.get(spc, "cid").value == 0
    assert [bool(deck.get(spc, "dof" + dof).value) for dof in ("x", "y", "z", "rx", "ry", "rz")] == [
        True, False, False, False, False, True]
    loads.add_prescribed_motion(deck, {"node_set": 1}, "x", "velocity", {"lcid": 1})
    assert deck.get(deck.blocks("*BOUNDARY_PRESCRIBED_MOTION_SET")[0], "vad").value == 0
    loads.add_rigid_wall(deck, [0, 0, -1], [0, 0, 1])
    assert deck.get(deck.blocks("*RIGIDWALL_PLANAR")[0], "nsid").value == 0


def test_valid_nine_kind_output_matches_the_old_product_lf_golden(tmp_path):
    _nine_kind_story(tmp_path)
    golden = json.loads((Path(__file__).parent / "data/p05-valid-identity-output.json").read_text(encoding="utf8"))
    raw = (tmp_path / "out/main.k").read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    assert hashlib.sha256(raw).hexdigest() == golden["sha256"]
