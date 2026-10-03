"""Optional typed DPF adapter with isolated local runtime and explicit semantics."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import StrictInt

from .dpf_fields import result_contract, write_labelled_csv
from .jobs import atomic_json, check_artifact
from .post_backend import ids


def source_family(settings, path, file_type):
    if file_type not in ("d3plot", "binout"):
        raise ValueError("DPF file_type must be d3plot or binout")
    source = settings.input_path(path)
    family = [source]
    if file_type == "d3plot":
        if re.fullmatch(r"d3plot\d+", source.name, flags=re.I):
            raise ValueError("Provide the base d3plot, not a numbered continuation")
        chunks = [(int(p.name[len(source.name):]), p) for p in source.parent.iterdir()
                  if p.is_file() and p.name.startswith(source.name) and p.name[len(source.name):].isdigit()]
        numbers = sorted(number for number, _ in chunks)
        if numbers and numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("Missing or ambiguous interior d3plot continuation; complete the family")
        family += [p for _, p in sorted(chunks)]
    else:
        prefix = re.sub(r"[.\d]+$", "", source.name)
        shards = [p for p in source.parent.iterdir() if p.is_file() and
                  re.fullmatch(re.escape(prefix) + r"(?:\d+)?(?:\.\d+)?", p.name)]
        if len(shards) > 1:
            raise ValueError("DPF MPP binout shard groups are not certified by this adapter")
    return [settings.input_path(str(p)) for p in family]


def run_worker(directory, request, timeout):
    atomic_json(directory / "request.json", request)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + environment.get("PYTHONPATH", "")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with (directory / "worker.log").open("wb") as log:
        subprocess.run([sys.executable, "-B", "-m", "ls_prepost_mcp.dpf_worker",
                        str(directory / "request.json"), str(directory / "response.json")],
                       cwd=directory, env=environment, stdout=log, stderr=subprocess.STDOUT,
                       timeout=timeout, check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    reply = json.loads((directory / "response.json").read_text(encoding="utf-8"))
    if not reply["ok"]:
        raise ValueError(reply["error"]["message"])
    return reply


class DpfTools:
    def probe_dpf_runtime(self) -> dict:
        """Discover optional client/server root without starting DPF, solver, remote connection or license checkout. A found root is not runtime certification."""
        def work(directory):
            reply = run_worker(directory, dict(action="probe", server_path=self.settings.dpf_path), self.settings.timeout)
            atomic_json(directory / "runtime.json", reply["data"])
            return reply["data"], [check_artifact(directory / "runtime.json", "json")]
        return self._post_job("probe_dpf_runtime", dict(units="not_applicable"), [], work)

    def inspect_dpf_results(self, path: str, file_type: str, actunits: str | None = None) -> dict:
        """Optional DPF source/result inventory with explicit server version and time-set IDs. Requires local DPF Server; does not control LS-PrePost. No implicit unit system."""
        return self._dpf_job("inspect", path, file_type, actunits, dict(units="not_applicable"))

    def export_dpf_result(self, path: str, file_type: str, result: str, units: str,
                          states: list[StrictInt] | None = None, entity_ids: list[StrictInt] | None = None,
                          label_filter: dict[str, StrictInt] | None = None, component: StrictInt | None = None,
                          actunits: str | None = None) -> dict:
        """Optional DPF beam/vector/erosion or global/part/contact-history export. Preserves labels and each result's time-ID mapping; no averaging/layer collapse. d3plot spatial results require explicit states. units is a declaration, not conversion. Remote DPF, tensor layers, solver launch and rendering are outside this adapter."""
        contract = result_contract(file_type, result)
        if component is not None and (type(component) is not int or not 0 <= component < contract["components"]):
            raise ValueError("Component is zero-based and must fit the selected result")
        if states is not None:
            ids(states, "states", 2000)
        if entity_ids is not None:
            ids(entity_ids, "entity_ids", 20000)
        if contract["location"] != "TimeFreq_steps" and not states:
            raise ValueError("Spatial DPF results require explicit time-set IDs")
        if contract["location"] != "TimeFreq_steps" and entity_ids is None and len(states) != 1:
            raise ValueError("Full-domain spatial extraction accepts one state; provide explicit entities for histories")
        if states and entity_ids and len(states) * len(entity_ids) * contract["components"] > 500000:
            raise ValueError("Requested spatial history exceeds the500000value budget")
        if contract["location"] == "TimeFreq_steps" and entity_ids is not None:
            raise ValueError("Use part/interface/idtype labels for histories, not mesh entity_ids")
        if label_filter is not None and (not isinstance(label_filter, dict) or len(label_filter) > 8 or
            any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", k) or type(v) is not int or v < 0
                for k, v in label_filter.items())):
            raise ValueError("Label filters must map label names to nonnegative integer values")
        return self._dpf_job("export", path, file_type, actunits,
                             dict(result=result, units=units, states=states, entity_ids=entity_ids,
                                  label_filter=label_filter, component=component))

    def _dpf_job(self, action, path, file_type, actunits, arguments):
        family = source_family(self.settings, path, file_type)
        unit_file = self.settings.input_path(actunits) if actunits else None
        sources = family + ([unit_file] if unit_file else [])
        if sum(p.stat().st_size for p in sources) > 2 * 1024**3:
            raise ValueError("DPF staging exceeds2GiB; select a bounded fixture")
        def work(directory):
            staged = directory / "inputs"
            staged.mkdir()
            for source in family:
                shutil.copy2(source, staged / source.name)
            if unit_file:
                if unit_file.name in {p.name for p in family}:
                    raise ValueError("actunits basename collides with result family")
                shutil.copy2(unit_file, staged / unit_file.name)
            request = dict(action=action, path=str(staged / family[0].name), file_type=file_type,
                           actunits=str(staged / unit_file.name) if unit_file else None,
                           server_path=self.settings.dpf_path, timeout=self.settings.timeout, **arguments)
            reply = run_worker(directory, request, self.settings.timeout)
            artifacts = []
            if reply["rows"] is not None:
                artifacts.append(write_labelled_csv(directory / "result.csv", reply["rows"]))
            atomic_json(directory / "semantics.json", reply["data"])
            artifacts.append(check_artifact(directory / "semantics.json", "json"))
            return reply["data"], artifacts
        return self._post_job("dpf_" + action, dict(path=path, file_type=file_type, actunits=actunits,
                               server_path=self.settings.dpf_path, **arguments), sources, work)
