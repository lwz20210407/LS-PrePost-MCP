"""I03: real SCL binout paths, with an ASCII control and explicit KI-049 gap."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tools.native_regression import resolve_value

pytestmark = pytest.mark.native


class NativeUnicodeJobError(RuntimeError):
    pass


@pytest.mark.parametrize("folder", ["ascii job", pytest.param("中文 作业", marks=pytest.mark.xfail(
    strict=True, raises=NativeUnicodeJobError, reason="KI-049: native Unicode job configuration remains unverified"))])
def test_binout_scl_job_paths(tmp_path, pytestconfig, folder):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Native binout paths require --run-native")
    exe = pytestconfig.getoption("--native-executable")
    if not exe:
        pytest.fail("Set --native-executable")
    np = pytest.importorskip("numpy")
    Binout = pytest.importorskip("lasso.dyna").Binout
    source = Path(resolve_value({"corpus": "binout_forces"}))
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    reader = Binout(str(source))
    times = reader.read("matsum", "time")
    uid = int(reader.read("matsum", "ids")[0])
    values = reader.read("matsum", "internal_energy")[:, 0]
    service = Service(Settings(tmp_path / folder, Path(exe), (source.parent,), timeout=60))
    result = service.extract_native_binout_curve(str(source), "matsum", "internal_energy", "raw", entity_id=uid)
    (tmp_path / "binout-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    if not folder.isascii() and result["status"] != "succeeded":
        raise NativeUnicodeJobError(result.get("error"))
    assert result["status"] == "succeeded", result
    with Path(result["artifacts"][0]["path"]).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(times)
    np.testing.assert_allclose([float(row["time"]) for row in rows], times, rtol=2e-5, atol=1e-8)
    np.testing.assert_allclose([float(row["value"]) for row in rows], values, rtol=2e-5, atol=1e-8)
