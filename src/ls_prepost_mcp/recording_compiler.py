"""Translate a documented subset of recorded cfile commands into typed GUI steps.

Unknown commands remain explicit review blockers; this is not a shell/script
execution gateway. Original recording bytes stay in the source job.
"""

import shlex

from .gui_quality import SHELL_CHECKS


def compile_commands(text, units, recorded_model_index=None):
    if recorded_model_index is not None and (
        type(recorded_model_index) is not int or recorded_model_index < 0
    ):
        raise ValueError("recorded_model_index must be a nonnegative integer")
    steps = []
    unknown = []
    selected = []
    target = None
    selection_initialized = False
    buffers = {}
    pending = None

    def emit(action, arguments):
        steps.append(dict(id="step" + str(len(steps) + 1), action=action, arguments=arguments))
        return {"$result": steps[-1]["id"], "path": ["verification", "selected_ids"]}

    quality_names = {spec[2]: name for name, spec in SHELL_CHECKS.items()}

    def selection_id(value):
        fields = value.split("/")
        if len(fields) > 2 or not all(v.isdigit() for v in fields) or int(fields[0]) <= 0:
            raise ValueError("Expected one positive user ID and optional model index")
        if len(fields) == 2 and (recorded_model_index is None or int(fields[1]) != recorded_model_index):
            raise ValueError(
                "Model-qualified IDs require an explicit matching recorded_model_index; multi-model remapping is not supported"
            )
        return int(fields[0])

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("$", "#")):
            continue
        try:
            words = [
                x[1:-1] if x.startswith('"') and x.endswith('"') else x
                for x in shlex.split(line, posix=False)
            ]
            head = words[0].lower()
            if head == "c":
                continue
            if head == "runpython":
                # A raw recording cannot certify what an opaque script changed.
                unknown.append(
                    dict(
                        line=lineno,
                        command=line,
                        reason="Opaque Python call; use managed operation recording or replace with reviewed typed steps",
                    )
                )
            elif head in ("exit", "quit", "t"):
                continue
            elif head == "new":
                emit("new_model", {})
                selected, target, buffers = [], None, {}
                selection_initialized = True
            elif head in ("open", "openc") and len(words) == 3 and words[1] in ("keyword", "d3plot"):
                emit("open_model", dict(path=words[2], file_type=words[1]))
                selected, target, buffers = [], None, {}
                selection_initialized = True
            elif len(words) == 3 and words[:2] == ["save", "keyword"]:
                emit("checkpoint", {})
            elif head in ("top", "bottom", "left", "right", "front", "back", "home") and len(words) == 1:
                emit("set_gui_display", dict(view=head, capture=False))
            elif words == ["isometric", "x"]:
                emit("set_gui_display", dict(view="isometric", capture=False))
            elif head in ("shad", "wire", "hide", "edge", "feat", "grid", "view") and len(words) == 1:
                modes = dict(
                    shad="shaded",
                    wire="wireframe",
                    hide="hidden",
                    edge="edge",
                    feat="feature",
                    grid="grid",
                    view="flat",
                )
                emit("set_gui_display", dict(display_mode=modes[head], capture=False))
            elif head in ("parallel", "perspective") and len(words) == 1:
                emit("set_gui_display", dict(projection=head, capture=False))
            elif head == "background" and len(words) == 4:
                emit("set_gui_display", dict(background=[float(v) for v in words[1:]], capture=False))
            elif (
                head in ("showlegend", "showtriad", "timestamp")
                and len(words) == 2
                and words[1] in ("0", "1")
            ):
                name = dict(showlegend="legend", showtriad="triad", timestamp="timestamp", title="title")[
                    head
                ]
                emit("set_gui_display", {name: words[1] == "1", "capture": False})
            elif len(words) == 3 and words[:2] == ["title", "toggle"] and words[2] in ("0", "1"):
                emit("set_gui_display", dict(title=words[2] == "1", capture=False))
            elif words == ["ac"]:
                emit("set_gui_display", dict(center=True, capture=False))
            elif words == ["pfringe"]:
                continue
            elif head == "fringe" and len(words) == 2:
                emit("set_gui_display", dict(fringe_code=int(words[1]), capture=False))
            elif head == "state" and len(words) == 2 and words[1].isdigit():
                emit("set_gui_display", dict(state=int(words[1]), capture=False))
            elif words == ["pall"]:
                emit("set_gui_part_visibility", dict(mode="all"))
            elif head in ("+m", "-m", "m") and len(words) == 2:
                emit(
                    "set_gui_part_visibility",
                    dict(
                        mode={"+m": "show", "-m": "hide", "m": "isolate"}[head],
                        part_ids=[int(v) for v in words[1].split(",")],
                    ),
                )
            elif words == ["genselect", "clear"]:
                selected = []
                selection_initialized = True
                if target:
                    emit("select_gui_entities", dict(entity_type=target, entity_ids=[]))
            elif (
                len(words) == 3
                and words[:2] == ["genselect", "target"]
                and words[2] in ("node", "shell", "part", "element")
            ):
                if not selection_initialized or selected != []:
                    raise ValueError("Declare an explicit clear before changing the selection target")
                selected, target = [], words[2]
                emit("select_gui_entities", dict(entity_type=target, entity_ids=[]))
            elif (
                len(words) == 5
                and words[0] == "genselect"
                and words[1] in ("node", "shell", "part", "element")
                and words[2] in ("add", "remove")
                and words[3] == words[1]
            ):
                if target != words[1]:
                    raise ValueError("Selection target must be declared and match entity commands")
                uid = selection_id(words[4])
                if isinstance(selected, list):
                    selected = sorted(set(selected) | {uid} if words[2] == "add" else set(selected) - {uid})
                    emit("select_gui_entities", dict(entity_type=target, entity_ids=selected))
                else:
                    selected = emit(
                        "combine_gui_selections",
                        dict(
                            entity_type=target,
                            left_ids=selected,
                            right_ids=[uid],
                            operation="union" if words[2] == "add" else "difference",
                        ),
                    )
            elif words == ["genselect", "whole"]:
                if not target:
                    raise ValueError("Whole selection requires an explicit entity target")
                selected = emit("select_gui_entities", dict(entity_type=target))
            elif words == ["genselect", "reverse"]:
                if not target:
                    raise ValueError("Reverse selection requires an explicit entity target")
                selected = emit(
                    "select_gui_entities", dict(entity_type=target, entity_ids=selected, invert=True)
                )
            elif len(words) == 3 and words[:2] == ["genselect", "save"]:
                slot = int(words[2]) + 1
                if not 1 <= slot <= 10 or target not in ("node", "shell", "part") or selected == []:
                    raise ValueError("Buffer save needs a supported nonempty selection and slot 0..9")
                emit("save_gui_selection_buffer", dict(entity_type=target, entity_ids=selected, slot=slot))
                buffers[slot] = target
            elif len(words) == 3 and words[:2] == ["genselect", "load"]:
                slot = int(words[2]) + 1
                if slot not in buffers or target != buffers[slot] or selected != []:
                    raise ValueError(
                        "Buffer load requires a matching prior save and explicit clear in this recording"
                    )
                selected = emit("load_gui_selection_buffer", dict(slot=slot))
            elif words == ["normal", "reverse"]:
                if target != "shell" or selected == []:
                    raise ValueError("Normal reverse requires a nonempty declared shell selection")
                emit("reverse_gui_shell_normals", dict(shell_ids=selected, units=units))
            elif words == ["elemcheck", "shell", "init"]:
                continue
            elif len(words) == 4 and words[:2] == ["elemcheck", "shell"] and words[2] in quality_names:
                emit(
                    "check_gui_shell_quality",
                    dict(thresholds={quality_names[words[2]]: float(words[3])}, units=units),
                )
            elif head == "meshing" and len(words) >= 4 and words[2] == "create" and words[1] == "boxsolid":
                if pending:
                    raise ValueError("Previous operation was not accepted")
                values = [float(v) for v in words[3:]]
                if len(values) != 10 or values[9] != 0:
                    raise ValueError("Unsupported box mesh variant")
                divisions = [int(v) for v in values[6:9]]
                if divisions != values[6:9]:
                    raise ValueError("Nonintegral mesh divisions")
                pending = dict(
                    kind="boxsolid",
                    action="create_solid_box",
                    arguments=dict(
                        origin=values[:3],
                        size=[values[i + 3] - values[i] for i in range(3)],
                        divisions=divisions,
                        units=units,
                    ),
                )
            elif head == "meshing" and len(words) >= 4 and words[2] == "create" and words[1] == "spheresolid":
                if pending:
                    raise ValueError("Previous operation was not accepted")
                v = [float(x) for x in words[3:]]
                if len(v) != 11 or v[5:] != [1, 0, 0, 0, 1, 0] or v[4] != int(v[4]):
                    raise ValueError("Unsupported sphere orientation")
                pending = dict(
                    kind="spheresolid",
                    action="create_solid_sphere",
                    arguments=dict(center=v[:3], radius=v[3], divisions=int(v[4]), units=units),
                )
            elif (
                head == "meshing"
                and len(words) >= 4
                and words[2] == "accept"
                and pending
                and pending["kind"] == words[1]
            ):
                args = pending["arguments"]
                args["part_id"] = int(words[3])
                if pending["kind"] == "boxsolid":
                    if len(words) < 6:
                        raise ValueError("Box accept needs explicit element/node IDs")
                    args.update(element_start=int(words[4]), node_start=int(words[5]))
                emit(pending["action"], args)
                pending = None
            elif head == "translate_model" and len(words) == 4:
                if target != "node" or selected == [] or pending:
                    raise ValueError(
                        "Translation needs a nonempty declared node selection and no pending operation"
                    )
                pending = dict(
                    kind="translate",
                    action="translate_gui_nodes",
                    arguments=dict(node_ids=selected, offset=[float(v) for v in words[1:]], units=units),
                )
            elif words == ["translate_model", "accept"] and pending and pending["kind"] == "translate":
                emit(pending["action"], pending["arguments"])
                pending = None
            else:
                unknown.append(dict(line=lineno, command=line, reason="No validated typed translation"))
        except (ValueError, IndexError, OverflowError) as exc:
            unknown.append(dict(line=lineno, command=line, reason=str(exc)))
    if pending:
        unknown.append(
            dict(line=None, command=str(pending), reason="Unaccepted operation at end of recording")
        )
    if len(steps) > 100:
        unknown.append(dict(line=None, command="", reason="Workflow exceeds 100-step execution limit"))
    return dict(
        schema_version=1,
        name="Imported cfile recording",
        defaults={},
        steps=steps,
        unrecognized_commands=unknown,
        requires_gui_session=True,
        recorded_model_index=recorded_model_index,
        output_policy="Original recorded output paths are not overwritten; save becomes a fresh checkpoint",
    )
