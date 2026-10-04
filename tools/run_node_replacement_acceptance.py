"""Opt-in native node/connection replacement with supported references and rejection cases."""

import argparse
import uuid
from pathlib import Path

from run_topology_selection_acceptance import fixture

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import inspect_cards
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service


def model(path, extra=""):
    fixture(path)
    path.write_text(path.read_text().replace("*END", "*SET_NODE_LIST\n100\n11,12\n*SET_NODE_LIST\n101\n12\n"
        "*SET_SEGMENT\n200\n4,5,12,12\n*BOUNDARY_SPC_NODE_ID\n12,Source constraint\n12,0,1,0,0,0,0,0\n"
        "*BOUNDARY_SPC_SET\n100,0,0,1,0,0,0,0\n" + extra + "*END"), encoding="ascii")


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("node-replace-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    source = root / "source.k"
    model(source)
    original = fingerprint(source)
    service = Service(Settings(root, Path(executable), timeout=120))
    sid = service.start_gui_session()["session_id"]
    checks = []

    def checked(name, result):
        atomic_json(root / (name+".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        checks.append(name)
        print(name, flush=True)
        return result

    def output(result):
        return Path(next(a["path"] for a in result["artifacts"] if a["kind"] == "keyword"))

    def assert_refs(path, target):
        cards = inspect_cards(path)
        assert cards["sets"][("node",100)]["member_ids"] == sorted({11,target})
        assert cards["sets"][("node",101)]["member_ids"] == [target]
        assert cards["sets"][("segment",200)]["segments"][0]["node_ids"] == [4,5,target]
        row = next(r for r in cards["spcs"] if r["target_type"] == "node")
        assert row["target_id"] == target and row["constraint_id"] == 12

    def rejected(name, source_id, target_id, text):
        before = checked(name+"-before", service.inspect_gui_mesh(sid,include_entities=True))["data"]
        try:
            service.replace_gui_node(sid,source_id,target_id,"mm")
        except ValueError as exc:
            assert text in str(exc), str(exc)
        else:
            raise AssertionError("Expected pre-edit rejection")
        after = checked(name+"-after", service.inspect_gui_mesh(sid,include_entities=True))["data"]
        assert before["nodes"] == after["nodes"] and before["elements"] == after["elements"]
        assert service.inspect_gui_session(sid)["state"] == "ready"

    try:
        service.show_gui_session(sid,maximize=True)
        checked("open",service.open_in_gui_session(sid,str(source)))
        checked("view",service.set_gui_display(sid,view="isometric",center=True,capture=False))
        before = checked("topology-before",service.select_gui_shell_topology(sid,[101],feature_angle=30.))
        assert before["verification"]["selected_ids"] == [101,205,517]
        service.start_session_recording(sid)
        replaced = checked("replace",service.replace_gui_node(sid,12,11,"mm"))
        assert_refs(output(replaced),11)
        record = checked("recording",service.stop_session_recording(sid))
        assert record["managed_steps"] == 1
        after = checked("topology-after",service.select_gui_shell_topology(sid,[101],feature_angle=30.))
        assert after["verification"]["selected_ids"] == [101,205,413,517]
        checked("reopen",service.open_in_gui_session(sid,str(output(replaced))))
        assert_refs(output(checked("reopened-checkpoint",service.checkpoint_gui_session(sid))),11)
        template = checked("template",service.parameterize_workflow(record["workflow"],
            [dict(step_id="step1",path=["target_node_id"],parameter="target")]))
        replay = checked("replay",service.run_workflow(template["artifacts"][0]["path"],dict(target=10),sid))
        assert_refs(output(replay["data"]["steps"]["step1"]),10)
        checked("fresh-source",service.open_in_gui_session(sid,str(source)))
        rejected("element-collapse",1,2,"collapse")
        for name, extra, message in [
            ("segment-collapse","*SET_SEGMENT\n201\n11,12,0,0\n","collapse"),
            ("spc-overlap","*BOUNDARY_SPC_NODE\n11,0,1,0,0,0,0,0\n","overlapping"),
            ("unsupported-load","*LOAD_NODE_POINT\n12,1,9,1.0\n*DEFINE_CURVE\n9\n0.0,0.0\n1.0,1.0\n","not yet verified")]:
            path = root / (name+".k")
            model(path,extra)
            checked(name+"-open",service.open_in_gui_session(sid,str(path)))
            rejected(name,12,11,message)
        checked("empty",service.reset_gui_session(sid))
        checked("hex",service.gui_session_action(sid,"create_solid_box",dict(divisions=[1,1,1],size=[2.,2.,2.],units="mm")))
        checked("target-node",service.create_gui_nodes(sid,[dict(id=100,coordinates=[.1,0.,0.])],"mm"))
        solid = checked("hex-replacement",service.replace_gui_node(sid,1,100,"mm"))
        assert solid["verification"]["affected_elements"] == [dict(type="solid",id=1)]
        assert fingerprint(source) == original
        atomic_json(root / "acceptance.json",dict(status="succeeded",checks=checks,source_unchanged=True,
            scope="4.13.4 visible Tri3/Quad4 and Hex8 node replacement, full bounded geometry comparison, supported Node/Segment/SPC repair via fresh copy/native reopen, constraint-ID preservation, topology change, parameter replay and pre-edit collapse/conflict/unsupported-reference rejection. No all-keyword/solver/large-model certification."))
    finally:
        atomic_json(root / "closed.json",service.close_gui_session(sid,save_checkpoint=False))
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",required=True)
    parser.add_argument("--executable",required=True)
    args = parser.parse_args()
    print(accept(args.workspace,args.executable))
