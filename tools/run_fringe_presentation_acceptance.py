"""Opt-in native title/MinMax defaults, explicit override and MP4 presentation check."""

import argparse
import csv
import re
import uuid
from pathlib import Path

from run_result_selection_acceptance import hashes

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.windows_transport import WindowsCommandTransport


def read_average(pid):
    transport = WindowsCommandTransport(pid)
    transport.open_menu_item(["FEM", "Post", "Fringe Range"])
    try:
        hwnd = transport._panel_control("Fringe Range", 10414, class_name="ComboBox")
        def send(message, wparam=0, lparam=0):
            value = transport.ctypes.c_size_t()
            if not transport.u.SendMessageTimeoutW(hwnd, message, wparam, lparam, 0x0002, 3000, transport.ctypes.byref(value)):
                raise RuntimeError("Native averaging readback timed out")
            return transport.ctypes.c_ssize_t(value.value).value
        selected = send(0x0147)
        assert 0 <= selected < send(0x0146)
        length = send(0x0149, selected)
        assert 0 <= length < 1024
        buffer = transport.ctypes.create_unicode_buffer(length+1)
        send(0x0148, selected, transport.ctypes.cast(buffer, transport.ctypes.c_void_p).value)
        return buffer.value
    finally:
        transport._click_panel_control("Fringe Range", 5101, "Done")


def accept(workspace, executable, source, part=1):
    source = Path(source).resolve(strict=True)
    family = [source]+sorted(p for p in source.parent.iterdir() if p.is_file() and re.fullmatch(re.escape(source.name)+r"\d+", p.name))
    before = hashes(family)
    root = Path(workspace).resolve()/("native-fringe-presentation-"+uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    service = Service(Settings(root, Path(executable), allowed_roots=(source.parent,), timeout=150))
    session = service.start_gui_session()
    sid, pid = session["session_id"], session["process"]["pid"]
    atomic_json(root/"session.json", session)
    cases = []
    def checked(name, response):
        atomic_json(root/(name+".json"), response)
        assert response["status"] == "succeeded", response.get("error")
        cases.append(name)
        print(name, flush=True)
        return response
    def values(response):
        with Path(response["artifacts"][1]["path"]).open(newline="") as stream:
            return list(csv.DictReader(stream))
    try:
        service.show_gui_session(sid, maximize=True)
        opened = checked("open", service.open_in_gui_session(sid, str(source), "d3plot"))
        checked("view", service.set_gui_display(sid, view="isometric", center=True, capture=False))
        state = max(2, opened["data"]["counts"]["states"]//2)
        default = checked("minmax", service.render_gui_field(sid, "solid", "von_mises", state, "model_stress", part_ids=[part]))
        assert read_average(pid) == "MinMax"
        assert default["data"]["legend_label"] == "Von Mises stress"
        assert default["data"]["display_averaging"] == "minmax"
        raw = checked("none", service.render_gui_field(sid, "solid", "von_mises", state, "model_stress", part_ids=[part], averaging="none"))
        assert read_average(pid) == "None"
        assert values(default) == values(raw), "Presentation averaging must not rewrite raw entity CSV"
        fixed = [0., default["data"]["value_max"]*1.05]
        service.start_session_recording(sid)
        checked("recorded", service.render_gui_field(sid, "solid", "von_mises", 1, "model_stress", part_ids=[part], color_range=fixed))
        recording = checked("recording", service.stop_session_recording(sid))
        replay = checked("replay", service.run_workflow(recording["workflow"], session_id=sid))
        assert replay["data"]["steps"]["step1"]["data"]["display_averaging"] == "minmax"
        for i in (2, 3):
            checked("state-"+str(i), service.render_gui_field(sid, "solid", "von_mises", i, "model_stress", part_ids=[part], color_range=fixed))
        movie = checked("movie", service.export_gui_animation(sid, last=3, width=640, height=480))
        assert movie["data"]["display_averaging"] == "minmax" and read_average(pid) == "MinMax"
        assert before == hashes(family)
        atomic_json(root/"acceptance.json", dict(status="succeeded", cases=cases, source_unchanged=True,
            averaging_readback="Native Fringe Range combo: MinMax by default, None on explicit override",
            title_scope="Observed native quantity name; generated SCL and movie commands contain no metadata suffix/model-title mutation; rendered PNG requires visual review",
            numeric_scope="Raw entity CSV unchanged by presentation averaging; no claim of independently reconstructed nodal MinMax algorithm"))
    finally:
        atomic_json(root/"closed.json", service.close_gui_session(sid, save_checkpoint=False))
    print(root, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--part", type=int, default=1)
    accept(**vars(parser.parse_args()))
