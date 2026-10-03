"""Opt-in native Blank display-state, part preservation and workflow replay acceptance."""

import argparse
import re
import time
import uuid
from pathlib import Path

from run_result_selection_acceptance import hashes

from ls_prepost_mcp.compact_server import CompactTools
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.windows_transport import WindowsCommandTransport


def mixed_fixture(path):
    coordinates = [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1),
                   (2,0,0),(2,1,0),(2,0,1),(2,1,1)]
    nodes = "\n".join(",".join(map(str, (i, *xyz))) for i, xyz in enumerate(coordinates, 1))
    path.write_text("*KEYWORD\n*TITLE\nMixed visibility fixture\n*NODE\n"+nodes+"\n"
        "*ELEMENT_SOLID\n1,1,1,2,3,4,5,6,7,8\n2,1,2,9,10,3,6,11,12,7\n"
        "*ELEMENT_SHELL\n101,2,1,2,3,4\n102,2,5,6,7,8\n"
        "*ELEMENT_BEAM\n201,3,9,10,0\n202,3,11,12,0\n"
        "*PART\nSolids\n1,1,1\n*PART\nShells\n2,2,1\n*PART\nBeams\n3,3,1\n"
        "*SECTION_SOLID\n1,1\n*SECTION_SHELL\n2,2\n1,1,1,1\n*SECTION_BEAM\n3,1\n1,1,0,0,0,0,0,0\n"
        "*MAT_ELASTIC\n1,1,100000,0.3\n*END\n", encoding="ascii")


def accept(workspace, executable, result=None):
    source = Path(result).resolve(strict=True) if result else None
    family = ([source] + sorted(p for p in source.parent.iterdir() if p.is_file() and
               re.fullmatch(re.escape(source.name)+r"\d+", p.name))) if source else []
    identities = hashes(family)
    root = Path(workspace).resolve() / ("native-common-visibility-"+uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    service = Service(Settings(root, Path(executable), allowed_roots=(source.parent,) if source else (), timeout=240))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root/"session.json", session)
    cases = []

    def checked(name, operation):
        atomic_json(root/(name+".json"), operation)
        assert operation["status"] == "succeeded", operation.get("error")
        cases.append(name)
        print(name, flush=True)
        return operation

    def visibility(name, mode, entity_ids=None, kind="solid", capture=False):
        started = time.perf_counter()
        result = service.set_gui_entity_visibility(sid, kind, mode, entity_ids, capture)
        result["acceptance_elapsed_seconds"] = time.perf_counter()-started
        return checked(name, result)

    try:
        service.show_gui_session(sid, maximize=True)
        transport = WindowsCommandTransport(session["process"]["pid"])
        fallback = WindowsCommandTransport(session["process"]["pid"], control_id=-999)
        assert fallback.command_window() == transport.command_window()
        atomic_json(root/"dynamic-menu.json", transport.open_panel("normals"))
        transport._click_panel_control("Normals", 10015, "Done")
        checked("created", CompactTools(service).lspp_run_operation("create_solid_box", dict(divisions=[3, 1, 1], size=[3., 2., 2.], units="mm"), "gui", sid))
        checked("display", service.set_gui_display(sid, view="isometric", center=True, capture=False))
        page = checked("solids", service.inspect_gui_mesh(sid, entity_type="solid", limit=3))
        uids = [row["id"] for row in page["data"]["elements"]]
        hidden = visibility("hide-one", "hide", uids[:1], capture=True)
        assert hidden["verification"]["visible_count"] == 2
        shown = visibility("show-one", "show", uids[:1])
        assert shown["verification"]["visible_count"] == 3
        isolated = visibility("isolate-one", "isolate", uids[:1])
        assert isolated["verification"]["visible_count"] == 1
        visibility("restore-isolate", "restore_last")
        visibility("hide-all", "hide")
        visibility("show-subset", "show", uids[:2])
        visibility("reverse-subset", "reverse", uids[1:])
        visibility("reverse-all", "reverse")
        visibility("show-all", "show")
        visibility("empty-scope", "hide", [])
        checked("part-hidden", service.set_gui_part_visibility(sid, "hide", [1]))
        preserved = visibility("hidden-part-change", "hide", uids[:1])
        assert preserved["data"]["part_visibility"] == {"1": False}
        visibility("hidden-part-restore", "restore_last")
        checked("part-shown", service.set_gui_part_visibility(sid, "all"))
        service.start_session_recording(sid)
        visibility("recorded-hide", "hide", uids[:1])
        recorded = checked("recording", service.stop_session_recording(sid))
        assert recorded["managed_steps"] == 1
        visibility("before-replay", "show")
        replay = checked("replay", service.run_workflow(recorded["workflow"], session_id=sid))
        assert replay["data"]["steps"]["step1"]["verification"]["visible_count"] == 2
        visibility("after-replay", "restore_last")
        mixed = root/"mixed.k"
        mixed_fixture(mixed)
        checked("mixed-open", service.open_in_gui_session(sid, str(mixed), "keyword"))
        for kind, first in (("solid", 1), ("shell", 101), ("beam", 201)):
            visibility(kind+"-hide-all", "hide", kind=kind)
            visibility(kind+"-show-one", "show", [first], kind=kind)
            visibility(kind+"-reverse", "reverse", kind=kind)
            visibility(kind+"-restore", "restore_last", kind=kind)
            visibility(kind+"-show-all", "show", kind=kind)
        visibility("mixed-isolate", "isolate", [1, 101, 201], kind="element")
        visibility("mixed-restore", "restore_last", kind="element")
        visibility("before-stale-restore", "hide", [101], kind="shell")
        manager = service._session_manager()
        with manager.lock(sid):
            checked("external-visibility", manager.dispatch(sid, "gui_mesh_digest", {}, native_commands=["unblank all 10"]))
        rejected = service.set_gui_entity_visibility(sid, "shell", "restore_last")
        atomic_json(root/"stale-restore-rejected.json", rejected)
        assert rejected["status"] == "failed" and "externally" in rejected["error"]["message"]
        assert service.inspect_gui_session(sid)["state"] == "ready"
        if source:
            opened = checked("results-open", service.open_in_gui_session(sid, str(source), "d3plot"))
            page = checked("result-solids", service.inspect_gui_mesh(sid, entity_type="solid", offset=opened["data"]["counts"]["elements"]-3, limit=3))
            result_ids = [row["id"] for row in page["data"]["elements"]]
            checked("result-state", service.set_gui_display(sid, state=max(1, opened["data"]["counts"]["states"]//2), center=True, capture=False))
            visibility("result-hide", "hide", result_ids, capture=True)
            visibility("result-show", "show", result_ids)
            visibility("result-isolate", "isolate", result_ids, capture=True)
            visibility("result-restore", "restore_last")
        assert identities == hashes(family)
        atomic_json(root/"acceptance.json", dict(status="succeeded", cases=cases, source_unchanged=True,
                    scope="Standard native display-active flags, complete geometry/state/part preservation, owned restore and replay; no node glyph or physical erosion certification"))
    finally:
        atomic_json(root/"closed.json", service.close_gui_session(sid, save_checkpoint=False))
    print(str(root), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--result")
    accept(**vars(parser.parse_args()))
