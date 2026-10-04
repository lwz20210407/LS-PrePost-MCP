"""Visible native overlay, unequal XY grids, old-plot preservation and replay."""

import argparse
import json
import uuid
from pathlib import Path

from run_element_set_acceptance import fixture

from ls_prepost_mcp.config import Settings, command_path
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("mc-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    model = root / "model.k"
    fixture(model)
    a, b, c = [root / name for name in ("loading.csv", "reference.csv", "alternate.csv")]
    a.write_text("x,y\n0,0\n1,2\n0.5,1\n2,3\n")
    b.write_text("x,y\n0,1\n1,1.5\n2,2\n")
    c.write_text("x,y\n0,4\n0.5,2\n1,0\n2,1\n3,2\n")
    originals = {p: p.read_bytes() for p in (model, a, b, c)}
    service = Service(Settings(root, Path(executable), timeout=90))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    print(root, flush=True)

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        print(name, flush=True)
        return result

    args = dict(
        path=str(a),
        x_column="x",
        y_column="y",
        title="Response comparison",
        x_label="Displacement",
        y_label="Force",
        x_unit="mm",
        y_unit="N",
    )

    def curve(path, label):
        return dict(path=str(path), x_column="x", y_column="y", label=label, x_unit="mm", y_unit="N")

    try:
        service.show_gui_session(sid, maximize=True)
        checked("open", service.open_in_gui_session(sid, str(model)))
        old = checked("single", service.export_gui_curve_plot(sid, **args))
        old_xy = Path(old["job_directory"]) / "native.xy"
        original_xy = old_xy.read_bytes()
        service.start_session_recording(sid)
        overlay = checked(
            "overlay",
            service.export_gui_curve_plot(
                sid,
                **args,
                curve_label="Loading",
                additional_curves=[curve(b, "Reference"), curve(c, "Alternate")],
            ),
        )
        assert overlay["data"]["curve_count"] == 3
        assert [v["numeric_verification"]["sample_count"] for v in overlay["data"]["curves"]] == [4, 3, 5]
        record = checked("record", service.stop_session_recording(sid))
        workflow = json.loads(Path(record["workflow"]).read_text(encoding="utf8"))
        assert len(workflow["steps"]) == 1 and workflow["steps"][0]["arguments"]["additional_curves"][0][
            "path"
        ] == str(b)
        p = service.parameterize_workflow(
            record["workflow"],
            [dict(step_id="step1", path=["additional_curves", 0, "path"], parameter="reference")],
        )
        replay = checked(
            "replay", service.run_workflow(p["artifacts"][0]["path"], dict(reference=str(c)), sid)
        )
        replotted = replay["data"]["steps"]["step1"]
        assert [v["numeric_verification"]["sample_count"] for v in replotted["data"]["curves"]] == [4, 5, 5]
        assert replotted["data"]["plot_id"] != overlay["data"]["plot_id"] != old["data"]["plot_id"]
        m = service._session_manager()
        with m.lock(sid):
            checked(
                "old-plot-readback",
                m.dispatch(
                    sid,
                    "inspect_model",
                    {},
                    native_commands=[
                        f"xyplot {old['data']['plot_id']} savefile xypair "
                        + command_path(root / "old-after.xy")
                        + " 1 all"
                    ],
                ),
            )
        assert (root / "old-after.xy").read_bytes() == original_xy
        assert all(p.read_bytes() == data for p, data in originals.items())
        atomic_json(
            root / "acceptance.json",
            dict(
                status="succeeded",
                curve_counts=[1, 3, 3],
                sample_counts=[[4], [4, 3, 5], [4, 5, 5]],
                old_plot_preserved=True,
                source_unchanged=True,
                scope="Visible4.13.4 synthetic native overlays with unequal grids/hysteresis,labels,CSV/PNG,numeric float32 readback and nested source-path parameter replay; no solver quantity or publication typography certification",
                images=[str(Path(r["job_directory"]) / "plot.png") for r in (old, overlay, replotted)],
            ),
        )
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--executable", required=True)
    accept(**vars(p.parse_args()))
