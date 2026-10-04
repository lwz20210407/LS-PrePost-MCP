from collections import Counter

import pytest

from ls_prepost_mcp.node_replacement import expected_references, mapped_geometry, patch_reference_cards


def test_replace_refuses_element_collapse_and_checks_mapped_shape():
    state = dict(nodes=[[1,0,0,0],[2,1,0,0],[3,0,1,0],[4,.1,.1,0]],
                 elements=[dict(type="shell",id=10,nodes=[1,2,3,3])])
    with pytest.raises(ValueError, match="collapse"):
        mapped_geometry(state,1,2)
    _, elements, affected = mapped_geometry(state,1,4)
    assert elements[("shell",10)] == (4,2,3,3) and affected == [dict(type="shell",id=10)]


def index():
    return dict(sets={
        ("node",10):dict(member_ids=[11,12],title="Keep"),
        ("segment",20):dict(segments=[dict(node_ids=[1,2,12],attributes=[0.,0.,0.,0.])])},
        spcs=[dict(target_type="node",target_id=12,coordinate_system=0,dofs=[1,0,0,0,0,0])],
        other=Counter(),unresolved=[])


def test_node_merge_remaps_sets_segments_and_spcs_without_mutating_input():
    before = index()
    expected = expected_references(before,12,11)
    assert before["sets"][("node",10)]["member_ids"] == [11,12]
    assert expected["sets"][("node",10)]["member_ids"] == [11]
    assert expected["sets"][("segment",20)]["segments"][0]["node_ids"] == [1,2,11]
    assert expected["spcs"][0]["target_id"] == 11
    before["spcs"].append(dict(target_type="node_set",target_id=10,coordinate_system=0,dofs=[1,0,0,0,0,0]))
    with pytest.raises(ValueError, match="overlapping"):
        expected_references(before,12,11)


def test_segment_collapse_is_rejected_before_native_edit():
    before = index()
    before["sets"][("segment",20)]["segments"][0]["node_ids"] = [1,11,12]
    with pytest.raises(ValueError, match="collapse"):
        expected_references(before,12,11)


def test_reference_patch_leaves_unrelated_bytes_and_spc_id_headers_untouched(tmp_path):
    source = tmp_path / "native.k"
    material = "*MAT_ELASTIC\r\n12,1.00000E-9,2.1000000E5,.30\r\n"
    source.write_bytes(("*KEYWORD\r\n"+material+
        "*SET_NODE_LIST_TITLE\r\nKeep\r\n10,0,0,0,0,MECH,1\r\n11,11\r\n"
        "*SET_SEGMENT\r\n20\r\n1,2,12,12,0,0,0,0\r\n"
        "*BOUNDARY_SPC_NODE_ID\r\n12,Constraint ID must stay\r\n12,0,1,0,0,0,0,0\r\n*END\r\n").encode())
    target = tmp_path / "patched.k"
    patch_reference_cards(source,target,expected_references(index(),12,11),12,11)
    text = target.read_bytes().decode()
    assert material in text and "12,Constraint ID must stay\r\n11,0,1,0,0,0,0,0" in text
    assert "1,2,11,11,0,0,0,0" in text
    assert source.read_bytes().decode().count("11,11") == 1


@pytest.mark.parametrize("fail_stage", ["reopen", "verify"])
def test_multistage_edit_failure_keeps_original_recovery_checkpoint(tmp_path, monkeypatch, fail_stage):
    from contextlib import nullcontext

    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    service = Service(Settings(tmp_path))
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    checkpoint = baseline / "model.k"
    checkpoint.write_text("*KEYWORD\n*END\n")
    meta = dict(process_alive=True, state="ready", model_kind="keyword", bridge_protocol=4,
                last_checkpoint=None, dirty=False)

    class Manager:
        def lock(self, sid):
            return nullcontext()

        def read(self, sid):
            return dict(meta)

        def save(self, sid, value):
            meta.update(value)

        def dispatch(self, *args, **kwargs):
            return dict(status="succeeded", job_directory=str(baseline), data={},
                        artifacts=[dict(path=str(checkpoint), kind="keyword")])

        def journal(self, *args):
            pass

    monkeypatch.setattr(service, "_session_manager", Manager)

    def finalize(before, result):
        meta["last_checkpoint"] = None  # Native model reopen invalidates the old model cache.
        if fail_stage == "reopen":
            raise ValueError("Native reopen failed")
        return result

    def verify(before, after):
        raise ValueError("Unexpected connectivity after reopen")

    result = service._gui_mesh_edit("session", "replace_gui_node", {}, [], verify, finalize_native=finalize)
    assert result["status"] == "failed"
    assert meta["state"] == "uncertain" and meta["dirty"]
    assert meta["last_checkpoint"] == str(checkpoint)
    assert result["baseline_checkpoint"] == str(checkpoint)
