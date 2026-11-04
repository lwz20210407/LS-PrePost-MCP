"""No Windows API/window is created by these read-only probe contract tests."""
import ctypes
from types import SimpleNamespace

import pytest

from ls_prepost_mcp.windows_transport import WindowsCommandTransport


@pytest.mark.parametrize("reply,after,accepted", [(0, {"main_window": 7, "enabled": True}, False),
    (1, {"main_window": 7, "enabled": False}, False),
    (1, {"main_window": 8, "enabled": True}, False),
    (1, {"main_window": 7, "enabled": True}, True)])
def test_readonly_probe_requires_response_and_the_same_enabled_window(reply, after, accepted):
    transport = WindowsCommandTransport.__new__(WindowsCommandTransport)
    transport.ctypes, transport.pid = ctypes, 123
    transport.preflight = lambda: {"main_window": 7, "enabled": True}
    transport.window_state = lambda: after
    calls = []
    def message(*args):
        calls.append(args[:6])
        return reply
    transport.u = SimpleNamespace(SendMessageTimeoutW=message)
    if accepted:
        result = transport.probe_idle()
        assert result["responsive"] and "host validation" in result["scope"]
    else:
        with pytest.raises(RuntimeError):
            transport.probe_idle()
    assert calls == [(7, 0, 0, 0, 3, 2000)]  # WM_NULL only, no command or key input
