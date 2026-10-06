"""A04 embedded SDK, immutable dependencies, large arrays and full traceback."""

import json
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.sessions import Sessions
from tests.test_engine_native import native_case  # noqa: F401

pytestmark = pytest.mark.native

SOURCE = '''import json,numpy as np,DataCenter as dc,LsPrePost as lp
from helper import build
lp.execute_command("top")
count=int(dc.get_data("num_nodes"))
with open("support/offset.json") as stream: offset=json.load(stream)["offset"]
values=build(np,PARAMETERS["rows"],PARAMETERS["scale"])+offset
np.savez_compressed("large.npz",values=values)
with open("summary.json","w") as stream:
    json.dump({"nodes":count,"message":PARAMETERS["message"],"literal":"{{not_a_template}}"},stream)
'''


@pytest.mark.parametrize("context", ["batch", "session"])
def test_python_sdk_parameters_dependencies_npz_and_traceback(native_case, context):  # noqa: F811
    service, source = native_case
    helper = service.settings.workspace / "helper-source.py"
    helper.write_text('def build(np, rows, scale):\n    return np.arange(rows*2,dtype="float64").reshape(rows,2)*scale\n')
    data = service.settings.workspace / "offset-source.json"
    data.write_text('{"offset": 3}')
    options = dict(model=str(source / "input.k"))
    sid = None
    if context == "session":
        sid = Sessions(service.settings).start(transport="queue")["session_id"]
        assert service.open_in_gui_session(sid, str(source / "input.k"))["status"] == "succeeded"
        options = dict(session_id=sid)
    try:
        result = service.run_script("python", SOURCE, context=context, **options,
                                    parameters=dict(rows=1000000, scale=2, message="quotes ' \" and\nnewlines are data"),
                                    dependencies=[dict(path=str(helper),name="helper.py"),
                                                  dict(path=str(data),name="support/offset.json")],
                                    outputs=[dict(name="large.npz",kind="npz"),dict(name="summary.json",kind="json")],
                                    expected_counts=dict(nodes=8))
        (service.settings.workspace / "python-result.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        assert result["status"] == "succeeded", result
        assert len(json.dumps(result)) < 40000
        artifact = next(a for a in result["artifacts"] if a["kind"] == "npz")
        assert artifact["metadata"]["arrays"]["values"] == dict(shape=[1000000,2],dtype="float64",fortran_order=False,nbytes=16000000)
        with np.load(artifact["path"], allow_pickle=False) as arrays:
            assert arrays["values"][0].tolist() == [3,5]
            assert arrays["values"][-1].tolist() == [3999999,4000001]
        summary_path = next(a["path"] for a in result["artifacts"] if a["kind"] == "json")
        assert json.loads(Path(summary_path).read_text())["literal"] == "{{not_a_template}}"
        helper.write_text("def fail():\n    raise ValueError('native dependency failure')\n")
        failed = service.run_script("python", "from helper import fail\nfail()\n", context=context, **options,
                                    dependencies=[dict(path=str(helper),name="helper.py")])
        (service.settings.workspace / "python-error.json").write_text(json.dumps(failed, indent=2), encoding="utf8")
        assert failed["status"] == "failed", failed
        assert "helper.py" in failed["error"]["traceback"] and "native dependency failure" in failed["error"]["traceback"]
    finally:
        if sid:
            service.close_gui_session(sid, save_checkpoint=False)
