"""Opt-in native common pre/post measurements, geometry checks and parameter replay."""

import argparse
import math
import re
import uuid
from pathlib import Path

from run_result_selection_acceptance import hashes

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable, result=None):
    source = Path(result).resolve(strict=True) if result else None
    family = ([source] + sorted(p for p in source.parent.iterdir() if p.is_file() and
               re.fullmatch(re.escape(source.name)+r"\d+", p.name))) if source else []
    identities = hashes(family)
    root = Path(workspace).resolve() / ("native-common-measure-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    s = Service(Settings(root, Path(executable), allowed_roots=(source.parent,) if source else (), timeout=240))
    session = s.start_gui_session()
    sid = session["session_id"]
    atomic_json(root/"session.json", session)
    results = []

    def checked(name, operation):
        atomic_json(root/(name+".json"), operation)
        assert operation["status"] == "succeeded", operation.get("error")
        results.append(name)
        return operation

    try:
        s.show_gui_session(sid, maximize=True)
        checked("created", s.gui_session_action(sid, "create_solid_box", dict(divisions=[2, 1, 1], size=[2., 4., 6.], units="mm")))
        checked("view", s.set_gui_display(sid, view="isometric", center=True, capture=False))
        page = checked("nodes", s.inspect_gui_mesh(sid, entity_type="node", limit=100))
        lookup = {tuple(row[1:]): row[0] for row in page["data"]["nodes"]}
        a, b, c, d, top = [lookup[xyz] for xyz in ((0., 0., 0.), (2., 0., 0.), (0., 4., 0.), (2., 4., 0.), (2., 4., 6.))]
        coordinate = checked("coordinates", s.measure_gui_geometry(sid, "coordinates", [a, top], "mm"))
        assert coordinate["data"]["nodes"][-1]["coordinates"] == [2., 4., 6.]
        distance = checked("distance", s.measure_gui_geometry(sid, "distance", [a, top], "mm"))
        assert math.isclose(distance["data"]["distance"], math.sqrt(56), rel_tol=2e-6)
        height = checked("height", s.measure_gui_geometry(sid, "height", [top, a], "mm", axis="z"))
        assert height["data"]["height"] == 6 and height["data"]["signed_height"] == -6
        checked("angle3", s.measure_gui_geometry(sid, "angle3", [a, b, c], "mm"))
        checked("angle4", s.measure_gui_geometry(sid, "angle4", [a, b, c, d], "mm"))
        circle = checked("circle", s.measure_gui_geometry(sid, "circle3", [a, b, c], "mm", capture=True))
        assert circle["data"]["center"] == [1., 2., 0.]
        s.start_session_recording(sid)
        checked("recorded-height", s.measure_gui_geometry(sid, "height", [a, top], "mm", axis="z"))
        recorded = s.stop_session_recording(sid)
        assert recorded["status"] == "succeeded" and recorded["managed_steps"] == 1
        template = s.parameterize_workflow(recorded["workflow"], [dict(step_id="step1", path=["axis"], parameter="axis")])
        replay = checked("replayed-height", s.run_workflow(template["artifacts"][0]["path"], dict(axis="y"), sid))
        assert replay["data"]["steps"]["step1"]["data"]["height"] == 4
        collinear = [lookup[(0., 0., 0.)], lookup[(1., 0., 0.)], lookup[(2., 0., 0.)]]
        rejected = s.measure_gui_geometry(sid, "circle3", collinear, "mm")
        atomic_json(root/"collinear.json", rejected)
        assert rejected["status"] == "failed"
        assert rejected["verification"]["precondition_rejected"]
        assert s.inspect_gui_session(sid)["state"] == "ready"
        if source:
            opened = checked("results-open", s.open_in_gui_session(sid, str(source), "d3plot"))
            sample = checked("result-nodes", s.inspect_gui_mesh(sid, entity_type="node", offset=opened["data"]["counts"]["nodes"]-3, limit=3))
            uids = [row[0] for row in sample["data"]["nodes"]]
            state = max(2, opened["data"]["counts"]["states"]//2)
            checked("result-coordinates", s.measure_gui_geometry(sid, "coordinates", uids, "model_length", state=state))
            checked("result-distance", s.measure_gui_geometry(sid, "distance", uids[:2], "model_length", state=state, capture=True))
        atomic_json(root/"acceptance.json", dict(status="succeeded", cases=results,
                    source_unchanged=identities==hashes(family),
                    scope="Native numeric measurements, independent coordinate checks, complete reference mesh preservation and parameter replay"))
        assert identities==hashes(family)
    finally:
        atomic_json(root/"closed.json", s.close_gui_session(sid, save_checkpoint=False))
    print(str(root), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--result")
    accept(**vars(parser.parse_args()))
