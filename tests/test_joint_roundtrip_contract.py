"""P12 fixture and readback controls: schema-backed fields, no native process."""

import copy
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, joint_checks
from tests.test_joint_instance_reader import repeated
from tools.verify_p12_joint_roundtrip import (
    KINDS,
    _engine,
    compare,
    fixture,
    joint_records,
    plain,
    prepare_case,
    snapshot,
    verify_native,
)


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("p12-readback")
    return {name: prepare_case(name, root / name) for name in ("pilot", "nine_types", "body_modes")}


def test_handwritten_fixtures_cover_nine_kinds_and_both_attachment_directions(prepared):
    nine = prepared["nine_types"]["spec"]["expected"]
    assert {item["kind"] for item in nine["joints"]} == KINDS
    assert len(nine["joints"]) == 11  # nine types plus two motor support constraints
    bodies = prepared["body_modes"]["spec"]["expected"]
    assert [item["pid"] for item in bodies["cnrbs"]] == [900, 901, 902, 903]
    for item in prepared.values():
        assert compare(item["edited"], item["spec"]["expected"]) == []
        assert item["source"].read_bytes() != item["edited"].read_bytes()


def _copy_model(prepared, tmp_path, mutate):
    deck = KeywordDeck.load(prepared["edited"])
    mutate(deck)
    saved = deck.save_as(tmp_path / "copy")
    return Path(saved["main"])


@pytest.mark.parametrize("field,value", [("n1", 111), ("rps", .5), ("damp", .25), ("jid", 902)])
def test_native_counts_alone_cannot_hide_a_wrong_definition(prepared, tmp_path, field, value):
    def mutate(deck):
        joint = next(b for b in deck.iter_blocks() if b.name.startswith("*CONSTRAINED_JOINT_"))
        deck.set(joint, field, value)
    path = _copy_model(prepared["pilot"], tmp_path, mutate)
    assert compare(path, fixture("pilot")["expected"])


def test_wrong_side_binding_is_not_hidden_by_coincident_node_pairs(prepared, tmp_path):
    def mutate(deck):
        entry = deck.find("*CONSTRAINED_EXTRA_NODES_SET", pid=10)[0]
        deck.set(entry[0], "pid", 20, row=entry[1])
    path = _copy_model(prepared["pilot"], tmp_path, mutate)
    assert any(item["field"] == "extra_nodes" for item in compare(path, fixture("pilot")["expected"]))


def test_existing_mesh_part_connectivity_and_node_coordinates_are_also_protected(prepared, tmp_path):
    def mutate(deck):
        solid, key = deck.find("*ELEMENT_SOLID", eid=1001)[0]
        deck.set(solid, "pid", 20, row=key)
        node, key = deck.find("*NODE", nid=109)[0]
        deck.set(node, "z", 1., row=key)
    path = _copy_model(prepared["pilot"], tmp_path, mutate)
    fields = {item["field"] for item in compare(path, fixture("pilot")["expected"])}
    assert "solids" in fields and "Node 109.z" in fields


def test_single_and_merged_same_kind_blocks_use_the_same_static_expectations(prepared, tmp_path):
    def merge(deck):
        blocks = [b for b in deck.iter_blocks() if b.name == "*CONSTRAINED_JOINT_REVOLUTE_ID"]
        assert len(blocks) == 4
        text = blocks[0].lines[0] + "".join("".join(block.lines[1:]) for block in blocks)
        for block in blocks:
            deck.delete(block, force=True)
        deck.insert(text)
    path = _copy_model(prepared["body_modes"], tmp_path, merge)
    assert compare(path, prepared["body_modes"]["spec"]["expected"]) == []


def test_merged_motor_parm_cards_are_read_by_existing_boundaries_and_fields(tmp_path):
    deck = repeated(tmp_path)
    block = next(b for b in deck.iter_blocks() if b.name.startswith("*CONSTRAINED_JOINT_"))
    records = joint_records(deck, block)
    assert [(r["jid"], r["n1"], r["lcid"], r["type"], r["rps"], r["damp"]) for r in records] == [
        (7, 301, 70, 0, .75, .125), (8, 301, 70, 0, .75, .125)]


def test_duplicate_joint_identity_or_missing_cards_never_selects_only_the_first_record(prepared, tmp_path):
    def duplicate(deck):
        joint = next(b for b in deck.iter_blocks() if b.name.startswith("*CONSTRAINED_JOINT_"))
        deck.insert(joint.text())
    path = _copy_model(prepared["pilot"], tmp_path, duplicate)
    with pytest.raises(ValueError, match="duplicate Joint"):
        snapshot(path)


def test_incomplete_merged_instance_cannot_be_mistaken_for_success(tmp_path):
    deck = repeated(tmp_path)
    block = next(b for b in deck.iter_blocks() if b.name.startswith("*CONSTRAINED_JOINT_"))
    block.lines.pop()
    with pytest.raises(ValueError):
        joint_records(deck, block)


