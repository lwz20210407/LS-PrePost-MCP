"""Native Model Checking metrics read back from the owned visible dialog."""

import math
import re
from pathlib import Path

from .config import command_path
from .gui_mesh import check_same_nodes, check_same_parts, mesh_index, shell_cycle
from .jobs import check_artifact
from .windows_transport import WindowsCommandTransport

# Recorded on Windows 4.13.4. Commands are semantic; controls are validated by caption.
SHELL_CHECKS = {
    "min_side_length": (10697, "Min side len", "minsize", "length"),
    "max_side_length": (10699, "Max side len", "maxsize", "length"),
    "aspect_ratio": (10701, "Aspect ratio", "aratio", "dimensionless"),
    "warpage": (10703, "Warpage", "warpage", "degrees"),
    "min_quad_angle": (10705, "Min quad ang", "minqangle", "degrees"),
    "max_quad_angle": (10707, "Max quad ang", "maxqangle", "degrees"),
    "min_triangle_angle": (10709, "Min tria ang", "mintangle", "degrees"),
    "max_triangle_angle": (10711, "Max tria ang", "maxtangle", "degrees"),
    "taper": (10713, "Taper", "taper", "dimensionless"),
    "skew": (10715, "Skew", "skew", "degrees"),
    "jacobian": (10717, "Jacobian", "jacobian", "dimensionless"),
    "characteristic_length": (10719, "Char. length", "charlength", "length"),
    "area": (10721, "Area", "area", "length_squared"),
}


def parse_keyword_report(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0].lower() != "*model check result" or lines[-1].lower() != "*endcheckinfo":
        raise ValueError("Native keyword report is missing its complete envelope")
    totals = {}
    categories = []
    details = []
    for line in lines[1:-1]:
        total = re.fullmatch(r"total (warning|error|unref|undefine)\s+(\d+)", line, re.I)
        if total:
            key = total[1].lower()
            if key in totals:
                raise ValueError("Duplicate native keyword summary")
            totals[key] = int(total[2])
            continue
        row = re.fullmatch(
            r"\*(\S+)\s+\((\d+)\)\s+Warning\((\d+)\)\s+Error\((\d+)\)\s+Unreferenced\((\d+)\)\s+Undefine\((\d+)\)",
            line,
            re.I,
        )
        if row:
            categories.append(
                dict(
                    keyword=row[1],
                    count=int(row[2]),
                    warning=int(row[3]),
                    error=int(row[4]),
                    unref=int(row[5]),
                    undefine=int(row[6]),
                )
            )
        else:
            details.append(line)
    if set(totals) != {"warning", "error", "unref", "undefine"}:
        raise ValueError("Native keyword report is missing summary counts")
    return dict(
        totals=totals,
        categories=categories,
        details=details,
        has_findings=any(totals.values()),
        passed_checks=not any(totals.values()),
        contacts_checked=False,
        solver_validated=False,
        scope="Native Keyword Check only. Unreferenced data is reported, not automatically deleted. This is not solver/physical validation.",
    )


def native_metric_row(rows, name, threshold):
    cid, label, command, units = SHELL_CHECKS[name]
    anchors = [
        r
        for r in rows
        if r["visible"] and r["control_id"] == cid and r["class_name"] == "Button" and r["text"] == label
    ]
    if len(anchors) != 1:
        raise ValueError("Native metric row identity missing or ambiguous: " + name)
    siblings = [r for r in rows if r["visible"] and r["parent"] == anchors[0]["parent"]]
    start = siblings.index(anchors[0])
    cells = []
    for row in siblings[start + 1 :]:
        if row["class_name"] == "Button":
            break
        if row["class_name"] == "Static":
            cells.append(row["text"])
    if len(cells) < 3:
        raise ValueError("Native metric result row is incomplete")
    low, high = float(cells[0]), float(cells[1])
    count = re.fullmatch(r"\s*(\d+)\s*\(\s*([\d.eE+-]+)\s*%\s*\)\s*", cells[2])
    if not math.isfinite(low) or not math.isfinite(high) or low > high or not count:
        raise ValueError("Native metric statistics are invalid")
    percentage = float(count[2])
    if not math.isfinite(percentage) or not 0 <= percentage <= 100:
        raise ValueError("Native violation percentage is invalid")
    return dict(
        metric=name,
        threshold=threshold,
        native_command=f"elemcheck shell {command} {threshold}",
        minimum=low,
        maximum=high,
        violated_count=int(count[1]),
        violated_percent=percentage,
        dimension=units,
        raw_display=cells[:3],
        precision="Native dialog display precision",
    )


