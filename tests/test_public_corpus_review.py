"""Offline coverage of #92 review contracts, including the real native test body."""

import importlib
import os
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service

ROOT = Path(__file__).resolve().parents[1]
ENGINE_TEST = ROOT / "tests/test_engine_native.py"
DIAGNOSTIC_TEST = ROOT / "tests/test_public_corpus_diagnostics.py"
KNOWN_ISSUES = ROOT / "docs/KNOWN_ISSUES.md"


def native_probe(tmp_path, monkeypatch, platform):
    namespace = runpy.run_path(str(ENGINE_TEST))
    test = namespace["test_batch_include_read_preserves_source_directory"]
    # Simulate only this test's platform; never mutate Python's shared os module.
    test.__globals__["os"] = SimpleNamespace(**(vars(os) | {"name": platform}))
    module = importlib.import_module("ls_prepost_mcp.service")
    monkeypatch.setattr(module, "_windows", lambda: platform == "nt", raising=False)
    monkeypatch.setattr(Settings, "native_executable", lambda _: tmp_path / "unused.exe")
    monkeypatch.setattr(module, "run_batch", lambda *a, **kw: pytest.fail("Unexpected native launch"))
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "input.k").write_text("*KEYWORD\n*NODE\n1,0,0,0\n*END\n", encoding="ascii")
    service = Service(Settings(tmp_path / "source-work", allowed_roots=(tmp_path,)))
    return test, (service, fixture), Mock(), namespace


def test_windows_native_regression_asserts_refusal_without_xfail(tmp_path, monkeypatch):
    test, native_case, request, _ = native_probe(tmp_path, monkeypatch, "nt")
    test(native_case, tmp_path, "输入 模型", request)
    request.node.add_marker.assert_not_called()
    parameters = next(mark for mark in test.pytestmark if mark.name == "parametrize").args[1]
    for parameter in parameters:
        assert not any(mark.name == "xfail" for mark in getattr(parameter, "marks", ()))
    assert not (tmp_path / "work/jobs").exists()


@pytest.mark.parametrize("message,expected", [
    ("There is no d3plot data!", "observed"), ("Unexpected failure", "unrelated"),
])
def test_non_windows_native_gap_keeps_strict_diagnostic_match(tmp_path, monkeypatch, message, expected):
    test, native_case, request, namespace = native_probe(tmp_path, monkeypatch, "posix")
    monkeypatch.setattr(Service, "inspect_model", lambda *a, **kw: {
        "status": "failed", "bridge_error": {"message": message}, "job_directory": str(tmp_path)})
    error = namespace["NativeIncludeReadError"] if expected == "observed" else AssertionError
    with pytest.raises(error):
        test(native_case, tmp_path, "输入 模型", request)
    # Both parameter marks and run-time marks are valid pytest mechanisms.
    markers = [call.args[0] for call in request.node.add_marker.call_args_list]
    parameters = next(mark for mark in test.pytestmark if mark.name == "parametrize").args[1]
    for parameter in parameters:
        if "输入 模型" in getattr(parameter, "values", ()):
            markers.extend(parameter.marks)
    marker = next(mark for mark in markers if mark.name == "xfail")
    assert marker.name == "xfail" and marker.kwargs["strict"] is True
    assert marker.kwargs["raises"] is namespace["NativeIncludeReadError"]


def test_guard_regression_does_not_replace_os_dependencies(tmp_path, monkeypatch):
    module = importlib.import_module("ls_prepost_mcp.service")
    original = Settings.input_path

    def input_path(settings, value, **kwargs):
        # Guard tests must also work when ordinary preflight uses os.path.
        assert module.os.path.isabs(value)
        assert module.os.environ is os.environ
        return original(settings, value, **kwargs)

    monkeypatch.setattr(Settings, "input_path", input_path)
    test = runpy.run_path(str(DIAGNOSTIC_TEST))[
        "test_windows_unicode_include_root_rejected_before_job_creation"]
    test(tmp_path, monkeypatch)


def test_known_issues_records_prelaunch_refusal_and_observed_failures():
    text = KNOWN_ISSUES.read_text(encoding="utf8")
    section = text.split("## I01：批处理输入路径暂存补修", 1)[1].split("\n## ", 1)[0]
    for fact in ("Windows", "含 INCLUDE 的非 ASCII 根路径", "创建作业前", "ValueError",
                 "0xC0000005", "rc=0", "test_engine_native.py", "i04-diagnostics/report.md"):
        assert fact in section
    assert "非 Windows" in section and "严格 xfail" in section


def test_known_issues_keeps_unicode_member_paths_unverified():
    text = KNOWN_ISSUES.read_text(encoding="utf8")
    section = text.split("## I01：批处理输入路径暂存补修", 1)[1].split("\n## ", 1)[0]
    for fact in ("未验证", "非 ASCII 的 INCLUDE 成员名", "*INCLUDE_PATH", "根路径"):
        assert fact in section


def test_known_issues_keeps_lasso_tail_gap_with_shared_owner():
    text = KNOWN_ISSUES.read_text(encoding="utf8")
    section = text.split("## I04：LASSO 结束标记后尾数据", 1)[1].split("\n## ", 1)[0]
    for fact in ("2.0.4", "11", "-999999", "Claude", "未修复", "不删状态",
                 "i04-diagnostics/report.md"):
        assert fact in section
