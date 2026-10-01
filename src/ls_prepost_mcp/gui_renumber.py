"""Visible native renumbering through validated dialog fields and native ID logs."""

from .gui_mesh import check_same_nodes, mesh_index
from .windows_transport import WindowsCommandTransport


def renumber_map(path, header, old_ids, new_ids):
    blocks, current = [], None
    for raw in path.read_text(encoding="utf8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("*"):
            current = dict(header=line.upper(), values={})
            blocks.append(current)
        elif line and not line.startswith("$") and current is not None:
            fields = line.split()
            if len(fields) == 2:
                old, new = map(int, fields)
                if old in current["values"] and current["values"][old] != new:
                    raise ValueError("Conflicting native renumber mapping")
                current["values"][old] = new
    candidates = [
        b["values"]
        for b in blocks
        if b["header"] == header
        and set(b["values"]) == set(old_ids)
        and set(b["values"].values()) == set(new_ids)
    ]
    if not candidates or any(c != candidates[0] for c in candidates[1:]):
        raise ValueError("Native renumber log does not identify a unique complete ID mapping")
    return candidates[0]


def verify_renumber(before, after, kind, start, log):
    old_nodes, old_elements = mesh_index(before)
    new_nodes, new_elements = mesh_index(after)
    old_ids = (
        list(old_nodes)
        if kind == "node"
        else [e["id"] for e in before["elements"] if e["type"] == "shell"]
        if kind == "shell"
        else before["part_ids"]
    )
    new_ids = (
        list(new_nodes)
        if kind == "node"
        else [e["id"] for e in after["elements"] if e["type"] == "shell"]
        if kind == "shell"
        else after["part_ids"]
    )
    if set(new_ids) != set(range(start, start + len(old_ids))):
        raise ValueError("Renumbered IDs do not match the requested range")
    mapping = renumber_map(
        log, {"node": "*NODE", "shell": "*ELEMENT_SHELL", "part": "*PART"}[kind], old_ids, new_ids
    )
    if kind == "node":
        check_same_nodes({mapping[k]: v for k, v in old_nodes.items()}, new_nodes)
        expected_elements = {
            key: tuple(mapping.get(n, n) for n in conn) for key, conn in old_elements.items()
        }
    else:
        check_same_nodes(old_nodes, new_nodes)
        expected_elements = {
            (typ, mapping[eid] if typ == "shell" and kind == "shell" else eid): conn
            for (typ, eid), conn in old_elements.items()
        }
    if expected_elements != new_elements:
        raise ValueError("Native renumber connectivity differs from its mapping")
    expected_part_ids = (
        {mapping[p] for p in before["part_ids"]} if kind == "part" else set(before["part_ids"])
    )
    if expected_part_ids != set(after["part_ids"]):
        raise ValueError("Native renumber changed unexpected part IDs")
    expected_parts = {
        str(mapping[int(pid)]) if kind == "part" else pid: sorted(
            mapping.get(eid, eid) if kind == "shell" else eid for eid in values
        )
        for pid, values in before["part_elements"].items()
    }
    if expected_parts != {pid: sorted(values) for pid, values in after["part_elements"].items()}:
        raise ValueError("Native renumber changed unexpected part membership")
    return dict(
        entity_type=kind,
        id_map={str(k): v for k, v in mapping.items()},
        count=len(mapping),
        coordinates_preserved=True,
        connectivity_verified=True,
        native_mapping_log=str(log),
    )


class GuiRenumberTools:
    def renumber_gui_entities(
        self, session_id: str, entity_type: str, start_id: int, check_references: bool = True
    ) -> dict:
        """Renumber all nodes, shells or parts through the visible Renumber dialog. Uses its native mapping log to verify coordinates/connectivity/part membership and optional scoped keyword references."""
        from .service import integer

        if entity_type not in ("node", "shell", "part"):
            raise ValueError("Visible renumber currently supports nodes, shells or parts")
        integer(start_id, "start_id")
        if type(check_references) is not bool:
            raise ValueError("check_references must be a boolean")
        if check_references:
            from .deck_backend import api

            api()
        context = {}

        def precheck(state):
            old_nodes, elements = mesh_index(state)
            count = (
                len(old_nodes)
                if entity_type == "node"
                else sum(k[0] == "shell" for k in elements)
                if entity_type == "shell"
                else len(state["part_ids"])
            )
            if count == 0 or start_id + count - 1 > 2_000_000_000:
                raise ValueError("No entities or renumber range exceeds supported IDs")
            if entity_type == "shell":
                if len({eid for _, eid in elements}) != len(elements):
                    raise ValueError("Shell renumber requires globally unique element IDs")
                retained = {eid for typ, eid in elements if typ != "shell"}
                if retained & set(range(start_id, start_id + count)):
                    raise ValueError("Requested shell IDs collide with retained elements")

        def preflight(path):
            if check_references:
                from .model_deck import validate_references

                before_refs = validate_references(path)
                if not before_refs["valid_within_scope"]:
                    raise ValueError(
                        "Input has invalid supported keyword references; inspect before renumbering"
                    )

        def commands(state, directory):
            manager = self._session_manager()
            meta = manager.read(session_id)
            if not meta["process_alive"]:
                raise RuntimeError("Owned process exited")
            transport = WindowsCommandTransport(meta["process"]["pid"])
            transport.open_panel("renumber")
            transport._click_panel_control("Renumber", 10001, "Renumber")
            transport._click_panel_control("Renumber", 10005, "Selected")
            control, caption = {"node": (10028, "Node"), "shell": (10029, "Shell"), "part": (10030, "Part")}[
                entity_type
            ]
            transport._click_panel_control("Renumber", control, caption)
            selected = manager.dispatch(
                session_id,
                "gui_mesh_state",
                {},
                native_commands=[
                    "pall",
                    "genselect clear",
                    "genselect target " + entity_type,
                    "genselect whole",
                ],
            )
            if selected["status"] != "succeeded":
                raise RuntimeError("Native renumber selection failed")
            expected = (
                {row[0] for row in state["nodes"]}
                if entity_type == "node"
                else {e["id"] for e in state["elements"] if e["type"] == "shell"}
                if entity_type == "shell"
                else set(state["part_ids"])
            )
            if set(selected["data"].get("selection_ids") or []) != expected:
                raise ValueError("Native renumber selection does not cover the requested entities")
            context["log"] = directory / "renumber-map.txt"
            transport._set_panel_checked("Renumber", 10006, True, "Save renumbering log file")
            transport._set_panel_text("Renumber", 10007, str(context["log"]))
            transport._set_panel_text("Renumber", 10031, str(start_id))
            transport._click_panel_control("Renumber", 10041, "Apply")
            return []

        def refs(before_path, after_path, verification):
            if not check_references:
                return dict(status="not_requested", all_keywords_certified=False)
            from .deck_backend import api
            from .model_deck import load_standalone, validate_references

            _, kw = api()
            mapping = {int(k): v for k, v in verification["id_map"].items()}
            before = load_standalone(before_path)
            after = load_standalone(after_path)
            expected = {
                int(c.sid): sorted(
                    mapping.get(int(n), int(n)) if entity_type == "node" else int(n)
                    for n in c.nodes
                    if int(n) != 0
                )
                for c in before.keywords
                if isinstance(c, kw.SetNodeList)
            }
            actual = {
                int(c.sid): sorted(int(n) for n in c.nodes if int(n) != 0)
                for c in after.keywords
                if isinstance(c, kw.SetNodeList)
            }
            if expected != actual:
                raise ValueError("Native renumber did not preserve node-set membership")
            checked = validate_references(after_path)
            if not checked["valid_within_scope"]:
                raise ValueError("Renumbered model has invalid supported references")
            return dict(
                node_sets_verified=len(expected), structural_check=checked, all_keywords_certified=False
            )

        return self._gui_mesh_edit(
            session_id,
            "renumber_gui_entities",
            dict(entity_type=entity_type, start_id=start_id, check_references=check_references),
            commands,
            lambda a, b: verify_renumber(a, b, entity_type, start_id, context["log"]),
            precheck,
            refs,
            preflight,
        )
