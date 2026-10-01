"""Native solid Element Quality criteria, with explicit zero-failure UI evidence."""

import math
import re

from .gui_mesh import check_same_nodes, check_same_parts, mesh_index
from .gui_selection import part_visibility
from .jobs import check_artifact
from .programs import native_errors
from .windows_transport import WindowsCommandTransport

# Observed from 4.13.4 Model Checking / Solid / Check command recordings.
SOLID_CHECKS = {
    "minimum_angle": ("minangle", "degrees"),
    "maximum_angle": ("maxangle", "degrees"),
    "distortion_index": ("distortion", "dimensionless"),
    "volume": ("volume", "length_cubed"),
    "characteristic_length": ("solidcharlen", "length"),
    "aspect_ratio": ("aratio", "dimensionless"),
}


def parse_solid_check(text, command, comparison, total, save_failed_enabled):
    if type(total) is not int or total <= 0 or type(save_failed_enabled) is not bool:
        raise ValueError("Native solid count and explicit Save Failed state are required")
    if command not in [line.strip() for line in text.splitlines()] or native_errors(text):
        raise ValueError("Native solid check command echo missing or diagnostics reported an error")
    counts = re.findall(r"^Number of elements (larger|less) than criteria:\s*(\d+)\s*$", text, re.M)
    percents = re.findall(
        r"^Failed elements accounted for ([\d.]+)% of the total solid elements\s*$", text, re.M
    )
    if not counts and not percents:
        if save_failed_enabled:
            raise ValueError("Native failed capture exists but its count was not reported")
        return dict(
            violated_count=0,
            violated_percent=0.0,
            zero_evidence="Completed valid command and disabled native Save Failed control",
        )
    if len(counts) != 1 or len(percents) != 1:
        raise ValueError("Native solid check summary is missing or ambiguous")
    direction, count = counts[0][0], int(counts[0][1])
    percentage = float(percents[0])
    if direction != {"gt": "larger", "lt": "less"}[comparison] or not 0 <= count <= total:
        raise ValueError("Native solid comparison/count does not match requested scope")
    if not math.isfinite(percentage) or not math.isclose(percentage, count * 100 / total, abs_tol=0.011):
        raise ValueError("Native solid percentage does not match the full solid registry")
    if save_failed_enabled != (count > 0):
        raise ValueError("Native failed-element capture disagrees with reported count")
    return dict(violated_count=count, violated_percent=percentage, zero_evidence=None)


def check_solids(service, session_id, checks, units):
    from .service import unit_label

    unit_label(units)
    if not isinstance(checks, list) or not 1 <= len(checks) <= 12:
        raise ValueError("Provide 1..12 explicit solid quality criteria")
    normalized, seen = [], set()
    for item in checks:
        if not isinstance(item, dict) or set(item) != {"metric", "comparison", "threshold"}:
            raise ValueError("Each check requires metric, comparison and threshold")
        name, comparison, value = item["metric"], item["comparison"], item["threshold"]
        if not isinstance(name, str) or name not in SOLID_CHECKS or comparison not in ("gt", "lt"):
            raise ValueError("Use native gt/lt and a solid metric from: " + ", ".join(SOLID_CHECKS))
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Solid quality threshold must be finite and numeric")
        if SOLID_CHECKS[name][1] == "degrees" and not 0 <= value <= 180:
            raise ValueError("Solid angle threshold must be in 0..180 degrees")
        if (name, comparison) in seen:
            raise ValueError("Duplicate metric/comparison")
        seen.add((name, comparison))
        normalized.append(dict(metric=name, comparison=comparison, threshold=float(value)))
    reports, count = [], []

    def precheck(state):
        solids = [e for e in state["elements"] if e["type"] == "solid"]
        if not solids or any(
            len(e["nodes"]) != 8 or len(set(e["nodes"])) != 8 or 0 in e["nodes"] for e in solids
        ):
            raise ValueError("Native solid quality currently requires a nonempty Hex8-only solid registry")
        part_visibility(state)
        count.append(len(solids))

    def commands(state, directory):
        manager = service._session_manager()
        transport = WindowsCommandTransport(manager.read(session_id)["process"]["pid"])
        transport.open_menu_item(["Application", "Model Checking", "General Checking"])
        transport._select_panel_tab("Model Checking", 13339, 0)
        transport._click_panel_control("Model Checking", 10145, "Solid")
        log = manager.directory(session_id) / "lspost.msg"
        for index, item in enumerate(normalized):
            token, dimension = SOLID_CHECKS[item["metric"]]
            command = "elemcheck solid %s %s %s" % (token, item["comparison"], item["threshold"])
            offset = log.stat().st_size if log.exists() else 0
            result = manager.dispatch(session_id, "inspect_model", {}, native_commands=["pall", command])
            if result["status"] != "succeeded":
                raise RuntimeError("Native solid quality request failed")
            if any(result["data"]["counts"].get(k) != state["counts"].get(k) for k in ("nodes", "elements")):
                raise ValueError("Model counts changed during solid checking")
            with log.open("rb") as stream:
                stream.seek(offset)
                text = stream.read().decode("utf8", errors="replace")
            controls = [
                r
                for r in transport.inspect_controls()
                if r["visible"]
                and r["class_name"] == "Button"
                and r["control_id"] == 10336
                and r["text"] == "Save Failed"
            ]
            if len(controls) != 1:
                raise ValueError("Native Save Failed control missing or ambiguous")
            report = parse_solid_check(text, command, item["comparison"], count[0], controls[0]["enabled"])
            path = directory / ("solid-check-%02d.txt" % index)
            path.write_text(text, encoding="utf8")
            reports.append(
                dict(
                    **item,
                    **report,
                    dimension=dimension,
                    native_command=command,
                    native_report=check_artifact(path, "text"),
                )
            )
        return ["-m " + pid for pid, active in part_visibility(state).items() if not active]

    def verify(before, after):
        old, old_elements = mesh_index(before)
        new, new_elements = mesh_index(after)
        check_same_nodes(old, new)
        check_same_parts(before, after)
        if old_elements != new_elements or part_visibility(before) != part_visibility(after):
            raise ValueError("Solid checking changed topology or failed to restore part visibility")
        return dict(
            backend="lsprepost-native-model-checking",
            entity_type="solid",
            units=units,
            total_solid_count=count[0],
            criteria=reports,
            checked_count=len(reports),
            passed_checks=all(r["violated_count"] == 0 for r in reports),
            geometry_unchanged=True,
            part_visibility_preserved=True,
            solver_validated=False,
            scope="Requested native Hex8 criteria over all parts; counts are per criterion, not a union of failed IDs. Display/captured-check state may change.",
        )

    return service._gui_mesh_edit(
        session_id,
        "check_gui_solid_quality",
        dict(checks=normalized, units=units),
        commands,
        verify,
        precheck,
        transaction_kind="inspection",
    )