class GuiQualityTools:
    def check_gui_keywords(self, session_id: str) -> dict:
        """Run actual native Keyword Check with contact checking excluded, export and parse its completed report, and verify mesh unchanged. Reports warnings/errors/unreferenced/undefined separately; never auto-clean."""
        context = {}

        def commands(state, directory):
            manager = self._session_manager()
            meta = manager.read(session_id)
            if not meta["process_alive"]:
                raise RuntimeError("Owned native process exited")
            transport = WindowsCommandTransport(meta["process"]["pid"])
            transport.open_menu_item(["Application", "Model Checking", "General Checking"])
            transport._select_panel_tab("Model Checking", 13339, 1)
            transport._set_panel_checked("Model Checking", 11377, True, "Do not Check Contact")
            context["path"] = directory / "native-keyword-check.txt"
            return ["modelcheck checkgeneral", "modelcheck writetofile " + command_path(context["path"])]

        def verify(before, after):
            nodes, elements = mesh_index(before)
            new_nodes, new_elements = mesh_index(after)
            check_same_nodes(nodes, new_nodes)
            check_same_parts(before, after)
            if elements != new_elements:
                raise ValueError("Native Keyword Check unexpectedly changed connectivity")
            artifact = check_artifact(context["path"], "text")
            report = parse_keyword_report(Path(context["path"]).read_text(encoding="utf8", errors="replace"))
            return dict(
                backend="lsprepost-native-keyword-check",
                geometry_unchanged=True,
                native_report=artifact,
                **report,
            )

        return self._gui_mesh_edit(session_id, "check_gui_keywords", {}, commands, verify)

    def inspect_gui_menu(
        self, session_id: str, path_prefix: list[str] | None = None, max_depth: int = 2
    ) -> dict:
        """Read actual native menu paths/IDs/enabled state in an owned GUI. Menu discovery is not implementation or certification of every listed function."""
        if type(max_depth) is not int or not 1 <= max_depth <= 8:
            raise ValueError("max_depth must be 1..8")
        prefix = [] if path_prefix is None else path_prefix
        if not isinstance(prefix, list) or any(not isinstance(p, str) or not p for p in prefix):
            raise ValueError("path_prefix must contain nonempty exact menu labels")
        manager = self._session_manager()
        with manager.lock(session_id):
            meta = manager.read(session_id)
            if not meta["process_alive"]:
                raise RuntimeError("Owned native process is not alive")
            rows = WindowsCommandTransport(meta["process"]["pid"]).inspect_menu()
        filtered = [
            r
            for r in rows
            if r["path"][: len(prefix)] == prefix and len(r["path"]) <= len(prefix) + max_depth
        ]
        return dict(
            status="succeeded",
            session_id=session_id,
            menu_entries=filtered,
            total_menu_entries=len(rows),
            scope="Navigation inventory only; no claim that listed actions are automated",
        )

    def check_gui_shell_quality(self, session_id: str, thresholds: dict[str, float], units: str) -> dict:
        """Run requested native shell Element Quality checks in the visible Model Checking panel. Read minimum/maximum/violation counts and verify mesh unchanged. Status succeeded means checks executed; inspect passed_checks, not solver validity. No clean/delete/repair is performed."""
        from .service import unit_label

        unit_label(units)
        if not isinstance(thresholds, dict) or not thresholds or not thresholds.keys() <= SHELL_CHECKS.keys():
            raise ValueError("Choose one or more supported native shell metrics: " + ", ".join(SHELL_CHECKS))
        limits = {}
        for name, value in thresholds.items():
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("Quality thresholds must be finite nonnegative numbers")
            if SHELL_CHECKS[name][3] == "degrees" and value > 180:
                raise ValueError("Angle thresholds must not exceed 180 degrees")
            limits[name] = float(value)
        reports = {}
        counts = {3: 0, 4: 0}

        def precheck(state):
            for e in state["elements"]:
                if e["type"] == "shell":
                    counts[len(shell_cycle(e["nodes"]))] += 1
            if not sum(counts.values()):
                raise ValueError("Model has no supported shells")

        def commands(state, directory):
            manager = self._session_manager()
            meta = manager.read(session_id)
            if not meta["process_alive"]:
                raise RuntimeError("Owned native process exited")
            transport = WindowsCommandTransport(meta["process"]["pid"])
            transport.open_menu_item(["Application", "Model Checking", "General Checking"])
            transport._select_panel_tab("Model Checking", 13339, 0)
            for name, limit in limits.items():
                count = (
                    counts[3] if "triangle" in name else counts[4] if "quad" in name else sum(counts.values())
                )
                if not count:
                    reports[name] = dict(status="not_applicable", reason="No matching shell topology")
                    continue
                result = manager.dispatch(
                    session_id,
                    "gui_mesh_state",
                    {},
                    native_commands=[
                        "elemcheck shell init",
                        f"elemcheck shell {SHELL_CHECKS[name][2]} {limit}",
                    ],
                )
                if result["status"] != "succeeded":
                    raise RuntimeError("Native quality request failed: " + name)
                report = native_metric_row(transport.inspect_controls(), name, limit)
                if report["violated_count"] > count:
                    raise ValueError("Native failed-element count exceeds applicable shell count")
                reports[name] = dict(
                    status="checked",
                    applicable_shell_count=count,
                    total_shell_count=sum(counts.values()),
                    percent_basis="Native displayed percent; not re-normalized to topology subset",
                    **report,
                )
            return []

        def verify(before, after):
            nodes, elements = mesh_index(before)
            new_nodes, new_elements = mesh_index(after)
            check_same_nodes(nodes, new_nodes)
            check_same_parts(before, after)
            if elements != new_elements:
                raise ValueError("Native quality check unexpectedly changed mesh connectivity")
            checked = [r for r in reports.values() if r["status"] == "checked"]
            return dict(
                backend="lsprepost-native-model-checking",
                units=units,
                metrics=reports,
                checked_count=len(checked),
                passed_checks=all(r["violated_count"] == 0 for r in checked) if checked else None,
                geometry_unchanged=True,
                solver_validated=False,
                scope="Requested shell Element Quality criteria only; not Keyword/Contact Check, union of failed IDs or all model checks",
            )

        return self._gui_mesh_edit(
            session_id,
            "check_gui_shell_quality",
            dict(thresholds=limits, units=units),
            commands,
            verify,
            precheck,
        )
