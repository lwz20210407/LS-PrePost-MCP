"""Translate a documented subset of recorded cfile commands into typed GUI steps.

Unknown commands remain explicit review blockers; this is not a shell/script
execution gateway. Original recording bytes stay in the source job.
"""

import shlex


def compile_commands(text, units):
    steps = []
    unknown = []
    nodes = []
    pending = None

    def emit(action, arguments):
        steps.append(dict(id="step" + str(len(steps) + 1), action=action, arguments=arguments))

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
            elif head in ("open", "openc") and len(words) == 3 and words[1] in ("keyword", "d3plot"):
                emit("open_model", dict(path=words[2], file_type=words[1]))
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
                nodes = []
            elif words == ["genselect", "target", "node"]:
                nodes = []
            elif (
                words[:4] == ["genselect", "node", "add", "node"]
                and len(words) == 5
                and words[4].endswith("/0")
            ):
                nodes.append(int(words[4][:-2]))
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
                pending = dict(
                    kind="translate",
                    action="translate_mesh_nodes",
                    arguments=dict(
                        node_ids=list(dict.fromkeys(nodes)), offset=[float(v) for v in words[1:]], units=units
                    ),
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
        output_policy="Original recorded output paths are not overwritten; save becomes a fresh checkpoint",
    )
