import io
import json
import runpy
import zipfile

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import check_artifact
from ls_prepost_mcp.program_bundle import python_wrapper
from ls_prepost_mcp.service import Service


def test_python_parameters_are_data_and_change_execution_identity(tmp_path):
    service = Service(Settings(tmp_path))
    code = "assert isinstance(PARAMETERS['value'], str)\n"
    a = service.prepare_native_program("python", code=code, script_parameters=dict(value="x'\nraise RuntimeError()"))
    b = service.prepare_native_program("python", code=code, script_parameters=dict(value="different"))
    assert a["data"]["sha256"] != b["data"]["sha256"]
    directory = service.jobs.root / a["job_id"]
    wrapper = directory / "bootstrap.py"
    wrapper.write_text(python_wrapper(directory, [], a["data"]["python_parameters"]), encoding="utf8")
    runpy.run_path(str(wrapper))
    assert json.loads((directory / "python-result.json").read_text())["ok"]


def test_npz_reads_headers_and_crc_without_loading_arrays(tmp_path, monkeypatch):
    path = tmp_path / "arrays.npz"
    np.savez_compressed(path, coordinates=np.arange(24, dtype="float64").reshape(8, 3))
    monkeypatch.setattr(np, "load", lambda *a, **kw: pytest.fail("Do not materialize arrays"))
    artifact = check_artifact(path, "npz")
    assert artifact["arrays"]["coordinates"] == dict(shape=[8, 3], dtype="float64", fortran_order=False, nbytes=192)
    assert len(artifact["sha256"]) == 64


def test_npz_rejects_pickle_and_truncated_archive(tmp_path):
    path = tmp_path / "bad.npz"
    np.savez(path, objects=np.array([dict(x=1)], dtype=object))
    with pytest.raises(ValueError, match="pickle"):
        check_artifact(path, "npz")
    buffer = io.BytesIO()
    np.save(buffer, np.arange(4, dtype="float64"))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("values.npy", buffer.getvalue()[:-8])
    with pytest.raises(ValueError, match="payload length"):
        check_artifact(path, "npz")


def test_python_wrapper_preserves_full_dependency_traceback(tmp_path):
    (tmp_path / "helper.py").write_text("def fail():\n    raise ValueError('specific fault')\n")
    (tmp_path / "program.py").write_text("import helper\nhelper.fail()\n")
    script = tmp_path / "bootstrap.py"
    script.write_text(python_wrapper(tmp_path, ["helper.py"]))
    runpy.run_path(str(script))
    result = json.loads((tmp_path / "python-result.json").read_text())
    assert not result["ok"] and "helper.py" in result["traceback"] and "specific fault" in result["traceback"]
