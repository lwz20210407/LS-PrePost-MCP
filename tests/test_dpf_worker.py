import sys
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace

import pytest

from ls_prepost_mcp import dpf_worker


def test_missing_client_probe_does_not_attempt_server(monkeypatch):
    def absent(_):
        raise PackageNotFoundError("ansys-dpf-core")
    monkeypatch.setattr(dpf_worker, "version", absent)
    report = dpf_worker.runtime_info()
    assert not report["ready_for_runtime_attempt"] and not report["server_started"]


def test_local_entry_context_no_remote_fallback_and_shutdown_on_error(monkeypatch):
    observed = {}
    server = SimpleNamespace(meet_version=lambda _: True, version="8.2",
                             shutdown=lambda: observed.update(shutdown=True))
    def start(**kwargs):
        observed.update(kwargs)
        return server
    class Sources:
        def __init__(self, **kwargs):
            assert kwargs["server"] is server

        def set_result_file_path(self, path, key):
            observed["source_key"] = key

    dpf = SimpleNamespace(start_local_server=start, AvailableServerConfigs=SimpleNamespace(InProcessServer="inprocess"),
                          AvailableServerContexts=SimpleNamespace(entry="entry"), DataSources=Sources,
                          Model=lambda *a, **kw: SimpleNamespace(metadata=SimpleNamespace(
                              result_info=SimpleNamespace(available_results=[]))))
    monkeypatch.setitem(sys.modules, "ansys.dpf", SimpleNamespace(core=dpf))
    monkeypatch.setattr(dpf_worker, "runtime_info", lambda _: dict(ready_for_runtime_attempt=True, server_path="installed"))
    with pytest.raises(ValueError, match="not available"):
        dpf_worker.execute(dict(action="export", file_type="d3plot", result="erosion_flag",
                                path="staged/d3plot", states=[1], units="1", timeout=30))
    assert observed["as_global"] is False and observed["context"] == "entry"
    assert observed["config"] == "inprocess"
    assert not observed["use_docker_by_default"] and not observed["use_pypim_by_default"]
    assert observed["shutdown"] is True and observed["source_key"] == "d3plot"
