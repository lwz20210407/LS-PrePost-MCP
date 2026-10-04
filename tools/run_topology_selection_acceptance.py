"""Opt-in visible native shell topology -> Segment set -> pressure -> replay/reopen."""

import argparse
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service


def fixture(path):
    nodes = [(1,0,0,0),(2,1,0,0),(3,2,0,0),(4,0,1,0),(5,1,1,0),(6,2,1,0),
             (7,2.5,0,.866025403784),(8,2.5,1,.866025403784),(9,-1,1,0),(10,-1,2,0),
             (11,0,2,0),(12,.5,2,0)]
    path.write_text("*KEYWORD\n*NODE\n" + "".join(",".join(map(str,n))+"\n" for n in nodes) +
        "*ELEMENT_SHELL\n101,1,1,2,5,4\n205,1,2,3,6,5\n309,2,3,7,8,6\n413,1,4,9,10,11\n517,1,4,5,12,12\n"
        "*PART\nPlane\n1,1,1\n*PART\nFold\n2,1,1\n*SECTION_SHELL\n1,2\n1,1,1,1\n*MAT_ELASTIC\n1,1,1000,.3\n*END\n", encoding="ascii")


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("topology-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    source = root / "folded.k"
    fixture(source)
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

    def selected(name, expected, **kwargs):
        result = checked(name, service.select_gui_shell_topology(sid, [101], **kwargs))
        assert result["verification"]["selected_ids"] == expected
        return result

    try:
        service.show_gui_session(sid, maximize=True)
        checked("open", service.open_in_gui_session(sid, str(source)))
        checked("legacy-snapshot", service.inspect_gui_mesh(sid, include_entities=True))
        checked("view", service.set_gui_display(sid, view="isometric", center=True, capture=False))
        selected("adjacent1", [101,205,413,517], mode="adjacent", rings=1)
        selected("adjacent2", [101,205,309,413,517], mode="adjacent", rings=2)
        service.start_session_recording(sid)
        pick = selected("feature30", [101,205,517], feature_angle=30.)
        segments = checked("segments", service.create_gui_segment_set(sid,700,"Smooth faces","shell_faces","mm",
                                                                    selection_job=pick["job_directory"]))
        assert segments["verification"]["segment_count"] == 3
        checked("pressure", service.create_gui_segment_pressure(sid,700,800,"Pressure",[[0.,0.],[1.,10.]],"s","MPa","mm"))
        record = checked("recording", service.stop_session_recording(sid))
        assert record["managed_steps"] == 3
        template = checked("template", service.parameterize_workflow(record["workflow"],
            [dict(step_id="step1",path=["feature_angle"],parameter="angle")]))
        replay = checked("replay", service.run_workflow(template["artifacts"][0]["path"],dict(angle=80.),sid))
        assert replay["data"]["steps"]["step2"]["verification"]["segment_count"] == 4
        saved = checked("checkpoint", service.checkpoint_gui_session(sid))["artifacts"][0]["path"]
        checked("reopen", service.open_in_gui_session(sid,saved))
        assert checked("reopened-set", service.inspect_gui_entity_sets(sid,"segment",700))["data"]["total"] == 4
        checked("hide-part", service.set_gui_part_visibility(sid,"hide",[2]))
        selected("hidden-part-boundary", [101,205,517], feature_angle=80.)
        checked("show-part", service.set_gui_part_visibility(sid,"show",[2]))
        checked("hide-shell", service.set_gui_entity_visibility(sid,"shell","hide",[205]))
        selected("hidden-shell-boundary", [101,517], feature_angle=80.)
        try:
            service.select_gui_shell_topology(sid,[205])
        except ValueError as exc:
            assert "visible" in str(exc)
        else:
            raise AssertionError("Hidden seed must be rejected")
        assert service.inspect_gui_session(sid)["state"] == "ready"
        checked("show-shell", service.set_gui_entity_visibility(sid,"shell","show",[205]))
        checked("reverse-normal", service.reverse_gui_shell_normals(sid,"mm",[205]))
        selected("reversed-normal-propagation", [101,205,309,517], feature_angle=80.)
        assert fingerprint(source) == original
        atomic_json(root/"acceptance.json",dict(status="succeeded",checks=checks,source_unchanged=True,
            scope="Visible4.13.4 keyword Tri3/Quad4 node-ring adjacency and shared-edge local unoriented-angle propagation; part/Blank boundaries, hidden seed refusal, Segment+pressure parameter replay/reopen. No result-state topology, adaptive, arbitrary nonmanifold or large-topology runtime certification."))
    finally:
        atomic_json(root/"closed.json",service.close_gui_session(sid,save_checkpoint=False))
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",required=True)
    parser.add_argument("--executable",required=True)
    args = parser.parse_args()
    print(accept(args.workspace,args.executable))
