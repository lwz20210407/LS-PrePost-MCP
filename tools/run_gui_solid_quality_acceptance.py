"""Opt-in visible native solid quality/gate/recording tests on two synthetic Hex8 cells."""

import argparse
import json
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_solid_quality import SOLID_CHECKS
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service

MODEL = """*KEYWORD
*TITLE
Synthetic native solid quality acceptance
*NODE
1,0,0,0
2,2,0,0
3,2,1,0
4,0,1,0
5,0,0,1
6,2,0,1
7,2,1,1
8,0,1,1
9,3,0,0
10,3,1,0
11,3,0,1
12,3,1,1
*ELEMENT_SOLID
1,1,1,2,3,4,5,6,7,8
2,1,2,9,10,3,6,11,12,7
*PART
Synthetic solids
1,1,1
*SECTION_SOLID
1,1
*MAT_ELASTIC
1,1,100,0.3
*END
"""


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("native-solid-acceptance-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    source = root / "synthetic.k"
    source.write_text(MODEL, encoding="ascii")
    identity = fingerprint(source)
    service = Service(Settings(root, Path(executable), timeout=60))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session-start.json", session)
    service.show_gui_session(sid, maximize=True)
    assert service.open_in_gui_session(sid, str(source))["status"] == "succeeded"
    service.set_gui_display(sid, view="isometric", center=True, capture=False)
    requests = Path(session["directory"]) / "requests"
    exports = set(requests.rglob("model.k"))
    cases = {}
    for name in SOLID_CHECKS:
        limit = 180 if "angle" in name else 1e6
        for comparison, expected in [("gt", 0), ("lt", 2)]:
            result = service.check_gui_solid_quality(
                sid, [dict(metric=name, comparison=comparison, threshold=limit)], "mm"
            )
            cases[name + "_" + comparison] = result
            atomic_json(root / "criteria.json", cases)
            assert result["status"] == "succeeded", result.get("error")
            assert result["verification"]["criteria"][0]["violated_count"] == expected
            assert not result["checkpoint_created"]
        print(name, "pass/fail verified", flush=True)
    assert set(requests.rglob("model.k")) == exports
    service.set_gui_part_visibility(sid, "hide", [1])
    hidden = service.check_gui_solid_quality(
        sid, [dict(metric="aspect_ratio", comparison="gt", threshold=1.5)], "mm"
    )
    atomic_json(root / "hidden-parts.json", hidden)
    assert hidden["status"] == "succeeded", hidden.get("error")
    assert hidden["verification"]["criteria"][0]["violated_count"] == 1
    assert service.inspect_gui_mesh(sid)["data"]["part_visibility"] == {"1": False}
    service.set_gui_part_visibility(sid, "all")
    before = service.inspect_gui_mesh(sid, include_entities=True)["data"]
    recipe = service.create_workflow(
        "Native solid gate before coordinate edit",
        [
            dict(
                id="quality",
                action="check_gui_solid_quality",
                arguments=dict(
                    checks=[dict(metric="aspect_ratio", comparison="gt", threshold={"$param": "limit"})],
                    units="mm",
                ),
            ),
            dict(
                id="edit",
                action="set_gui_node_coordinates",
                arguments=dict(nodes=[dict(id=1, coordinates=[-0.1, None, None])], units="mm"),
            ),
        ],
        dict(limit=10),
    )
    failed = service.run_workflow(recipe["artifacts"][0]["path"], dict(limit=1.5), session_id=sid)
    atomic_json(root / "failed-gate.json", failed)
    assert failed["status"] == "failed" and failed["data"]["skipped_steps"] == ["edit"]
    assert service.inspect_gui_mesh(sid, include_entities=True)["data"]["nodes"] == before["nodes"]
    service.start_session_recording(sid)
    passed = service.run_workflow(recipe["artifacts"][0]["path"], session_id=sid)
    assert passed["status"] == "succeeded", passed.get("error")
    record = service.stop_session_recording(sid)
    template = service.parameterize_workflow(
        record["workflow"], [dict(step_id="step1", path=["checks", 0, "threshold"], parameter="limit")]
    )
    replay = service.run_workflow(template["artifacts"][0]["path"], dict(limit=1.5), session_id=sid)
    atomic_json(root / "recorded-gate.json", replay)
    assert replay["status"] == "failed" and replay["data"]["skipped_steps"] == ["step2"]
    assert service.inspect_gui_mesh(sid, include_entities=True)["data"]["nodes"] == before["nodes"]
    assert fingerprint(source) == identity
    atomic_json(
        root / "acceptance.json",
        dict(
            status="succeeded",
            session_id=sid,
            criteria_pass_fail=12,
            hidden_parts_checked_and_restored=True,
            automatic_gate_blocks_edit=True,
            recorded_threshold_gate=True,
            no_inspection_keyword_exports=True,
            source_unchanged=True,
            scope="4.13.4 synthetic Hex8 native criteria; not all solid topologies or solver checks",
        ),
    )
    print(json.dumps(dict(status="succeeded", evidence_directory=str(root))), flush=True)
    service.close_gui_session(sid, save_checkpoint=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    accept(args.workspace, args.executable)
