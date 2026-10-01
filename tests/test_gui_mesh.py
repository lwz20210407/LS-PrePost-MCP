import copy

import numpy as np
import pytest

from ls_prepost_mcp.gui_mesh import (
    check_no_collapse,
    mesh_index,
    verify_merge,
    verify_reverse,
    verify_transform,
)
from ls_prepost_mcp.native_config import isolate_preferences


def mesh():
    return dict(
        nodes=[[1, 0, 0, 0], [2, 1, 0, 0], [3, 1, 1, 0], [4, 0, 1, 0], [5, 0, 0, 0]],
        elements=[dict(type="shell", id=10, nodes=[5, 2, 3, 4])],
        part_ids=[1],
    )


def test_native_merge_checks_actual_survivor_and_connectivity():
    before = mesh()
    after = copy.deepcopy(before)
    after["nodes"].pop()
    after["elements"][0]["nodes"][0] = 1
    assert verify_merge(before, after, 1e-4)["node_map"] == {"5": 1}
    after["elements"][0]["nodes"][0] = 2
    with pytest.raises(ValueError, match="connectivity"):
        verify_merge(before, after, 1e-4)


def test_native_merge_rejects_unrelated_removal_movement_and_collapsed_elements():
    before = mesh()
    check_no_collapse(*mesh_index(before), 1e-4)
    bad = copy.deepcopy(before)
    bad["nodes"] = bad["nodes"][:1] + bad["nodes"][2:]
    with pytest.raises(ValueError, match="missing node"):
        verify_merge(before, bad, 1e-4)
    bad = copy.deepcopy(before)
    bad["nodes"][0][1] = 9
    with pytest.raises(ValueError, match="coordinates"):
        verify_merge(before, bad, 1e-4)
    before["elements"][0]["nodes"] = [1, 2, 3, 5]
    with pytest.raises(ValueError, match="collapse"):
        check_no_collapse(*mesh_index(before), 1e-4)


def test_noop_duplicate_command_cannot_pass_verification():
    before = mesh()
    with pytest.raises(ValueError, match="remain"):
        verify_merge(before, before, 1e-4)


def test_native_partial_transform_checks_unselected_nodes():
    before = mesh()
    after = copy.deepcopy(before)
    for row in after["nodes"]:
        if row[0] in (2, 3):
            row[1] += 2
    result = verify_transform(before, after, {2, 3}, lambda xyz: xyz + np.array([2, 0, 0]))
    assert result["maximum_coordinate_error"] == 0
    after["nodes"][0][1] = 5
    with pytest.raises(ValueError, match="exactly"):
        verify_transform(before, after, {2, 3}, lambda xyz: xyz + np.array([2, 0, 0]))


def test_restart_restores_opened_input_when_no_explicit_checkpoint(tmp_path, monkeypatch):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    s = Service(Settings(tmp_path))

    class Manager:
        def read(self, sid):
            return dict(
                process_alive=False, model_kind="keyword", last_checkpoint=None, staged_model="staged.k"
            )

    calls = []
    monkeypatch.setattr(s, "_session_manager", Manager)
    monkeypatch.setattr(s, "start_gui_session", lambda: dict(session_id="new"))
    monkeypatch.setattr(s, "show_gui_session", lambda *args, **kwargs: None)

    def opened(sid, path, kind):
        calls.append((sid, path, kind))
        return dict(status="succeeded")

    monkeypatch.setattr(s, "open_in_gui_session", opened)
    assert s.restart_gui_session("old")["status"] == "succeeded"
    assert calls == [("new", "staged.k", "keyword")]


def test_shell_normal_verification_checks_orientation_and_untouched_entities():
    before = mesh()
    before["elements"].append(dict(type="beam", id=11, nodes=[1, 2]))
    after = copy.deepcopy(before)
    after["elements"][0]["nodes"] = [5, 4, 3, 2]
    assert verify_reverse(before, after)["reversed_shells"] == 1
    with pytest.raises(ValueError, match="not reversed"):
        verify_reverse(before, before)
    after["elements"][1]["nodes"] = [2, 1]
    with pytest.raises(ValueError, match="non-shell"):
        verify_reverse(before, after)


def test_private_native_preferences_preserve_original_and_consent(tmp_path):
    source = tmp_path / "user-config"
    source.write_bytes(
        b"*\npythonhome = C:/existing/python\nansys_apip = 0\nsession_file = old.cfile\nmessage_file = old.msg\nbackground_color = 1,1,1\n"
    )
    before = source.read_bytes()
    jobs = [tmp_path / "session1", tmp_path / "session2"]
    for job in jobs:
        job.mkdir()
        env, info = isolate_preferences(
            tmp_path / "lsprepost4.13.exe", job, {"LSPP_CONFIG_SOURCE": str(source)}
        )
        copied = (job / "native-config" / "lsppconf").read_bytes()
        assert b"ansys_apip = 0" in copied and b"pythonhome = C:/existing/python" in copied
        assert b"background_color = 1,1,1" in copied and b"old.cfile" not in copied
        assert str(job / "native-config") == env["LSTC_FILE"]
        assert info["source_modified"] is False
    assert source.read_bytes() == before
    assert (jobs[0] / "native-config/lsppconf").read_bytes() != (
        jobs[1] / "native-config/lsppconf"
    ).read_bytes()


def test_partial_normal_reversal_checks_unselected_shells():
    before = mesh()
    before["elements"].append(dict(type="shell", id=20, nodes=[1, 2, 3, 4]))
    after = copy.deepcopy(before)
    after["elements"][0]["nodes"] = [5, 4, 3, 2]
    assert verify_reverse(before, after, {10})["reversed_shells"] == 1
    after["elements"][1]["nodes"] = [1, 4, 3, 2]
    with pytest.raises(ValueError, match="unselected"):
        verify_reverse(before, after, {10})