def test_missing_joint_and_motor_curve_changes_are_differences(prepared, tmp_path):
    def mutate(deck):
        motor = deck.find("*CONSTRAINED_JOINT_ROTATIONAL_MOTOR_ID", jid=908)[0][0]
        deck.set(motor, "type", 1)
        curve = deck.find("*DEFINE_CURVE", lcid=701)[0][0]
        deck.set_points(curve, [(0., 3.), (1., 3.)])
        other = deck.find("*CONSTRAINED_JOINT_SPHERICAL_ID", jid=901)[0][0]
        deck.delete(other, force=True)
    path = _copy_model(prepared["nine_types"], tmp_path, mutate)
    fields = {item["field"] for item in compare(path, fixture("nine_types")["expected"])}
    assert {"joint_ids", "Joint 908.type", "curves"} <= fields


def test_unknown_joint_passthrough_does_not_count_as_a_recognized_definition(prepared, tmp_path):
    def mutate(deck):
        deck.insert("*CONSTRAINED_JOINT_UNVERIFIED_SENTINEL\n         1         2\n")
    path = _copy_model(prepared["pilot"], tmp_path, mutate)
    with pytest.raises(ValueError, match="Unverified Joint keyword"):
        snapshot(path)
    with pytest.raises(ValueError, match="Unsupported Joint"):
        joint_checks.joint_instances(KeywordDeck.load(path), KeywordDeck.load(path).blocks("*CONSTRAINED_JOINT_UNVERIFIED_SENTINEL")[0])


def test_readback_is_not_allowed_to_follow_an_include_back_to_its_input(prepared, tmp_path):
    readback = tmp_path / "readback.k"
    readback.write_text("*KEYWORD\n*INCLUDE\n" + str(prepared["pilot"]["edited"]) + "\n*END\n", encoding="utf8")
    with pytest.raises((ValueError, PermissionError)):
        snapshot(readback)


def test_existing_export_include_policy_is_preserved(prepared, tmp_path, monkeypatch):
    service = prepared["pilot"]["service"]
    root = service.settings.workspace / "include-refusal"
    root.mkdir()
    child = root / "mesh.k"
    child.write_bytes(prepared["pilot"]["edited"].read_bytes())
    main = root / "main.k"
    main.write_text("*KEYWORD\n*INCLUDE\nmesh.k\n*END\n", encoding="utf8")
    # Resolve a trusted host path without starting any process. Include rejection
    # must occur before a native job is created or the batch executor is reached.
    monkeypatch.setattr(type(service.settings), "native_executable", lambda self: main)
    before = service.jobs.list()
    with pytest.raises(ValueError, match="flatten the include-tree"):
        service.export_keyword(str(main))
    assert service.jobs.list() == before


def test_dirty_or_unavailable_git_identity_rejects_before_any_native_call(prepared, monkeypatch):
    service = prepared["pilot"]["service"]
    monkeypatch.setattr(service, "save_model", lambda *a, **kw: pytest.fail("No native call authorized"))
    with pytest.raises(ValueError, match="clean actual Git"):
        verify_native(prepared["pilot"], dict(actual_git_head="uncommitted", working_tree_dirty=True))


def test_failure_differences_are_json_safe_and_expected_data_is_not_recomputed(prepared):
    expected = copy.deepcopy(prepared["pilot"]["spec"]["expected"])
    expected["extra_nodes"][0]["members"] = [999]
    differences = compare(prepared["pilot"]["edited"], expected)
    serialized = json.dumps(plain(differences), allow_nan=False)
    assert "extra_nodes" in serialized and "999" in serialized


@pytest.mark.parametrize("fault", ["job_id", "operation", "status", "error", "stage", "backend", "checks", "pid", "graphics", "argv", "returncode", "timed_out"])
def test_process_evidence_cannot_be_replaced_by_an_output_echo(fault):
    manifest = dict(job_id="abc", action="export_keyword", engine_result=dict(job_id="abc", operation="export_keyword",
        status="unverified", stage="execution", backend="lsprepost", error=None,
        data=dict(pid=123, graphics=False, argv=["fake", "-nographics"], returncode=0, timed_out=False)))
    _engine(manifest)  # Valid evidence control before changing the one selected field.
    engine = manifest["engine_result"]
    if fault in ("job_id", "operation", "status", "stage", "backend"):
        engine[fault] = "wrong"
    elif fault == "error":
        engine["error"] = dict(message="native failure")
    elif fault == "checks":
        engine["checks"] = [dict(name="failed fixture", status="failed", required=True)]
    else:
        engine["data"][fault] = dict(pid=None, graphics=True, argv=[], returncode=1, timed_out=True)[fault]
    with pytest.raises(ValueError, match="headless execution evidence"):
        _engine(manifest)
