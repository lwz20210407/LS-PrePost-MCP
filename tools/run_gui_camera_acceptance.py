"""Opt-in native absolute zoom/pan, incremental rotations, preservation and managed replay."""

import argparse
import hashlib
import re
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_mesh import verify_mesh_digest
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def pixels(result):
    artifact = next(a for a in result["artifacts"] if a["kind"] == "png")
    with Image.open(artifact["path"]) as frame:
        return frame.size, hashlib.sha256(frame.convert("RGB").tobytes()).hexdigest()


def raster_equivalent_arrays(before, after):
    """Allow only symmetric one-pixel raster-edge movement / one RGB level rounding."""
    if before.shape != after.shape:
        return False
    def contained(a, b):
        padded = np.pad(b.astype(np.int16), ((1,1),(1,1),(0,0)), mode="edge")
        matches = np.zeros(a.shape[:2], dtype=bool)
        for y in range(3):
            for x in range(3):
                matches |= (np.abs(a.astype(np.int16)-padded[y:y+a.shape[0],x:x+a.shape[1]]) <= 1).all(axis=2)
        return bool(matches.all())
    return contained(before, after) and contained(after, before)


def raster_equivalent(before, after):
    def array(result):
        path = next(a["path"] for a in result["artifacts"] if a["kind"] == "png")
        with Image.open(path) as frame:
            return np.asarray(frame.convert("RGB"))
    return raster_equivalent_arrays(array(before), array(after))


def accept(workspace, executable, result=None):
    source = Path(result).resolve(strict=True) if result else None
    family = ([source]+sorted(p for p in source.parent.iterdir() if p.is_file() and re.fullmatch(re.escape(source.name)+r"\d+",p.name))) if source else []
    def hashes():
        result = {}
        for path in family:
            with path.open("rb") as stream:
                result[str(path)] = hashlib.file_digest(stream,"sha256").hexdigest()
        return result
    original = hashes()
    root = Path(workspace).resolve()/("native-camera-acceptance-"+uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    service = Service(Settings(root, Path(executable), allowed_roots=(source.parent,) if source else (), timeout=90))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root/"session.json", session)
    def checked(name, result):
        atomic_json(root/(name+".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        print(name, flush=True)
        return result
    def digest():
        manager = service._session_manager()
        with manager.lock(sid):
            return manager.dispatch(sid, "gui_mesh_digest", {})["data"]
    try:
        service.show_gui_session(sid, maximize=True)
        checked("created", service.gui_session_action(sid, "create_solid_box", dict(divisions=[2,1,1], size=[2.,4.,6.], units="mm")))
        checked("fit", service.set_gui_display(sid, view="isometric", projection="parallel", center=True))
        before = digest()
        zoom = checked("zoom", service.set_gui_display(sid, zoom_scale=1.5))
        assert pixels(zoom) == pixels(checked("zoom-repeat", service.set_gui_display(sid, zoom_scale=1.5)))
        pan = checked("pan", service.set_gui_display(sid, pan_xy=[0.1,0.05]))
        assert pixels(pan) != pixels(zoom)
        assert pixels(pan) == pixels(checked("pan-repeat", service.set_gui_display(sid, pan_xy=[0.1,0.05])))
        half = checked("half", service.set_gui_display(sid, zoom_scale=0.75))
        assert pixels(half) != pixels(pan)
        rotated = checked("rotate", service.set_gui_display(sid, rotation_xyz_degrees=[15.,0.,0.]))
        assert pixels(rotated) != pixels(half)
        returned = checked("inverse-rotate", service.set_gui_display(sid, rotation_xyz_degrees=[-15.,0.,0.]))
        assert pixels(returned) == pixels(half)
        for axis, angle in ((1,25.), (2,30.)):
            angles = [0.,0.,0.]
            angles[axis] = angle
            moved = checked("rotate-"+"xyz"[axis], service.set_gui_display(sid, rotation_xyz_degrees=angles))
            assert pixels(moved) != pixels(half)
            angles[axis] = -angle
            restored = checked("inverse-"+"xyz"[axis], service.set_gui_display(sid, rotation_xyz_degrees=angles))
            assert raster_equivalent(half, restored)
        service.start_session_recording(sid)
        checked("recorded", service.set_gui_display(sid, zoom_scale=1.5, pan_xy=[0.,0.]))
        recording = checked("recording", service.stop_session_recording(sid))
        assert recording["managed_steps"] == 1
        template = service.parameterize_workflow(recording["workflow"], [dict(step_id="step1",path=["zoom_scale"],parameter="zoom")])
        replay = checked("replay", service.run_workflow(template["artifacts"][0]["path"],dict(zoom=0.75),sid))
        assert "zoom 0.75" in replay["data"]["steps"]["step1"]["data"]["applied_commands"]
        after = digest()
        verify_mesh_digest(before, after)
        assert before["part_visibility"] == after["part_visibility"] and before["current_state"] == after["current_state"]
        if source:
            opened = checked("results-open",service.open_in_gui_session(sid,str(source),"d3plot"))
            checked("result-fit",service.set_gui_display(sid,state=min(2,opened["data"]["counts"]["states"]),view="isometric",projection="parallel",center=True,averaging="minmax"))
            result_before = digest()
            first = checked("result-zoom",service.set_gui_display(sid,zoom_scale=1.5,pan_xy=[0.,0.]))
            repeat = checked("result-repeat",service.set_gui_display(sid,zoom_scale=1.5,pan_xy=[0.,0.]))
            assert pixels(first)==pixels(repeat)
            checked("result-rotate",service.set_gui_display(sid,rotation_xyz_degrees=[0.,0.,15.]))
            restored = checked("result-inverse",service.set_gui_display(sid,rotation_xyz_degrees=[0.,0.,-15.]))
            assert raster_equivalent(first,restored)
            result_after=digest()
            verify_mesh_digest(result_before,result_after)
            assert result_before["current_state"]==result_after["current_state"] and result_before["part_visibility"]==result_after["part_visibility"]
        assert hashes()==original
        atomic_json(root/"acceptance.json", dict(status="succeeded",
            source_unchanged=True, result_case_tested=bool(source),
            scope="Absolute zoom/pan pixel-exact idempotence; separate X/Y/Z rotation/inverse within symmetric one-pixel/one-RGB-level raster tolerance; geometry/state/part preservation and changed-zoom managed replay. Optional d3plot zoom/rotation/state preservation. No numeric camera matrix or cross-model bookmark certification."))
    finally:
        atomic_json(root/"closed.json", service.close_gui_session(sid,save_checkpoint=False))
    print(root, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--result")
    accept(**vars(parser.parse_args()))
