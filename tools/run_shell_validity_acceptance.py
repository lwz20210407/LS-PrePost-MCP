"""Opt-in visible shell deletion/stress/layer/fringe/movie verification against known synthetic truth."""

import argparse
import csv
import math
import uuid
from pathlib import Path

from synthetic_shell_result import create_fixture

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("shell-validity-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    source, truth = create_fixture(root / "fixture")
    before = fingerprint(source)
    service = Service(Settings(root, Path(executable), timeout=120))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    checks = []

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error") or result.get("restoration_error")
        checks.append(name)
        print(name, flush=True)
        return result

    def stress_rows(result):
        with (Path(result["job_directory"]) / "stress.csv").open(newline="") as stream:
            return list(csv.DictReader(stream))

    try:
        service.show_gui_session(sid, maximize=True)
        checked("open", service.open_in_gui_session(sid, str(source), "d3plot"))
        checked("view", service.set_gui_display(sid, view="isometric", center=True, zoom_scale=.7, capture=False))
        params = dict(element_type="shell", element_ids=truth["shell_ids"], states=[1,2,3], integration_point="2", units="Pa")
        raw = checked("raw", service.gui_session_action(sid, "extract_native_stress", params))
        assert len(stress_rows(raw)) == 9
        kept = checked("alive", service.gui_session_action(sid, "extract_native_stress", dict(params, validity_policy="alive")))
        expected = {(1,101),(1,305),(1,9001),(2,101),(2,9001),(3,9001)}
        assert {(int(r["state"]),int(r["entity_id"])) for r in stress_rows(kept)} == expected
        for row in stress_rows(kept):
            assert math.isclose(float(row["von_mises"]), truth["point2_values"][row["entity_id"]], rel_tol=2e-6)
        empty = checked("all-deleted", service.gui_session_action(sid, "extract_native_stress",
                        dict(params, element_ids=[101,305], states=[3], validity_policy="alive")))
        assert empty["data"]["row_count"] == 0 and empty["data"]["derived_statistics"]["von_mises"]["maximum"] is None
        # Only deleted high-stress entities are requested in this part at state3.
        failed = service.render_gui_field(sid, "shell", "von_mises", 3, "Pa", integration_point="2",
                                         part_ids=[7], validity_policy="alive")
        atomic_json(root / "empty-fringe-rejected.json", failed)
        assert failed["status"] == "failed" and "No physically present" in failed["error"]["message"]
        assert not failed["artifacts"]
        # Reopen the unchanged fixture to start the positive sequence with clean Blank.
        checked("reopen", service.open_in_gui_session(sid, str(source), "d3plot"))
        for state, count, maximum in zip(truth["states"], truth["retained_counts"], truth["point2_maximum"], strict=True):
            rendered = checked("fringe-"+str(state), service.render_gui_field(sid, "shell", "von_mises", state,
                "Pa", integration_point="2", color_range=[0.,2000.], validity_policy="alive"))
            assert rendered["data"]["rendered_entity_count"] == count
            assert math.isclose(rendered["data"]["value_max"], maximum, rel_tol=2e-6)
        movie = checked("movie", service.export_gui_field_animation(sid, [1,2,3], [0.,2000.], fps=5, width=640, height=480))
        assert [f["count"] for f in movie["data"]["frames"]] == [3,2,1]
        assert movie["data"]["video"]["decoded_frames"] == 3 and movie["restoration"]["verified"]
        assert fingerprint(source) == before
        atomic_json(root / "acceptance.json", dict(status="succeeded", checks=checks, synthetic_solver_run=False,
                    truth=truth, source_unchanged=True,
                    scope="Native4.13.4 shell stored-point2 and MDLOPT2 sparse-ID deletion: raw9/retained6/empty rows, high deleted stress excluded from extrema, empty display rejected, per-state PNG/MP4 counts3/2/1. This is a constructed binary fixture, not physical material-failure or solver validation."))
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    print(accept(args.workspace, args.executable))
