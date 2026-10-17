"""Q08 render_xyplot session route against a simulated owned GUI session (no visible GUI)."""

import csv
import hashlib
import re
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ls_prepost_mcp import gui_curves
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service

DATA = dict(counts=dict(nodes=8, elements=6, states=0), part_ids=[1], current_state=1)


def native_text(blocks, corrupt=False):
    text = ""
    for number, block in enumerate(blocks):
        text += f"{len(block):10d}\n"
        for row, (x, y) in enumerate(block):
            if corrupt and number == 1 and row == 1:
                y *= 1.001
            text += f"{float(np.float32(x)):20.10e}{float(np.float32(y)):20.10e}\n"
    return text


class Manager:
    def __init__(self, root, corrupt=False):
        self.root, self.corrupt = root, corrupt
        self.windows, self.calls, self.entries, self.xy = {1, 2}, [], [], None
        (root / "lspost.msg").write_text("")

    def lock(self, sid):
        return nullcontext()

    def directory(self, sid):
        return self.root

    def dispatch(self, sid, action, parameters, native_commands=()):
        self.calls.append((action, list(native_commands)))
        for command in native_commands:
            path = re.search(r'"([^"]+)"', command)
            if command.startswith("open xydata"):
                self.xy = Path(path[1])
            elif command == "newplot":
                self.windows.add(max(self.windows) + 1)
            elif command.startswith("print png"):
                image = Image.new("RGB", (64, 48), "white")
                image.putpixel((3, 3), (255, 0, 0))
                image.save(path[1])
            elif " savefile xypair " in command:
                lines, blocks = self.xy.read_text().splitlines(), []
                while lines:
                    count = int(lines.pop(0))
                    blocks.append([tuple(float(v) for v in lines.pop(0).split(",")) for _ in range(count)])
                Path(path[1]).write_text(native_text(blocks, self.corrupt))
        return dict(status="succeeded", data=dict(DATA), job_directory=str(self.root))

    def journal(self, sid, entry):
        self.entries.append(entry)


class Transport:
    manager = None

    def __init__(self, pid):
        pass

    def inspect_controls(self):
        return [dict(parent=0, class_name="wxWindowNR", text=f"PlotWindow-{i}") for i in sorted(self.manager.windows)]


@pytest.fixture
def session(tmp_path, monkeypatch):
    def build(corrupt=False):
        root = tmp_path / "session"
        root.mkdir(exist_ok=True)
        manager = Manager(root, corrupt)
        service = Service(Settings(tmp_path / "jobs", None, (tmp_path,)))
        monkeypatch.setattr(service, "_session_manager", lambda: manager)
        monkeypatch.setattr(service, "_visible_mesh_session",
                            lambda sid, m, allow_results: dict(process=dict(pid=4242), model_kind="keyword"))
        monkeypatch.setattr(Transport, "manager", manager)
        monkeypatch.setattr(gui_curves, "WindowsCommandTransport", Transport)
        return service, manager
    return build


def cases(tmp_path, count=3):
    curves = []
    for k in range(count):
        path = tmp_path / f"case_{k}.csv"
        rows = [(0.5 + i, (k + 1) * (2.0 + i * i)) for i in range(3 + k % 3)]
        path.write_text("disp,force\n" + "".join(f"{x!r},{y!r}\n" for x, y in rows))
        curves.append(dict(path=str(path), x_column="disp", y_column="force", label=f"Case {k + 1}",
                           x_unit="mm", y_unit="kN"))
    return curves


def artifact(result, suffix):
    return next((Path(a["path"]) for a in result["artifacts"] if a["path"].endswith(suffix)), None)


