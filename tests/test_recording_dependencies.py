import json
import os
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.sessions import process_identity
from ls_prepost_mcp.workflows import recording_argument_links


def recording_service(tmp_path):
    service = Service(Settings(tmp_path))
    manager = service._session_manager()
    sid = "d" * 32
    directory = manager.directory(sid)
    directory.mkdir(parents=True)
    atomic_json(
        directory / "session.json",
        dict(
            process=process_identity(os.getpid()),
            state="ready",
            model_kind="d3plot",
            recording=dict(
                id="e" * 32,
                initial_model=None,
                initial_file_type="d3plot",
                native_offset=None,
                journal_offset=0,
            ),
        ),
    )
    return service, manager, sid, directory


def test_recorded_selection_change_drives_new_history_and_real_curve_math(tmp_path, monkeypatch):
    service, manager, sid, directory = recording_service(tmp_path)
    requests = []

    def selected(session_id, **args):
        result = dict(
            status="succeeded",
            session_id=session_id,
            job_directory=str(directory / uuid.uuid4().hex),
            verification=dict(selected_ids=sorted(args["entity_ids"])),
        )
        manager.journal(session_id, dict(action="select_gui_entities", parameters=args, result=result))
        return result

    def history(session_id, action, parameters):
        requests.append(parameters["node_ids"])
        output = directory / uuid.uuid4().hex
        output.mkdir()
        curves = []
        for uid in parameters["node_ids"]:
            path = output / (str(uid) + ".csv")
            path.write_text("time,value\n0,%d\n1,%d\n" % (uid, uid + 1))
            curves.append(dict(path=str(path)))
        result = dict(
            status="succeeded", session_id=session_id, job_directory=str(output), data=dict(curves=curves)
        )
        manager.journal(session_id, dict(action=action, parameters=parameters, result=result))
        return result

    monkeypatch.setattr(service, "select_gui_entities", selected)
    monkeypatch.setattr(service, "gui_session_action", history)
    made = service.create_workflow(
        "Dependency recording",
        [
            dict(
                id="selection",
                action="select_gui_entities",
                arguments=dict(entity_type="node", entity_ids=[1, 2]),
            ),
            dict(
                id="history",
                action="extract_node_history",
                arguments=dict(
                    node_ids={"$result": "selection", "path": ["verification", "selected_ids"]},
                    quantity="displacement",
                    states=[1, 2],
                    units="mm",
                ),
            ),
            dict(
                id="relative",
                action="combine_history_curves",
                arguments=dict(
                    paths=[{"$result": "history", "path": ["data", "curves", i, "path"]} for i in (0, 1)],
                    operation="difference",
                    units="mm",
                ),
            ),
        ],
    )
    first = service.run_workflow(made["artifacts"][0]["path"], session_id=sid)
    assert first["status"] == "succeeded", first
    recorded = service.stop_session_recording(sid)
    assert recorded["status"] == "succeeded" and recorded["managed_steps"] == 3
    recipe = json.loads(Path(recorded["workflow"]).read_text())
    assert recipe["steps"][1]["arguments"]["node_ids"] == {
        "$result": "step1",
        "path": ["verification", "selected_ids"],
    }
    assert recipe["steps"][2]["arguments"]["paths"][0]["$result"] == "step2"
    parameterized = service.parameterize_workflow(
        recorded["workflow"], [dict(step_id="step1", path=["entity_ids"], parameter="nodes")]
    )
    second = service.run_workflow(parameterized["artifacts"][0]["path"], dict(nodes=[6, 4]), session_id=sid)
    assert second["status"] == "succeeded", second
    assert requests == [[1, 2], [4, 6]]
    curve = Path(second["data"]["steps"]["step3"]["artifacts"][0]["path"])
    assert all(float(row.split(",")[1]) == -2 for row in curve.read_text().splitlines()[1:])
    old_curve = first["data"]["steps"]["relative"]["artifacts"][0]["path"]
    assert str(curve) != old_curve


def test_only_explicit_links_are_preserved_and_artifacts_keep_their_index():
    template = dict(ids=[1, 2], other={"$param": "ids"}, path={"$artifact": "export", "index": 2})
    links = recording_argument_links(template, dict(export=dict(job_directory="unique-job")))
    assert links == [
        dict(argument_path=["path"], source_job_directory="unique-job", result_path=["artifacts", 2, "path"])
    ]


def test_argument_resolution_failure_marks_partial_recording_for_review(tmp_path, monkeypatch):
    service, manager, sid, directory = recording_service(tmp_path)
    made = service.create_workflow(
        "Invalid dependency",
        [
            dict(id="source", action="process_curve", arguments={}),
            dict(id="bad", action="process_curve", arguments=dict(path={"$artifact": "source"})),
        ],
    )
    monkeypatch.setattr(service, "process_curve", lambda **kw: dict(status="succeeded", artifacts=[]))
    result = service.run_workflow(made["artifacts"][0]["path"], session_id=sid)
    assert result["status"] == "failed" and result["data"]["failure_phase"] == "argument_resolution"
    record = service.stop_session_recording(sid)
    assert record["status"] == "needs_review" and record["managed_steps"] == 1
