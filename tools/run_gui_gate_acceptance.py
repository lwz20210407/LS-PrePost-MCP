"""Opt-in visible native quality-gate acceptance on a fresh owned synthetic session.

Requires Windows, installed LS-PrePost and its working embedded Python. Does not
touch user models or existing sessions. --stop-file cancels between operations
and leaves the owned window/evidence intact. Never used by hosted CI.
"""

import argparse
import json
import time
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service

MODEL = """*KEYWORD
*TITLE
Synthetic native workflow gate acceptance
*NODE
1,0,0,0
2,2,0,0
3,2,1,0
4,0,1,0
*ELEMENT_SHELL
100,10,1,2,3,4
*PART
Synthetic shell
10,1,1
*SECTION_SHELL
1,2,0.833333,3
1,1,1,1
*MAT_ELASTIC
1,1,100,0.3
*SET_NODE_LIST
7
1,2
*END
"""


def accept(workspace, executable, hold_seconds=0, stop_file=None):
    if not 0 <= hold_seconds <= 600:
        raise ValueError("hold_seconds must be 0..600")
    root = Path(workspace).resolve() / ("native-gate-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    stop = Path(stop_file).resolve() if stop_file else None

    def active():
        if stop and stop.exists():
            raise RuntimeError("Native acceptance interrupted; no further GUI commands sent")

    source = root / "synthetic.k"
    source.write_text(MODEL, encoding="ascii")
    identity = fingerprint(source)
    service = Service(Settings(root, Path(executable), timeout=45))
    active()
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    print("SESSION", sid, str(root), flush=True)
    active()
    service.show_gui_session(sid, maximize=True)
    opened = service.open_in_gui_session(sid, str(source))
    assert opened["status"] == "succeeded", opened
    service.set_gui_display(sid, view="top", display_mode="shaded", center=True, capture=False)
    cases = {}

    def run_case(name, first, expect_success, offset):
        active()
        before = service.inspect_gui_mesh(sid, include_entities=True)
        assert before["status"] == "succeeded", before
        definition = service.create_workflow(
            name,
            [
                dict(id="check", **first),
                dict(
                    id="dependent_edit",
                    action="translate_gui_nodes",
                    arguments=dict(
                        node_ids=[1, 2, 3, 4], offset=[0, 0, offset], units="synthetic length units"
                    ),
                ),
            ],
        )
        result = service.run_workflow(definition["artifacts"][0]["path"], session_id=sid)
        cases[name] = result
        atomic_json(root / "cases.json", cases)
        print(name, result["status"], result["data"]["skipped_steps"], flush=True)
        assert result["status"] == ("succeeded" if expect_success else "failed"), result
        active()
        after = service.inspect_gui_mesh(sid, include_entities=True)
        assert after["status"] == "succeeded", after
        expected = [
            [row[0], row[1], row[2], row[3] + (offset if expect_success else 0)]
            for row in before["data"]["nodes"]
        ]
        assert after["data"]["nodes"] == expected, (expected, after["data"]["nodes"])
        assert before["data"]["elements"] == after["data"]["elements"]
        return result

    run_case(
        "passing_shell_check",
        dict(
            action="check_gui_shell_quality",
            arguments=dict(thresholds={"aspect_ratio": 10}, units="synthetic length units"),
        ),
        True,
        0.25,
    )
    failed = run_case(
        "failing_shell_check",
        dict(
            action="check_gui_shell_quality",
            arguments=dict(thresholds={"aspect_ratio": 1.5}, units="synthetic length units"),
        ),
        False,
        10,
    )
    assert failed["data"]["steps"]["check"]["verification"]["metrics"]["aspect_ratio"]["violated_count"] == 1
    failed = run_case("keyword_findings_block", dict(action="check_gui_keywords", arguments={}), False, 20)
    assert failed["data"]["steps"]["check"]["verification"]["totals"]["unref"] == 1
    allowed = run_case(
        "explicit_keyword_policy",
        dict(
            action="check_gui_keywords",
            arguments={},
            quality_policy="report_only",
            checks=[
                dict(path=["verification", "totals", "error"], operator="eq", value=0),
                dict(path=["verification", "totals", "undefine"], operator="eq", value=0),
                dict(path=["verification", "totals", "warning"], operator="eq", value=0),
                dict(path=["verification", "totals", "unref"], operator="le", value=1),
            ],
        ),
        True,
        0.25,
    )
    active()
    recorded_baseline = service.inspect_gui_mesh(sid, include_entities=True)["data"]["nodes"]
    service.start_session_recording(sid)
    cases["recorded_explicit_policy"] = service.run_workflow(allowed["parameters"]["path"], session_id=sid)
    assert cases["recorded_explicit_policy"]["status"] == "succeeded"
    recording = service.stop_session_recording(sid)
    definition = json.loads(Path(recording["workflow"]).read_text(encoding="utf8"))
    assert recording["managed_steps"] == 2
    assert definition["steps"][0]["quality_policy"] == "report_only"
    assert definition["steps"][0]["checks"][3]["value"] == 1
    template = service.parameterize_workflow(
        recording["workflow"],
        [dict(step_id="step1", section="checks", path=[3, "value"], parameter="allowed_unreferenced")],
    )
    for name, limit, expected in [("replay_gate_pass", 1, "succeeded"), ("replay_gate_blocks", 0, "failed")]:
        active()
        result = service.run_workflow(template["artifacts"][0]["path"], dict(allowed_unreferenced=limit), sid)
        cases[name] = result
        atomic_json(root / "cases.json", cases)
        print(name, result["status"], result["data"]["skipped_steps"], flush=True)
        assert result["status"] == expected, result
        nodes = service.inspect_gui_mesh(sid, include_entities=True)["data"]["nodes"]
        expected_nodes = [
            [row[0], row[1], row[2], row[3] + (0.25 if limit else 0)] for row in recorded_baseline
        ]
        assert nodes == expected_nodes
    atomic_json(root / "recording.json", dict(recording=recording, template=template))
    active()
    snapshot = service.set_gui_display(sid, view="top", display_mode="shaded", center=True, capture=True)
    assert snapshot["status"] == "succeeded", snapshot
    assert source.read_text(encoding="ascii") == MODEL
    summary = dict(
        mode="visible_native_gui",
        directory=str(root),
        session_id=sid,
        native_software_launched=True,
        input_identity=identity,
        cases={
            k: dict(
                status=v["status"],
                completed_steps=v["data"]["completed_steps"],
                skipped_steps=v["data"]["skipped_steps"],
            )
            for k, v in cases.items()
        },
        final_snapshot=snapshot["artifacts"],
        unchanged_source=True,
    )
    atomic_json(root / "acceptance.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    deadline = time.monotonic() + hold_seconds
    while time.monotonic() < deadline and service.inspect_gui_session(sid)["process_alive"]:
        if stop and stop.exists():
            print("Interrupted: leaving owned GUI intact", flush=True)
            return summary
        time.sleep(0.5)
    active()
    if service.inspect_gui_session(sid)["process_alive"]:
        closed = service.close_gui_session(sid)
        atomic_json(root / "session-close.json", closed)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--hold-seconds", type=int, default=0)
    parser.add_argument("--stop-file")
    args = parser.parse_args()
    accept(args.workspace, args.executable, args.hold_seconds, args.stop_file)
