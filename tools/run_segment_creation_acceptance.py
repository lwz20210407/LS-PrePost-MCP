"""Opt-in native oriented Hex/Tet/shell/2D Segment creation, replay and reopen."""

import argparse
import math
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def planar_fixture(path):
    path.write_text("*KEYWORD\n*NODE\n1,0,0,0\n2,1,0,0\n3,2,0,0\n4,0,1,0\n5,1,1,0\n6,2,1,0\n"
                    "*ELEMENT_SHELL\n1,1,1,2,5,4\n2,1,2,3,6,5\n*PART\nPlane strain\n1,1,1\n"
                    "*SECTION_SHELL\n1,13\n1,1,1,1\n*MAT_ELASTIC\n1,1,1000,.3\n*END\n", encoding="ascii")


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-segment-acceptance-" + uuid.uuid4().hex)
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

    def rejected(name, operation):
        try:
            operation()
        except ValueError as exc:
            assert service.inspect_gui_session(sid)["state"] == "ready"
            atomic_json(root / (name + ".json"), dict(expected_rejection=str(exc)))
            cases.append(name)
        else:
            raise AssertionError("Expected rejection: " + name)

    def query(name, set_id, count):
        result = checked(name, service.inspect_gui_entity_sets(sid, "segment", set_id))
        assert result["data"]["total"] == count
        return result["data"]["segments"]

    try:
        service.show_gui_session(sid, maximize=True)
        checked("box", service.gui_session_action(sid, "create_solid_box", dict(divisions=[2,1,1], size=[2.,1.,1.], units="mm")))
        service.start_session_recording(sid)
        selected = checked("selection", service.select_gui_entities(sid, "solid", [1, 2]))
        top = checked("top", service.create_gui_segment_set(sid, 100, "Top", "solid_exterior", "mm",
                              selection_job=selected["job_directory"], normal_direction=[0.,0.,1.]))
        assert top["verification"]["segment_count"] == 2 and top["verification"]["total_measure"] == 2
        recording = checked("recording", service.stop_session_recording(sid))
        template = service.parameterize_workflow(recording["workflow"], [
            dict(step_id="step1", path=["entity_ids"], parameter="elements"),
            dict(step_id="step2", path=["normal_direction"], parameter="direction")])
        checked("replay", service.run_workflow(template["artifacts"][0]["path"],
                                               dict(elements=[1], direction=[0.,0.,-1.]), sid))
        query("bottom-after-replay", 100, 1)
        checked("hide-neighbor", service.set_gui_entity_visibility(sid, "solid", "hide", [2]))
        first = checked("first-cell-boundary", service.create_gui_segment_set(sid, 101, "First boundary", "solid_exterior", "mm", element_ids=[1]))
        assert first["verification"]["segment_count"] == 5
        whole = checked("whole-boundary", service.create_gui_segment_set(sid, 102, "Whole", "solid_exterior", "mm", element_ids=[1,2]))
        before = query("whole-query", 102, 10)
        rejected("id-collision", lambda: service.create_gui_segment_set(sid, 102, "Collision", "solid_exterior", "mm", element_ids=[1]))
        rejected("empty-normal-filter", lambda: service.create_gui_segment_set(sid, 103, "None", "solid_exterior", "mm", element_ids=[1], normal_direction=[1.,1.,1.], cosine_min=1.0))
        saved = next(a["path"] for a in whole["artifacts"] if a["kind"] == "keyword")
        checked("reopen-hex", service.open_in_gui_session(sid, saved))
        assert query("reopened-whole", 102, 10) == before

        tet = root / "tet.k"
        tet.write_text("*KEYWORD\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n*ELEMENT_SOLID\n1,1,1,2,3,4,4,4,4,4\n"
                       "*PART\nTetrahedron\n1,1,1\n*SECTION_SOLID\n1,10\n*MAT_ELASTIC\n1,1,1000,.3\n*END\n", encoding="ascii")
        tet_original = tet.read_bytes()
        checked("open-tet", service.open_in_gui_session(sid, str(tet)))
        triangle = checked("tet-surface", service.create_gui_segment_set(sid, 200, "Tet faces", "solid_exterior", "mm", element_ids=[1]))
        assert math.isclose(triangle["verification"]["total_measure"], 1.5 + math.sqrt(3)/2)
        assert all(len(r["node_ids"]) == 3 for r in query("tet-query", 200, 4))

        plane = root / "plane.k"
        planar_fixture(plane)
        plane_original = plane.read_bytes()
        checked("open-plane", service.open_in_gui_session(sid, str(plane)))
        checked("shell-faces", service.create_gui_segment_set(sid, 300, "Plane faces", "shell_faces", "mm", element_ids=[1,2]))
        checked("hide-shell", service.set_gui_entity_visibility(sid, "shell", "hide", [2]))
        selected = checked("plane-select", service.select_gui_entities(sid, "shell", [1,2]))
        edges = checked("edges", service.create_gui_segment_set(sid, 301, "Boundary edges", "shell_boundary_2d", "mm", selection_job=selected["job_directory"]))
        assert edges["verification"]["total_measure"] == 6 and edges["verification"]["measure_dimension"] == 1
        records = query("edge-query", 301, 6)
        xy = {1:(0,0), 2:(1,0), 3:(2,0), 4:(0,1), 5:(1,1), 6:(2,1)}
        twice_area = sum(xy[a][0]*xy[b][1] - xy[b][0]*xy[a][1] for a,b in (r["node_ids"] for r in records))
        assert twice_area == 4  # directed boundary is counterclockwise
        saved = next(a["path"] for a in edges["artifacts"] if a["kind"] == "keyword")
        checked("reopen-plane", service.open_in_gui_session(sid, saved))
        assert query("reopened-edges", 301, 6) == records
        assert tet.read_bytes() == tet_original and plane.read_bytes() == plane_original
        atomic_json(root / "acceptance.json", dict(status="succeeded", cases=cases, originals_unchanged=True,
                    scope="4.13 visible native Segment sets: Hex8 exterior, Tet4 triangular faces, Tri/Quad shell faces and directed XY edges. Geometry ownership/orientation computed from native export; no pressure/nonreflecting/solver certification."))
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))
    print(root, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    accept(**vars(parser.parse_args()))
