"""M3 pre-processing target tools on the raw-preserving keyword engine (I07), returning JobResult/v1.

model_info (P01), edit_keywords (P02/P03/P10), create_entities (P04-P06), mesh_ops (P08) and
check_model (P09) are thin wrappers over ``domain.model.operations``. Material / EOS / section /
hourglass / control cards are edit_keywords ops; run_recipe is the A08 recipe tool, not defined here.
No LS-PrePost is needed: edits are applied to the deck text, untouched bytes and the Include
structure are kept, and the result deck is written to the job directory, never over the input.
Selections may be ``core.contracts.Selector`` objects (``"selector"`` in an edit or target).
"""
from __future__ import annotations

import math
from pathlib import Path

from .core.contracts import Artifact, CheckResult, JobResult
from .jobs import atomic_json

BACKEND = "keyword-engine"
CREATE_OPS = frozenset({"create_set", "add_boundary", "add_contact", "add_joint", "add_part", "set_part"})


def _jsonable(value: object) -> object:
    """Plain JSON values (numpy scalars and arrays, paths, non-finite floats as text)."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _result(operation: str, status: str, data: dict, **fields: object) -> dict:
    return JobResult(operation=operation, status=status, backend=BACKEND, data=_jsonable(data), **fields).model_dump(
        mode="json")


class ModelTargetTools:
    """Mixed into Service: needs ``self.settings`` (input paths) and ``self.jobs`` (job directories)."""

    def model_info(self, model: str) -> dict:
        """P01: inventory of a keyword deck with its Include tree (parts, materials, sections, sets,
        element counts, keyword counts, unread blocks). Read-only; no LS-PrePost."""
        from .domain.model.operations import inspect_deck

        source = self.settings.input_path(model)
        try:
            data = inspect_deck(str(source))
        except (ValueError, KeyError, TypeError, OSError) as error:
            return _result("model_info", "failed", {"model": str(source)}, error=_error(error))
        return _result("model_info", "succeeded", data, scope="keyword deck and its includes")

    def check_model(self, model: str, thresholds: dict | None = None, coincident_tolerance: float | None = None,
                    include_mesh: bool = True) -> dict:
        """P09: includes, parameters, dangling/duplicate references, element quality against the given
        thresholds, coordinate round-off, free-format field widths and short prescribed-motion curves.
        Execution succeeds when the check ran; findings are reported as checks, not as a failure."""
        from .domain.model.operations import check_deck

        source = self.settings.input_path(model)
        try:
            report = check_deck(str(source), thresholds=thresholds, coincident_tol=coincident_tolerance,
                                include_mesh=include_mesh)
        except (ValueError, KeyError, TypeError, OSError) as error:
            return _result("check_model", "failed", {"model": str(source)}, error=_error(error))
        kinds = sorted({e["kind"] for e in report["errors"]})
        checks = [CheckResult(name="objective_defects", status="failed" if report["errors"] else "passed"),
                  CheckResult(name="all_blocks_read", status="passed" if report["complete"] else "missing")]
        checks += [CheckResult(name=f"defect:{kind}", status="failed") for kind in kinds]
        return _result("check_model", "succeeded", report, checks=checks, warnings=tuple(report["warnings"][:50]),
                       scope="keyword deck and its includes")

    def edit_keywords(self, model: str, edits: list[dict], allow_new_dangling: bool = False) -> dict:
        """P02/P03/P10: apply edits atomically and write the edited deck (Include structure kept) to the
        job directory. Ops: set, set_parameter, set_members, set_points, insert (card or text),
        delete, create_set, every create_entities / mesh_ops op, and card recipes: add_material,
        add_eos, add_section, add_hourglass (units required, no defaults filled in) and set_control
        (termination, timestep, d3plot, ascii, ...). Nothing is written when any edit fails or
        creates dangling references (unless allowed)."""
        return self._edit("edit_keywords", model, edits, None, allow_new_dangling)

    def create_entities(self, model: str, entities: list[dict]) -> dict:
        """P04-P06, P12: sets (ids / select / selector), boundary conditions and loads (add_boundary with a
        declared unit system), contacts (add_contact recipes), parts (add_part / set_part) and joints.

        Joint: {"op": "add_joint", "kind": "revolute", "a": {"part": 1}, "b": {"part": 2},
        "origin": [0, 0, 0], "axis": [0, 1, 0]}. kind: spherical, revolute, cylindrical, planar,
        universal (second_axis), translational, locking, rotational_motor / translational_motor
        (motor = {"curve": {"points": [[t, v], ...]} or {"lcid": n}, "type": "velocity"}). A side is a
        rigid part {"part": pid}, an existing {"nodal_rigid_body": pid} or nodes of a deformable part
        ({"nodes": [...]}, {"select": {...}}, {"selector": {...}}), held by a new nodal rigid body.
        Optional: length, reference / third_point, jid, title, rps, damp, failure, local."""
        return self._edit("create_entities", model, entities, CREATE_OPS, False)

    def mesh_ops(self, model: str, operations: list[dict]) -> dict:
        """P08: transform / copy / array / offset / renumber / merge duplicate nodes / delete /
        reverse / unify normals / clean or quantize coordinates, on the deck text."""
        from .domain.model.operations import MESH_OPS

        return self._edit("mesh_ops", model, operations, MESH_OPS, False)

    def _edit(self, operation: str, model: str, edits: list[dict], allowed: frozenset | None,
              allow_new_dangling: bool) -> dict:
        from .domain.model.operations import edit_deck

        if not isinstance(edits, list) or not edits or not all(isinstance(e, dict) and "op" in e for e in edits):
            raise ValueError("Give a non-empty list of edits, each with an 'op'")
        if allowed is not None:
            other = sorted({e["op"] for e in edits} - allowed)
            if other:
                raise ValueError(f"{operation} does not run {other}; allowed: {sorted(allowed)}")
        source = self.settings.input_path(model)
        directory, manifest = self.jobs.create(operation, {"model": str(source), "edits": _jsonable(edits)})
        try:
            outcome = edit_deck(str(source), edits, output_dir=str(directory / "deck"),
                                allow_new_dangling=allow_new_dangling)
        except (ValueError, KeyError, TypeError, OSError) as error:
            outcome = {"status": "failed", "error": f"{type(error).__name__}: {error}", "written": False}
        data = {k: outcome.get(k) for k in ("changes", "summaries", "diff", "diff_truncated", "new_dangling",
                                            "modified_files", "failed_edit", "applied_before_failure")
                if k in outcome}
        if outcome["status"] != "succeeded" or not outcome.get("written"):
            result = _result(operation, "failed", data, job_id=manifest["job_id"],
                             error={"message": str(outcome.get("error") or "nothing written"),
                                    "failed_edit": outcome.get("failed_edit")})
        else:
            save = outcome["save"]
            artifacts = []
            for item in save["files"]:
                path = Path(item["dest"])
                artifacts.append(Artifact(path=str(path), kind="keyword", sha256=item["sha256"],
                                          size_bytes=path.stat().st_size, verification="verified",
                                          metadata={"source": item["source"], "modified": item["modified"]}))
            checks = [CheckResult(name="edits_applied", status="passed"),
                      CheckResult(name="no_new_dangling_references",
                                  status="failed" if outcome["new_dangling"] else "passed"),
                      CheckResult(name="saved_deck_reloads",
                                  status="failed" if save["reload_warnings"] else "passed")]
            data["main"] = save["main"]
            result = _result(operation, "succeeded", data, job_id=manifest["job_id"], artifacts=tuple(artifacts),
                             checks=checks, warnings=tuple(str(w) for w in outcome.get("warnings", [])[:50]),
                             scope="input deck unchanged; edited copy in the job directory")
        atomic_json(directory / "job.json", {**manifest, "status": result["status"], "result": result})
        return result


def _error(error: Exception) -> dict:
    return {"type": type(error).__name__, "message": str(error) or type(error).__name__}


__all__ = ["CREATE_OPS", "ModelTargetTools"]
