"""Native solid Element Quality criteria, with explicit zero-failure UI evidence."""

import math
import re

from .field_contracts import EntitySelection
from .gui_mesh import check_same_nodes, check_same_parts, mesh_index
from .gui_selection import available_ids, part_visibility
from .jobs import atomic_json, check_artifact
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


def verified_failed_ids(values, count, registry):
    if type(count) is not int or count < 0:
        raise ValueError("Native failed count must be a nonnegative integer")
    selection = EntitySelection("solid", values)
    if len(selection.entity_ids) != count or not set(selection.entity_ids) <= registry:
        raise ValueError("Native failed user IDs do not match the reported count/current solid registry")
    return sorted(selection.entity_ids)


def check_solids(service, session_id, checks, units, capture_failed_ids=False):
    from .service import unit_label

    unit_label(units)
    if type(capture_failed_ids) is not bool:
        raise ValueError("capture_failed_ids requires a boolean")
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
    solid_ids, failed_union = set(), set()
    buffer_backup = {}

    def precheck(state):
        solids = [e for e in state["elements"] if e["type"] == "solid"]
        if not solids or any(
            len(e["nodes"]) != 8 or len(set(e["nodes"])) != 8 or 0 in e["nodes"] for e in solids
        ):
            raise ValueError("Native solid quality currently requires a nonempty Hex8-only solid registry")
        part_visibility(state)
        count.append(len(solids))
        if capture_failed_ids:
            solid_ids.update(available_ids(state, "solid"))

    def commands(state, directory):
        manager = service._session_manager()
        transport = WindowsCommandTransport(manager.read(session_id)["process"]["pid"])
        transport.open_menu_item(["Application", "Model Checking", "General Checking"])
        transport._select_panel_tab("Model Checking", 13339, 0)
        transport._click_panel_control("Model Checking", 10145, "Solid")
        if capture_failed_ids:
            # The native Save Failed operation uses Buffer1. Invalidate its
            # managed identity before dispatch, including uncertain outcomes.
            meta = manager.read(session_id)
            previous = meta.setdefault("selection_buffers", {}).pop("1", None)
            if previous is not None:
                backup = directory / "buffer1-before-capture.json"
                atomic_json(
                    backup,
                    dict(
                        session_id=session_id,
                        slot=1,
                        previous_managed_metadata=previous,
                        scope="Managed identity only; not a snapshot of unknown/manual native buffer contents",
                    ),
                )
                buffer_backup.update(check_artifact(backup, "json"))
            manager.save(session_id, meta)
            cleared = manager.dispatch(
                session_id,
                "inspect_model",
                {},
                native_commands=[
                    "genselect clear",
                    "genselect target element",
                    "genselect save 0",
                ],
            )
            if cleared["status"] != "succeeded":
                raise RuntimeError("Cannot initialize the explicitly requested failed-ID capture buffer")
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
            if capture_failed_ids:
                values = []
                if report["violated_count"]:
                    captured = manager.dispatch(
                        session_id,
                        "gui_mesh_state",
                        {},
                        native_commands=[
                            "genselect clear",
                            "genselect target element",
                            "genselect save 0",
                            "elemcheck savetogen",
                            "genselect load 0",
                        ],
                    )
                    if captured["status"] != "succeeded":
                        raise RuntimeError("Native failed-ID capture did not complete")
                    values = verified_failed_ids(
                        captured["data"].get("selection_ids"), report["violated_count"], solid_ids
                    )
                failed_union.update(values)
                ids_path = directory / ("solid-failed-%02d.json" % index)
                atomic_json(ids_path, dict(entity_type="solid", entity_ids=values, criterion=item))
                report.update(
                    failed_element_id_sample=values[:20], failed_ids_artifact=check_artifact(ids_path, "json")
                )
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
        return (["genselect clear"] if capture_failed_ids else []) + [
            "-m " + pid for pid, active in part_visibility(state).items() if not active
        ]

    def verify(before, after):
        old, old_elements = mesh_index(before)
        new, new_elements = mesh_index(after)
        check_same_nodes(old, new)
        check_same_parts(before, after)
        if old_elements != new_elements or part_visibility(before) != part_visibility(after):
            raise ValueError("Solid checking changed topology or failed to restore part visibility")
        if capture_failed_ids and after.get("selection_ids") != []:
            raise ValueError("Failed-ID capture did not clear the general selection")
        result = dict(
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
            capture_failed_ids=capture_failed_ids,
            native_buffer1_overwritten=capture_failed_ids,
            prior_managed_buffer1=buffer_backup or None,
            general_selection_cleared=capture_failed_ids,
            scope="Requested native Hex8 criteria over all parts. Per-criterion counts remain separate; optional captured user-ID union is verified. Display/captured-check state may change.",
        )
        if capture_failed_ids:
            result.update(
                failed_element_ids=sorted(failed_union),
                unique_failed_element_count=len(failed_union),
                failed_part_ids=sorted(
                    int(pid)
                    for pid, members in before["part_elements"].items()
                    if failed_union.intersection(members)
                ),
            )
        return result

    return service._gui_mesh_edit(
        session_id,
        "check_gui_solid_quality",
        dict(checks=normalized, units=units, capture_failed_ids=capture_failed_ids),
        commands,
        verify,
        precheck,
        transaction_kind="inspection",
    )
