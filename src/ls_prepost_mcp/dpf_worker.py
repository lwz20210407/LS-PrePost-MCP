"""Owned isolated local DPF worker. No remote server, solver or license-term changes."""

import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .dpf_fields import RESULTS, field_spec, flatten_fields, result_contract, time_axis
from .native.versions import dependency_supported


def runtime_info(server_path=None):
    report = dict(backend="dpf", client_version=None, server_path=None,
                  ready_for_runtime_attempt=False, server_started=False,
                  protocol="local in-process", license_context="entry")
    try:
        report["client_version"] = version("ansys-dpf-core")
    except PackageNotFoundError:
        report["reason"] = "Install the dpf optional dependency (ansys-dpf-core0.16.1)"
        return report
    if not dependency_supported("ansys-dpf-core", report["client_version"]):
        report["reason"] = "This adapter is aligned with ansys-dpf-core0.16.1"
        return report
    try:
        from ansys.dpf.core.misc import get_ansys_path

        path = Path(get_ansys_path(server_path)).resolve(strict=True)
        if not path.is_dir():
            raise ValueError("DPF installation root is not a directory")
        report.update(server_path=str(path), ready_for_runtime_attempt=True,
                      reason="Installation root found; server version/plugins/license still require runtime validation")
    except Exception as exc:
        report["reason"] = str(exc)
    return report


def execute(request):
    runtime = runtime_info(request.get("server_path"))
    if request["action"] == "probe":
        return runtime, None
    if not runtime["ready_for_runtime_attempt"]:
        raise ValueError(runtime["reason"])
    if sys.platform not in ("win32", "linux"):
        raise ValueError("This adapter requires a local Windows/Linux in-process DPF runtime")
    from ansys.dpf import core as dpf

    server = dpf.start_local_server(
        ansys_path=runtime["server_path"], as_global=False,
        config=dpf.AvailableServerConfigs.InProcessServer,
        context=dpf.AvailableServerContexts.entry,
        use_docker_by_default=False, use_pypim_by_default=False,
        timeout=min(request["timeout"], 30),
    )
    try:
        if not server.meet_version("7.1"):
            raise ValueError("This client requires a compatible DPF Server7.1 or later; see DPF_INTEGRATION.md")
        runtime.update(server_started=True, server_version=str(server.version))
        sources = dpf.DataSources(server=server)
        sources.set_result_file_path(request["path"], key=request["file_type"])
        if request.get("actunits"):
            sources.add_file_path(request["actunits"], key="actunits")
        model = dpf.Model(sources, server=server)
        available = model.metadata.result_info.available_results
        if request["action"] == "inspect":
            times, units = time_axis(model.metadata.time_freq_support)
            return dict(**runtime, available_results=[dict(name=str(r.name), operator=str(r.operator_name),
                        location=str(r.native_location), components=int(r.n_components), dpf_unit=str(r.unit or ""),
                        adapter_export_supported=r.name in RESULTS[request["file_type"]])
                        for r in available],
                        sets=[dict(id=k, time=v) for k, v in times.items()], time_unit=units,
                        scope="Model time support; binout branch-specific time scoping is resolved during export"), None
        contract = result_contract(request["file_type"], request["result"])
        if not server.meet_version(contract["minimum_server"]):
            raise ValueError("Requested result requires DPF Server" + contract["minimum_server"])
        if request["result"] not in {r.name for r in available}:
            raise ValueError("Requested result is not available in this source")
        arguments = {}
        if contract["location"] != "TimeFreq_steps":
            arguments["time_scoping"] = request["states"]
            if request.get("entity_ids") is not None:
                arguments["mesh_scoping"] = dpf.Scoping(ids=request["entity_ids"],
                                                       location=contract["location"], server=server)
        operator = getattr(model.results, request["result"])(**arguments)
        container = operator.eval()
        rows, report = flatten_fields(container, request["file_type"], request["result"],
                                      request.get("states"), request.get("entity_ids"), request.get("label_filter"),
                                      request.get("component"))
        report.update(runtime=runtime, declared_units=request["units"],
                      labels_filtered=request.get("label_filter"),
                      component_selected=request.get("component"),
                      dimensional_validation=False, ls_prepost_native=False)
        report["field_spec"] = field_spec(rows, report, request["units"])
        return report, rows
    finally:
        server.shutdown()


def main():
    source, output = map(Path, sys.argv[1:3])
    request = json.loads(source.read_text(encoding="utf-8"))
    try:
        data, rows = execute(request)
        response = dict(ok=True, data=data, rows=rows)
    except Exception as exc:
        response = dict(ok=False, error=dict(type=type(exc).__name__, message=str(exc)))
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(response, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(output)


if __name__ == "__main__":
    main()