def test_session_route_succeeds_with_batch_shaped_result(tmp_path, session):
    service, manager = session()
    result = service.render_xyplot(cases(tmp_path), "Three load cases", "Displacement", "Force", "mm", "kN",
                                   x_range=[0.5, 4], y_range=[1, 100], y_log=True, legend_title="Load case",
                                   session_id="s")
    assert result["status"] == "succeeded", result
    assert result["action"] == "render_xyplot" and result["route"] == "session"
    assert [e["action"] for e in manager.entries] == ["render_xyplot"]
    assert manager.entries[0]["parameters"]["curves"][2]["label"] == "Case 3"
    commands = manager.calls[-1][1]
    assert 'xyplot 3 legendlabel "Load case"' in commands
    axes = commands.index("xyplot 3 axes Log-Lin")
    limits = [commands.index(f"xyplot 3 {key}") for key in ("xmin 0.5", "xmax 4", "ymin 1", "ymax 100")]
    assert axes < min(limits)
    data = result["data"]
    assert data["visible_gui"] is True and data["legend"] is True and data["legend_title"] == "Load case"
    assert data["axes"]["native_axes_token"] == "Log-Lin" and data["curve_count"] == 3
    names = sorted(Path(a["path"]).name for a in result["artifacts"])
    assert names == ["curves.csv", "native.xy", "plot.png"]
    consistency = data["png_csv_consistency"]
    for suffix, key in (("plot.png", "png_sha256"), ("curves.csv", "csv_sha256"), ("native.xy", "native_xy_sha256")):
        assert consistency[key] == hashlib.sha256(artifact(result, suffix).read_bytes()).hexdigest()
    with artifact(result, "curves.csv").open(newline="") as stream:
        assert sorted({int(r["curve"]) for r in csv.DictReader(stream)}) == [1, 2, 3]


def test_session_legacy_curve_plot_output_is_unchanged(tmp_path, session):
    service, manager = session()
    first, second = cases(tmp_path, 2)
    result = service.export_gui_curve_plot("s", first["path"], "disp", "force", "T", "u", "F", "mm", "kN",
                                           "A", [dict(second, label="B")])
    assert result["status"] == "succeeded" and result["action"] == "export_gui_curve_plot"
    assert "route" not in result and "visible_gui" not in result["data"]
    assert [Path(a["path"]).name for a in result["artifacts"]] == ["plot.png", "plotted.csv", "native.xy",
                                                                   "plotted-2.csv"]


@pytest.mark.parametrize("bad", ["log_nonpositive", "eleven", "unit"])
def test_session_requests_are_rejected_before_dispatch(tmp_path, session, bad):
    service, manager = session()
    curves, kwargs = cases(tmp_path), {}
    if bad == "log_nonpositive":
        Path(curves[0]["path"]).write_text("disp,force\n0,1\n1,2\n")
        kwargs = dict(x_log=True)
    if bad == "eleven":
        curves = [dict(curves[0], label=f"C{i}") for i in range(11)]
    if bad == "unit":
        curves[1]["x_unit"] = "m"
    with pytest.raises(ValueError):
        service.render_xyplot(curves, "T", "u", "F", "mm", "kN", session_id="s", **kwargs)
    assert manager.calls == [] and manager.entries == []


def test_session_readback_mismatch_fails_without_curves_csv(tmp_path, session):
    service, manager = session(corrupt=True)
    result = service.render_xyplot(cases(tmp_path), "T", "u", "F", "mm", "kN", session_id="s")
    assert result["status"] == "failed" and "do not match" in result["error"]["message"]
    assert artifact(result, "curves.csv") is None
    assert not (Path(result["job_directory"]) / "curves.csv").exists()
    assert manager.entries[0]["action"] == "render_xyplot"


def test_session_hidden_legend_does_not_report_a_legend_title(tmp_path, session):
    service, _ = session()
    result = service.render_xyplot(cases(tmp_path, 1), "T", "u", "F", "mm", "kN", legend=False,
                                   legend_title="Hidden", session_id="s")
    assert result["status"] == "succeeded", result
    assert result["data"]["legend"] is False and result["data"]["legend_title"] is None
