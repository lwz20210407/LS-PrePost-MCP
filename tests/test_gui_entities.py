import copy
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import check_spc_conflicts, inspect_cards, set_members, verify_cards
from ls_prepost_mcp.gui_entities import selection_source
from ls_prepost_mcp.service import Service

pytest.importorskip("ansys.dyna.core")


def write(path, text):
    path.write_text("*KEYWORD\n" + text + "\n*END\n", encoding="utf-8")
    return inspect_cards(path)


def test_targeted_parser_preserves_title_and_ignores_only_member_padding(tmp_path):
    index = write(tmp_path / "sets.k", "*SET_NODE_LIST_TITLE\nSupport face\n100\n1,2,3,0,0,0,0,0\n*SET_PART_LIST\n100\n4,5")
    assert set_members(index, "node", 100) == [1, 2, 3]
    assert set_members(index, "part", 100) == [4, 5]
    assert index["sets"][("node", 100)]["title"] == "Support face"


def test_existing_constraints_are_checked_by_expanded_nodes_and_dofs(tmp_path):
    index = write(tmp_path / "spc.k", "*SET_NODE_LIST\n8\n1,2\n*BOUNDARY_SPC_SET\n8,0,1,0,0,0,0,0")
    with pytest.raises(ValueError, match="overlaps"):
        check_spc_conflicts(index, [2, 3], 0, [1, 0, 0, 0, 0, 0], 55)
    check_spc_conflicts(index, [2], 0, [0, 1, 0, 0, 0, 0], 55)
    check_spc_conflicts(index, [3], 0, [1, 0, 0, 0, 0, 0], 55)
    with pytest.raises(ValueError, match="coordinate"):
        check_spc_conflicts(index, [2], 9, [1, 0, 0, 0, 0, 0], 55)


def test_unknown_set_variant_is_not_silently_empty_or_collision_free(tmp_path):
    index = write(tmp_path / "general.k", "*SET_NODE_GENERAL\n8\nALL")
    with pytest.raises(ValueError, match="same-domain set"):
        set_members(index, "node", 8)


def test_entity_verification_rejects_unrequested_cards_or_member_changes(tmp_path):
    before = write(tmp_path / "before.k", "*TITLE\nOriginal model\n*NODE\n1,0,0,0\n2,1,0,0")
    after = write(tmp_path / "after.k", "*TITLE\nOriginal model\n*NODE\n1,0,0,0\n2,1,0,0\n*SET_NODE_LIST\n20\n1,2")
    target = dict(entity_type="node", set_id=20, member_ids=[1, 2])
    assert verify_cards(before, after, new_set=target)["entity_references_verified"]
    bad = copy.deepcopy(after)
    bad["sets"][("node", 20)]["member_ids"] = [1]
    with pytest.raises(ValueError, match="members"):
        verify_cards(before, bad, new_set=target)
    bad = copy.deepcopy(after)
    bad["other"][("*MAT_NEW", "hash")] = 1
    with pytest.raises(ValueError, match="unrelated"):
        verify_cards(before, bad, new_set=target)


@pytest.mark.parametrize("body", ["*SET_NODE_LIST\n1\n1,1", "*SET_NODE_LIST\n1\n1\n*SET_NODE_LIST\n1\n2"])
def test_duplicate_members_or_domain_ids_rejected(tmp_path, body):
    with pytest.raises(ValueError, match="Duplicate"):
        write(tmp_path / "dup.k", body)


def test_explicit_constraint_id_and_dof_readback_must_match(tmp_path):
    before = write(tmp_path / "before.k", "*SET_NODE_LIST\n8\n1,2")
    after = write(tmp_path / "after.k", "*SET_NODE_LIST\n8\n1,2\n*BOUNDARY_SPC_SET_ID\n3,Fixture\n8,0,1,0,0,0,0,0")
    expected = dict(target_type="node_set", target_id=8, constraint_id=3, title="Fixture",
                    coordinate_system=0, dofs=[1, 0, 0, 0, 0, 0])
    assert verify_cards(before, after, new_spcs=[expected])["entity_references_verified"]
    with pytest.raises(ValueError, match="Constraint ID"):
        check_spc_conflicts(after, [7], 0, [1, 0, 0, 0, 0, 0], 3)
    expected["dofs"] = [0, 1, 0, 0, 0, 0]
    with pytest.raises(ValueError, match="SPC rows"):
        verify_cards(before, after, new_spcs=[expected])


