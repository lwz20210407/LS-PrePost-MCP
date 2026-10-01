import copy
import csv
import json
import re
from contextlib import nullcontext
from pathlib import Path, PureWindowsPath

import pytest

from ls_prepost_mcp.config import Settings, scl_command_path
from ls_prepost_mcp.gui_fields import verify_context
from ls_prepost_mcp.service import Service


def mesh():
    return dict(
        nodes=[[1, 0, 0, 0], [2, 1, 0, 0]],
        elements=[dict(type="solid", id=50, nodes=[1, 2])],
        part_ids=[7],
        part_elements={"7": [50]},
        part_visibility={"7": False},
        counts=dict(nodes=2, elements=1, states=3),
        current_state=2,
        selection_ids=[50],
    )


def test_gui_scl_reuses_parser_and_never_opens_or_exits_a_model(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    commands = []
    recorded = []

    class Manager:
        def lock(self, sid):
            return nullcontext()

        def read(self, sid):
            return dict(state="ready", model_kind="d3plot", process_alive=True, process={})

        def directory(self, sid):
            return tmp_path

        def dispatch(self, sid, action, params, **options):
            if options.get("native_commands"):
                commands.extend(options["native_commands"])
                script = Path(commands[1][len("runscript ") :].strip('"')).read_text(encoding="utf-8")
                output = Path(
                    json.loads(
                        re.search(r"fp=fopen((.*))", script).group(0)[len("fp=fopen(") :].split(',"w"')[0]
                    )
                )
                assert output.is_absolute() and output.is_relative_to(tmp_path)
                with output.open("w", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["state", "time", "entity_id", "stress_x"])
                    writer.writerows([[1, 0, 50, 2], [3, 1, 50, 4]])
            return dict(status="succeeded", data=copy.deepcopy(mesh()), artifacts=[])

        def journal(self, sid, entry):
            recorded.append(entry)

    monkeypatch.setattr(service, "_session_manager", Manager)
    # The optional visible executor must not invoke the independent batch runner.
    monkeypatch.setattr("ls_prepost_mcp.native_results.execute", lambda *a, **k: pytest.fail("Batch launch"))
    result = service.gui_session_action(
        "s",
        "extract_native_fields",
        dict(
            entity_type="solid",
            entity_ids=[50],
            states=[1, 3],
            fields=["stress_x"],
            integration_point="mid",
            units="MPa",
        ),
    )
    assert result["status"] == "succeeded", result
    assert result["data"]["row_count"] == 2 and result["data"]["session_context_preserved"]
    assert commands[0] == "anim stop" and commands[-1] == "state 2"
    assert not any(c in ("new", "exit") or c.startswith("openc") for c in commands)
    assert recorded[0]["action"] == "extract_native_fields"
    assert result["artifacts"][0]["validated"]


@pytest.mark.parametrize("change", ["state", "selection", "visibility", "geometry"])
def test_field_context_must_be_preserved(change):
    before, after = mesh(), mesh()
    if change == "state":
        after["current_state"] = 3
    elif change == "selection":
        after["selection_ids"] = []
    elif change == "visibility":
        after["part_visibility"]["7"] = True
    else:
        after["nodes"][0][1] = 8
    with pytest.raises(ValueError):
        verify_context(before, after)


def test_gui_field_rejects_source_replacement_and_invalid_ids_before_native_work(tmp_path):
    service = Service(Settings(tmp_path))
    with pytest.raises(ValueError, match="current staged model"):
        service.gui_session_action("s", "extract_native_fields", {"path": "other"})
    with pytest.raises(ValueError, match="positive integers"):
        service.gui_session_action(
            "s",
            "extract_native_stress",
            dict(element_type="solid", element_ids=[True], states=[1], integration_point="mid", units="MPa"),
        )
    assert not (tmp_path / "jobs").exists()


def test_scl_windows_path_retains_native_separator_and_shared_path_validation():
    assert scl_command_path(PureWindowsPath(r"F:\owned job\extract.scl")) == '"F:\\owned job\\extract.scl"'
    with pytest.raises(ValueError, match="unsupported"):
        scl_command_path(PureWindowsPath('F:\\bad"path\\extract.scl'))
