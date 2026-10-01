from ls_prepost_mcp.gui_controls import wait_for_gui_state


def test_delayed_native_state_is_observed_without_resubmitting_switch(monkeypatch):
    states = iter([1, 1, 2])
    requests = []

    class Manager:
        def dispatch(self, sid, action, params):
            requests.append((sid, action, params))
            return dict(status="succeeded", data=dict(current_state=next(states)))

    monkeypatch.setattr("ls_prepost_mcp.gui_controls.time.sleep", lambda _: None)
    result, evidence = wait_for_gui_state(Manager(), "s", 2, 10)
    assert result["status"] == "succeeded" and len(evidence) == 3
    assert requests == [("s", "inspect_model", {})] * 3


def test_state_timeout_and_native_failures_cannot_report_success(monkeypatch):
    clock = iter([0, 11])
    monkeypatch.setattr("ls_prepost_mcp.gui_controls.time.monotonic", lambda: next(clock))

    class Manager:
        def dispatch(self, *args):
            return dict(status="succeeded", data=dict(current_state=1))

    result, evidence = wait_for_gui_state(Manager(), "s", 2, 10)
    assert result["status"] == "failed" and len(evidence) == 1
    assert "no automatic replay" in result["error"]["message"]


def test_restore_command_is_sent_once_even_when_observation_is_delayed(monkeypatch):
    states = iter([1, 3])
    commands = []

    class Manager:
        def dispatch(self, sid, action, params, **kwargs):
            commands.append(kwargs.get("native_commands", ()))
            return dict(status="succeeded", data=dict(current_state=next(states)))

    monkeypatch.setattr("ls_prepost_mcp.gui_controls.time.sleep", lambda _: None)
    result, evidence = wait_for_gui_state(Manager(), "s", 3, 10, native_commands=["anim stop", "state 3"])
    assert result["status"] == "succeeded"
    assert commands == [["anim stop", "state 3"], ()]