def test_native_packed_spc_id_pairs_and_comma_titles_are_all_retained(tmp_path):
    header1 = f'{1003:10d}Node X, side A'
    header2 = f'{1004:10d}Node X, side B'
    index = write(tmp_path / "packed.k", f"*BOUNDARY_SPC_NODE_ID\n{header1}\n9,0,1,0,0,0,0,0\n{header2}\n10,0,1,0,0,0,0,0")
    assert [(r["target_id"], r["constraint_id"], r["title"]) for r in index["spcs"]] == [
        (9, 1003, "Node X, side A"), (10, 1004, "Node X, side B")]
    with pytest.raises(ValueError, match="Incomplete SPC"):
        write(tmp_path / "truncated.k", "*BOUNDARY_SPC_NODE_ID\n1003,No data")


def test_selection_input_requires_owned_successful_domain(tmp_path):
    class Manager:
        def directory(self, sid):
            return tmp_path / sid
        def read(self, sid):
            return dict(model_generation="current")
    directory = tmp_path / "session" / "requests" / "job"
    directory.mkdir(parents=True)
    data = dict(session_id="session", status="succeeded", model_generation="current",
                verification=dict(entity_type="node", selected_ids=[1, 2]))
    (directory / "operation.json").write_text(json.dumps(data))
    (directory / "after.json").write_text("{}")
    assert selection_source(Manager(), "session", str(directory), "node")[0] == [1, 2]
    with pytest.raises(ValueError, match="entity type"):
        selection_source(Manager(), "session", str(directory), "part")
    with pytest.raises(ValueError, match="owned request"):
        selection_source(Manager(), "another", str(directory), "node")
    data["model_generation"] = "old"
    (directory / "operation.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="older model"):
        selection_source(Manager(), "session", str(directory), "node")


@pytest.mark.parametrize("dofs", [[0]*6, [1]*5, [True]*6, [2,0,0,0,0,0]])
def test_bad_constraint_parameters_rejected_before_native_work(tmp_path, dofs):
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError, match="binary DOFs"):
        service.create_gui_spc("unused", 1, "Constraint", dofs, node_ids=[1])


def test_multi_node_spc_emits_distinct_native_id_cards(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    def edit(sid, action, params, commands, verify, precheck, postcheck, preflight, **kwargs):
        commands({}, tmp_path)
        text = (tmp_path / "entity-spc.k").read_text()
        assert text.count("*BOUNDARY_SPC_NODE_ID") == 2
        rows = inspect_cards(tmp_path / "entity-spc.k")["spcs"]
        assert [(r["target_id"], r["constraint_id"]) for r in rows] == [(5, 100), (9, 101)]
    monkeypatch.setattr(service, "_gui_mesh_edit", edit)
    service.create_gui_spc("unused", 100, "Support", [1, 0, 0, 0, 0, 0], node_ids=[9, 5])


def test_all_allocated_spc_ids_checked_before_native_dispatch(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    path = tmp_path / "baseline.k"
    write(path, "*BOUNDARY_SPC_NODE_ID\n101,Existing\n99,0,1,0,0,0,0,0")
    def edit(sid, action, params, commands, verify, precheck, postcheck, preflight, **kwargs):
        preflight(path)
        pytest.fail("Secondary allocated constraint ID collision must reject before dispatch")
    monkeypatch.setattr(service, "_gui_mesh_edit", edit)
    with pytest.raises(ValueError, match="Constraint ID already"):
        service.create_gui_spc("unused", 100, "Support", [1, 0, 0, 0, 0, 0], node_ids=[5, 9])


@pytest.mark.parametrize("source_recorded", [True, False])
def test_recording_links_selection_job_to_new_replay_result(tmp_path, monkeypatch, source_recorded):
    import ls_prepost_mcp.sessions as sessions
    monkeypatch.setattr(sessions, "alive", lambda _: True)
    service = Service(Settings(tmp_path))
    manager = service._session_manager()
    sid = "c" * 32
    root = manager.directory(sid)
    root.mkdir(parents=True)
    manager.save(sid, dict(session_id=sid, process={}, state="ready",
                          recording=dict(id="d"*32, initial_model=None, native_offset=None, journal_offset=0)))
    selected = str(root / "requests" / "source")
    if source_recorded:
        manager.journal(sid, dict(action="select_gui_entities", parameters=dict(entity_type="node", entity_ids=[1]),
                                 result=dict(status="succeeded", job_directory=selected)))
    manager.journal(sid, dict(action="create_gui_entity_set", parameters=dict(entity_type="node", set_id=10,
                             title="Support", entity_ids=None, selection_job=selected), result=dict(status="succeeded")))
    result = service.stop_session_recording(sid)
    workflow = json.loads(Path(result["workflow"]).read_text())
    if not source_recorded:
        assert result["status"] == "needs_review" and workflow["unrecognized_commands"]
        return
    assert workflow["steps"][1]["arguments"]["selection_job"] == {"$result": "step1", "path": ["job_directory"]}
