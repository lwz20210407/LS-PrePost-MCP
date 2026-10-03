import pytest

from ls_prepost_mcp.windows_transport import WindowsCommandTransport, resolve_command_candidate


def candidate(hwnd=1, **changes):
    return dict(dict(hwnd=hwnd, class_name="Edit", main_title="LS-PrePost test", text=">", style=0,
                     control_id=30827, visible=True, enabled=True, history_peer=True), **changes)


def test_prompt_fallback_handles_changed_id_but_rejects_form_fields():
    assert resolve_command_candidate([candidate(control_id=999), candidate(2, control_id=100, text="1.0")]) == 1
    assert resolve_command_candidate([candidate(control_id=999, style=4)]) == 1
    for row in (candidate(text="", control_id=999), candidate(control_id=999, history_peer=False), candidate(style=0x800),
                candidate(visible=False), candidate(main_title="Node Editing")):
        with pytest.raises(RuntimeError):
            resolve_command_candidate([row])
    with pytest.raises(RuntimeError, match="unique"):
        resolve_command_candidate([candidate(control_id=998), candidate(2, control_id=999)])
    with pytest.raises(RuntimeError, match="Ambiguous"):
        resolve_command_candidate([candidate(), candidate(2)])


def test_menu_ids_are_taken_from_current_tree(monkeypatch):
    transport = object.__new__(WindowsCommandTransport)
    transport.pid = 123
    observed = []
    def open_menu(path):
        observed.append(path)
        return dict(path=path, command_id=998877)
    monkeypatch.setattr(transport, "open_menu_item", open_menu)
    assert transport.open_panel("duplicate_nodes")["menu_id"] == 998877
    assert observed == [["FEM", "Element Tools", "Duplicate Nodes"]]
