"""Opt-in visible native stress/deletion/Blank/recording checks on a supplied result family."""

import argparse
import csv
import json
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

from ls_prepost_mcp.config import Settings, command_path, scl_command_path
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.result_validity import load_physical_validity
from ls_prepost_mcp.service import Service


def accept(workspace, executable, source, last_state):
    source = Path(source).resolve()
    root = Path(workspace).resolve() / ("native-validity-acceptance-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    service = Service(Settings(root, Path(executable), allowed_roots=(source.parent,), timeout=180))
    sources = service._result_family(str(source))
    original = [fingerprint(p) for p in sources]
    mask = load_physical_validity(source, [1, last_state], "solid")
    surviving = mask.user_ids[mask.mask[0] & mask.mask[-1]]
    deleted = mask.user_ids[mask.mask[0] & ~mask.mask[-1]]
    if not len(surviving) or not len(deleted):
        raise ValueError("Fixture must have solid elements present at both states and others deleted at the last state")
    keep, drop = int(surviving[0]), int(deleted[0])
    checks = []

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        checks.append(name)
        print(name, flush=True)
        return result

    def rows(result):
        artifact = next(a for a in result["artifacts"] if Path(a["path"]).name == "stress.csv")
        with Path(artifact["path"]).open(newline="", encoding="utf8") as stream:
            return list(csv.DictReader(stream))

    validity = checked("physical-mask", service.inspect_result_validity(str(source), "solid", [1, last_state]))
    assert validity["data"]["states"][-1]["deleted_count"] == len(deleted)
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    params = dict(element_type="solid", element_ids=[keep, drop], states=[1, last_state],
                  integration_point="mid", units="source_units_unresolved", validity_policy="alive")
    try:
        service.show_gui_session(sid, maximize=True)
        checked("open", service.open_in_gui_session(sid, str(source), "d3plot"))
        service.start_session_recording(sid)
        filtered = checked("native-alive", service.gui_session_action(sid, "extract_native_stress", params))
        record = checked("recording", service.stop_session_recording(sid))
        assert record["managed_steps"] == 1
        assert {(int(r["state"]), int(r["entity_id"])) for r in rows(filtered)} == {(1, keep), (1, drop), (last_state, keep)}
        assert filtered["data"]["physical_deletion_filter_applied"]
        replay = checked("replay", service.run_workflow(record["workflow"], session_id=sid))
        replayed = replay["data"]["steps"]["step1"]
        assert replayed["data"]["validity_policy"] == "alive" and rows(replayed) == rows(filtered)
        assert replayed["data"]["session_context_preserved"]
        empty = checked("native-all-deleted", service.gui_session_action(sid, "extract_native_stress",
                        dict(params, element_ids=[drop], states=[last_state])))
        assert rows(empty) == [] and empty["data"]["empty_reason"] == "all_requested_entities_deleted"
        assert empty["data"]["derived_statistics"]["von_mises"]["maximum"] is None
        # A present entity remains eligible even when explicitly blanked in the GUI.
        checked("hide-present", service.set_gui_entity_visibility(sid, "solid", "hide", entity_ids=[keep]))
        hidden = checked("hidden-present-retained", service.gui_session_action(sid, "extract_native_stress",
                         dict(params, element_ids=[keep], states=[last_state])))
        assert len(rows(hidden)) == 1 and hidden["data"]["session_context_preserved"]
        reader = checked("reader-alive", service.extract_d3plot_stress(str(source), "solid", mask.user_ids.tolist(),
                         [last_state], 1, "source_units_unresolved", validity_policy="alive"))
        maximum = reader["data"]["statistics"]["von_mises"]["maximum"]
        spot = checked("native-reader-maximum-spot", service.gui_session_action(sid, "extract_native_stress",
                       dict(params, element_ids=[maximum["entity_id"]], states=[last_state])))
        assert np.isclose(float(rows(spot)[0]["von_mises"]), maximum["value"], rtol=2e-5, atol=1e-12)
        first_fringe = checked("physical-fringe-first", service.render_gui_field(
            sid, "solid", "von_mises", last_state, "source_units", validity_policy="alive"))
        assert first_fringe["data"]["rendered_entity_count"] == int(mask.mask[-1].sum()) - 1
        checked("show-present", service.set_gui_entity_visibility(sid, "solid", "show", entity_ids=[keep]))
        checked("fit-physical-fringe", service.set_gui_display(
            sid, view="isometric", center=True, zoom_scale=0.7, capture=False))
        service.start_session_recording(sid)
        fringe = checked("physical-fringe", service.render_gui_field(
            sid, "solid", "von_mises", last_state, "source_units", validity_policy="alive"))
        fringe_record = checked("fringe-recording", service.stop_session_recording(sid))
        assert fringe["data"]["rendered_entity_count"] == int(mask.mask[-1].sum())
        assert np.isclose(fringe["data"]["value_max"], maximum["value"], rtol=2e-5, atol=1e-12)
        assert fringe["data"]["display_averaging"] == "minmax"
        fringe_replay = checked("fringe-replay", service.run_workflow(fringe_record["workflow"], session_id=sid))
        fringe = fringe_replay["data"]["steps"]["step1"]
        assert fringe["data"]["validity_policy"] == "alive"
        from ls_prepost_mcp.scene_state import require_movie_field_coverage

        try:
            require_movie_field_coverage(service._session_manager().read(sid), last_state)
        except ValueError as exc:
            assert "per-state visibility" in str(exc)
        else:
            raise AssertionError("Static physical Blank must not certify movie visibility")
        # Perturb excluded buffers only. Reapply identical averaging/range because
        # SCLFringeDCToModel itself resets presentation defaults.
        field_dir = Path(fringe["job_directory"])
        script = (field_dir / "field.scl").read_text(encoding="utf8")
        assert "else v[j]=0;" in script
        poison = root / "excluded-buffer-probe.scl"
        poison.write_text(script.replace("else v[j]=0;", "else v[j]=1e10;"), encoding="utf8")
        image = root / "excluded-buffer.png"
        commands = ["runscript " + scl_command_path(poison)]
        commands += json.loads((field_dir / "render-commands.json").read_text(encoding="utf8"))[:-1]
        commands += ["print png " + command_path(image) + ' opaque enlisted "OGL1x1"']
        checked("excluded-buffer-dispatch", service._session_manager().dispatch(
            sid, "inspect_model", {}, native_commands=commands))
        a = np.asarray(Image.open(field_dir / "fringe.png").convert("RGB"))
        b = np.asarray(Image.open(image).convert("RGB"))
        assert np.array_equal(a, b), "Hidden deleted buffers changed the fixed-presentation image"
        assert [fingerprint(p) for p in sources] == original
        atomic_json(root / "acceptance.json", dict(status="succeeded", checks=checks, source_fingerprints=original,
                    selected_ids=dict(present=keep, deleted=drop), states=[1, last_state],
                    excluded_buffer_pixel_difference=0,
                    scope="Solid native SCL values with explicit LASSO MDLOPT2 mask; all-deleted output, Blank independence, recording/replay, reader maximum native spot check; static MinMax PNG/CSV and excluded-buffer pixel invariance. No physical-mask animation, shell/beam/tshell or other-version certification."))
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--last-state", type=int, required=True)
    args = parser.parse_args()
    print(accept(args.workspace, args.executable, args.source, args.last_state))
