"""Q01 result_info: one inventory of a d3plot result folder, returned as JobResult/v1.

The numbers come from the shared LASSO overview (``domain.results.lasso_backend.overview`` with
the MPP binout catalogue of ``domain.results.mpp_shards``). The d3plot header words NEIPH / NEIPS /
NEIPB are reported beside the readable history-variable counts, because LASSO moves stored strain
tensors out of the history arrays and reports a family without such an array as 0.
With ``native_check`` the same file family is opened by LS-PrePost (the existing embedded-Python
``inspect_model``) and its state count and state times are compared with LASSO's.
"""
from __future__ import annotations

import math

from .core.contracts import CheckResult, JobResult
from .jobs import atomic_json

TIME_RELATIVE_TOLERANCE = 1e-6


def result_info(tools, path: str, native_check: bool) -> dict:
    from .domain.results import lasso_backend as lb

    if type(native_check) is not bool:
        raise ValueError("native_check must be true or false")
    source = tools.settings.input_path(path)
    directory, manifest = tools.jobs.create("result_info", {"path": str(source), "native_check": native_check})
    try:
        overview = lb.overview(source)
        header = _header(source)
    except Exception as error:  # reader failures of any kind are reported, not raised past the job record
        result = _result("failed", {"source": str(source)}, manifest["job_id"], error=_error(error))
        return _record(directory, manifest, result)
    warnings: list[str] = []
    data = {"source": str(source), "lasso_backend": overview["backend"], "state_index_base": 1,
            "states": overview["states"], "time_range": overview["time_range"], "times": overview["times"],
            "time_units": "as stored in the d3plot (model time unit; nothing converted)",
            "variables": overview["variables"], "elements": _elements(overview, header, lb.FAMILIES, warnings),
            "header": header, "parts": overview["parts"],
            "binout": {"files": overview["binout_files"], "databases": overview["binout_databases"],
                       "entries": overview["binout_entries"], "split_over_shards": overview["binout_split"]},
            "ascii_files": overview["ascii_files"]}
    if overview["times"] is None:
        warnings.append(f"The shared overview lists state times only up to 2000 states; this result has "
                        f"{overview['states']}, so only time_range is reported")
    checks = [CheckResult(name="lasso_overview", status="passed")]
    error = None
    if native_check:
        native, error = _native(tools, path)
        data["lsprepost"] = native
        checks.append(_agreement(overview, native, data))
    else:
        checks.append(CheckResult(name="backends_agree", status="not_applicable"))
    status = "partial" if error or overview["times"] is None else "succeeded"
    result = _result(status, data, manifest["job_id"], checks=checks, warnings=tuple(warnings), error=error,
                     backend="lasso+lsprepost" if native_check else "lasso")
    return _record(directory, manifest, result)


def _header(source) -> dict:
    from lasso.dyna.d3plot_header import D3plotHeader

    h = D3plotHeader().load_file(str(source))
    return {"neiph_solid": int(h.n_solid_history_vars), "neips_shell_tshell": int(h.n_shell_tshell_history_vars),
            "neipb_beam": int(h.n_beam_history_vars), "strain_tensor_stored": bool(h.has_element_strain),
            "plastic_strain_tensor_stored": bool(h.has_solid_shell_plastic_strain_tensor),
            "thermal_strain_tensor_stored": bool(h.has_solid_shell_thermal_strain_tensor),
            "deletion_data_stored": bool(h.has_element_deletion_data),
            "meaning": "header words: extra values per integration point, including stored strain tensors"}


def _elements(overview: dict, header: dict, families: dict, warnings: list[str]) -> dict:
    words = {"solid": header["neiph_solid"], "shell": header["neips_shell_tshell"],
             "tshell": header["neips_shell_tshell"], "beam": header["neipb_beam"]}
    out = {}
    for family, entry in overview["elements"].items():
        declared = words[family]
        readable = families[family][3] in overview["variables"]
        explained = 6 * (header["strain_tensor_stored"] + header["plastic_strain_tensor_stored"])
        if declared and not readable and not (family == "solid" and declared <= explained):
            warnings.append(f"{family}: the header declares {declared} extra values per point but LASSO exposes "
                            "no history-variable array; history_variables=0 is not a measured HSV count")
        deleted = entry.get("deleted_at_last_state")
        if deleted is None:
            warnings.append(f"{family}: the d3plot stores no element deletion data; deleted count is null, not 0")
        out[family] = {"count": entry["count"], "history_variables": entry["history_variables"],
                       "history_variables_source": "readable LASSO array (strain tensors excluded)",
                       "header_extra_values_per_point": declared, "deleted_at_last_state": deleted,
                       "deletion_meaning": "elements flagged deleted (zero MDLOPT code) at the last state"}
    return out


def _native(tools, path: str) -> tuple[dict, dict | None]:
    try:
        job = tools.inspect_model(path, "d3plot")
    except Exception as error:  # configuration / staging refusals happen before a native job exists
        return {"status": "failed", "job_id": None}, _error(error)
    reply = job.get("data") or {}
    native = {"status": job.get("status"), "job_id": job.get("job_id"),
              "states": (reply.get("counts") or {}).get("states"), "times": reply.get("state_times"),
              "executable": job.get("executable")}
    if job.get("status") != "succeeded":
        return native, {"message": "LS-PrePost inspect_model did not succeed: "
                        + str((job.get("error") or {}).get("message") or job.get("status")), "native": job.get("error")}
    if native["states"] is None or native["times"] is None:
        return native, {"message": "LS-PrePost reported no state count or state times"}
    return native, None


def _agreement(overview: dict, native: dict, data: dict) -> CheckResult:
    if native.get("states") is None or native.get("times") is None or overview["times"] is None:
        return CheckResult(name="backends_agree", status="missing")
    lasso_times, native_times = overview["times"], [float(t) for t in native["times"]]
    same_count = overview["states"] == native["states"] == len(native_times)
    tolerance = TIME_RELATIVE_TOLERANCE * max([abs(t) for t in lasso_times] or [0.0])
    difference = (max((abs(a - b) for a, b in zip(lasso_times, native_times)), default=0.0)
                  if len(lasso_times) == len(native_times) else None)
    same_times = difference is not None and math.isfinite(difference) and difference <= tolerance
    data["comparison"] = {"lasso_states": overview["states"], "lsprepost_states": native["states"],
                          "state_counts_equal": same_count, "max_abs_time_difference": difference,
                          "time_tolerance": tolerance, "time_tolerance_rule": "1e-6 x largest |state time|",
                          "times_equal": same_times}
    return CheckResult(name="backends_agree", status="passed" if same_count and same_times else "failed")


def _result(status: str, data: dict, job_id: str, backend: str = "lasso", **fields) -> dict:
    return JobResult(operation="result_info", status=status, backend=backend, job_id=job_id, data=data,
                     scope="d3plot family with binout/ASCII files in the same folder; inputs unchanged",
                     **fields).model_dump(mode="json")


def _record(directory, manifest: dict, result: dict) -> dict:
    atomic_json(directory / "job.json", {**manifest, "status": result["status"], "result": result})
    return result


def _error(error: Exception) -> dict:
    return {"type": type(error).__name__, "message": str(error) or type(error).__name__}


__all__ = ["TIME_RELATIVE_TOLERANCE", "result_info"]
