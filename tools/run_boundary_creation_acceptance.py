"""Opt-in native pressure and3D/modern2D/legacy2D nonreflecting workflow checks."""

import argparse
import json
import uuid
from pathlib import Path

from run_segment_creation_acceptance import planar_fixture

from ls_prepost_mcp.boundary_cards import inspect_boundary_cards
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-boundary-acceptance-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    service = Service(Settings(root, Path(executable), timeout=180))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    cases = []

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        cases.append(name)
        print(name, flush=True)
        return result

    def rejected(name, operation, message):
        try:
            operation()
        except ValueError as exc:
            assert message in str(exc), str(exc)
            assert service.inspect_gui_session(sid)["state"] == "ready"
            atomic_json(root / (name + ".json"), dict(expected_rejection=str(exc)))
            cases.append(name)
            print(name, flush=True)
        else:
            raise AssertionError("Expected rejection: " + name)

    def surface(set_id, direction=None, reverse=False, source="solid_exterior"):
        return service.create_gui_segment_set(sid, set_id, "Surface " + str(set_id), source, "mm",
                                             element_ids=[1,2], normal_direction=direction, reverse=reverse)

    def pressure(set_id, curve_id, **kwargs):
        return service.create_gui_segment_pressure(sid, set_id, curve_id, "Pressure " + str(curve_id),
                    [[0.,0.],[1.,1.23456789],[2.,0.]], "ms", "MPa", "mm", **kwargs)

    def reopen(name, result, ordered=False):
        saved = next(a["path"] for a in result["artifacts"] if a["kind"] == "keyword")
        expected = inspect_boundary_cards(Path(saved), include_ordered_node_sets=ordered)
        checked(name, service.open_in_gui_session(sid, saved))
        checkpoint = checked(name + "-checkpoint", service.checkpoint_gui_session(sid))
        new = next(a["path"] for a in checkpoint["artifacts"] if a["kind"] == "keyword")
        assert inspect_boundary_cards(Path(new), include_ordered_node_sets=ordered) == expected

    try:
        service.show_gui_session(sid, maximize=True)
        checked("box", service.gui_session_action(sid, "create_solid_box", dict(divisions=[2,1,1], size=[2.,1.,1.], units="mm")))
        service.start_session_recording(sid)
        selected = checked("selection", service.select_gui_entities(sid, "solid", [1,2]))
        checked("top", service.create_gui_segment_set(sid, 100, "Top", "solid_exterior", "mm",
                    selection_job=selected["job_directory"], normal_direction=[0.,0.,1.]))
        first = checked("pressure-top", pressure(100, 500, load_id=600, load_title="Top load"))
        directions = json.loads(Path(first["verification"]["direction_report"]).read_text())
        assert all(r["positive_pressure_direction"] == [0.,0.,-1.] for r in directions["reference_segments"])
        checked("bottom", surface(101, [0.,0.,-1.]))
        checked("nr3d", service.create_gui_nonreflecting_boundary(sid, 101, 3, 11, "mm", shear=False))
        recording = checked("recording", service.stop_session_recording(sid))
        template = service.parameterize_workflow(recording["workflow"], [dict(step_id="step3", path=["scale"], parameter="pressure_scale")])
        replay = checked("scale-replay", service.run_workflow(template["artifacts"][0]["path"], dict(pressure_scale=2.5), sid))
        assert replay["data"]["steps"]["step3"]["verification"]["created_load"]["scale"] == 2.5
        rejected("duplicate-pressure", lambda: pressure(100, 501), "already exists")
        rejected("curve-collision", lambda: pressure(101, 500), "namespace")
        rejected("load-id-collision", lambda: pressure(101, 501, load_id=600, load_title="Duplicate"), "collides")
        checked("right", surface(102, [1.,0.,0.]))
        checked("second-named-load", pressure(102, 501, load_id=601, load_title="Side load", arrival_time=0.25))
        checked("bottom-alias", surface(103, [0.,0.,-1.], reverse=True))
        rejected("nr-overlap-alias", lambda: service.create_gui_nonreflecting_boundary(sid, 103, 3, 16, "mm"), "already covers")
        checked("left-reversed", surface(104, [-1.,0.,0.], reverse=True))
        final = checked("nr-reversed3d", service.create_gui_nonreflecting_boundary(sid, 104, 3, 16, "mm"))
        assert final["verification"]["boundary_geometry"]["reversed_segments"] == 1
        reopen("reopen-3d", final)

        plane = root / "plane.k"
        planar_fixture(plane)
        original = plane.read_bytes()
        checked("plane", service.open_in_gui_session(sid, str(plane)))
        checked("edges", surface(300, source="shell_boundary_2d"))
        modern = checked("nr2d-modern", service.create_gui_nonreflecting_boundary(sid, 300, 2, 14, "mm", dilatational=False))
        assert modern["verification"]["created_boundary"] == dict(dimension=2, target_id=-300, ad=1., as_=0.)
        final = checked("pressure2d", pressure(300, 700))
        reopen("reopen-modern2d", final, ordered=True)

        checked("fresh-plane", service.open_in_gui_session(sid, str(plane)))
        checked("legacy-edges", surface(301, source="shell_boundary_2d"))
        checked("reverse-edges", surface(302, reverse=True, source="shell_boundary_2d"))
        rejected("reversed2d", lambda: service.create_gui_nonreflecting_boundary(sid, 302, 2, 14, "mm"), "counterclockwise")
        rejected("legacy-no-id-allocation", lambda: service.create_gui_nonreflecting_boundary(sid, 301, 2, 11, "mm"), "node_set_start_id")
        checked("reserved-id", service.create_gui_entity_set(sid, "node", 1003, "Existing", entity_ids=[1]))
        rejected("allocated-id-collision", lambda: service.create_gui_nonreflecting_boundary(sid, 301, 2, 11, "mm", node_set_start_id=1000), "already exists")
        legacy = checked("nr2d-legacy", service.create_gui_nonreflecting_boundary(sid, 301, 2, 11, "mm", node_set_start_id=2000))
        assert legacy["verification"]["created_node_set_count"] == 6
        audit = json.loads(Path(legacy["verification"]["geometry_report"]).read_text())
        assert any(r["order"][0] > r["order"][1] for r in audit["created_ordered_node_sets"])
        rejected("legacy-overlap", lambda: service.create_gui_nonreflecting_boundary(sid, 301, 2, 14, "mm"), "already covers")
        reopen("reopen-legacy2d", legacy, ordered=True)

        wrong = root / "thin-shell.k"
        plane_text = plane.read_text(encoding="ascii")
        assert "1,13\n" in plane_text
        wrong.write_text(plane_text.replace("1,13\n", "1,2\n"), encoding="ascii")
        assert wrong.read_bytes() != original
        checked("thin-shell", service.open_in_gui_session(sid, str(wrong)))
        checked("thin-shell-edges", surface(400, source="shell_boundary_2d"))
        rejected("inapplicable-formulation", lambda: service.create_gui_nonreflecting_boundary(sid, 400, 2, 14, "mm"), "formulations")
        assert plane.read_bytes() == original
        atomic_json(root / "acceptance.json", dict(status="succeeded", cases=cases, originals_unchanged=True,
                    scope="Visible4.13.4 pressure curves/IDs/sign metadata/replay and3D, negative-SID2D, ordered-node2D nonreflecting card creation, rejection and reopen. No solver execution/absorption certification."))
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))
    print(root, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    accept(**vars(parser.parse_args()))
