"""Typed operations shared by the MCP server, CLI and native smoke tests."""
import json
import math
import os
import re
import subprocess
from pathlib import Path

from pydantic import StrictInt

from .config import Settings, command_path
from .dpf_tools import DpfTools
from .engine.context import NativeContext
from .engineering import EngineeringTools
from .fringe_presentation import averaging_command
from .gui_boundaries import GuiBoundaryTools
from .gui_common import GuiCommonTools
from .gui_controls import GuiControls
from .gui_entities import GuiEntityTools
from .gui_media import GuiMediaTools
from .gui_mesh import GuiMeshTools
from .gui_motion import GuiMotionTools
from .gui_nodal_loads import GuiNodalLoadTools
from .gui_quality import GuiQualityTools
from .gui_renumber import GuiRenumberTools
from .gui_segments import GuiSegmentTools
from .gui_selection import GuiSelectionTools
from .gui_visibility import GuiVisibilityTools
from .installation_assets import InstallationTools
from .jobs import Jobs, atomic_json, check_artifact, fingerprint, now
from .keyword_tools import KeywordTools
from .mesh_tools import MeshTools
from .post_tools import PostTools
from .pre_tools import PreTools
from .programs import ProgramTools
from .results import lasso_vectors, open_binout
from .runner import decode, execute, failure_message
from .sessions import SessionTools
from .workflow_sweeps import WorkflowSweepTools
from .workflows import WorkflowTools

VIEWS = {"isometric": "isometric x", "top": "top", "bottom": "bottom", "front": "front",
         "back": "back", "left": "left", "right": "right"}


def integer(value: int, name: str, minimum: int = 1, maximum: int = 2_000_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def numbers(values, length: int, name: str, positive: bool = False) -> list[float]:
    if len(values) != length:
        raise ValueError(f"{name} requires {length} numbers")
    converted = [float(v) for v in values]
    if not all(math.isfinite(v) and (not positive or v > 0) for v in converted):
        raise ValueError(f"Invalid {name}")
    return converted


def unit_label(units: str) -> str:
    if not isinstance(units, str) or not units.strip() or len(units) > 100:
        raise ValueError("An explicit unit-system label is required; no units are inferred")
    return units.strip()


class Service(PostTools, PreTools, KeywordTools, SessionTools, InstallationTools, MeshTools, EngineeringTools, WorkflowTools, WorkflowSweepTools, GuiControls, ProgramTools, GuiMeshTools, GuiSelectionTools, GuiRenumberTools, GuiQualityTools, GuiMediaTools, DpfTools, GuiCommonTools, GuiVisibilityTools, GuiEntityTools, GuiSegmentTools, GuiBoundaryTools, GuiMotionTools, GuiNodalLoadTools):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jobs = Jobs(settings.workspace)
        self._native_context = NativeContext()

    def _native(self, action: str, parameters: dict, model: str | None = None,
                file_type: str = "keyword", graphics: bool = False,
                artifacts: tuple[tuple[str, str], ...] = (), export: bool = False) -> dict:
        executor = self._native_context.executor
        if executor is not None:
            if model is not None:
                raise ValueError("Session operations cannot load a batch input")
            return executor(action=action, parameters=parameters, file_type=file_type,
                            artifacts=artifacts, export=export)
        exe = self.settings.native_executable()
        if file_type not in ("keyword", "d3plot"):
            raise ValueError("file_type must be keyword or d3plot")
        source = self.settings.input_path(model) if model else None
        if source and file_type == "keyword":
            self.settings.check_keyword_includes(source)
            if export and any(line.strip().upper().startswith("*INCLUDE")
                              for line in source.read_text(errors="replace").splitlines()):
                raise ValueError("Native export of include-bearing models needs a staged include-tree implementation")
        directory, manifest = self.jobs.create(action, parameters)
        manifest["backend"] = "lsprepost"
        manifest["executable"] = fingerprint(exe)
        manifest["native_channel"] = "scl" if action == "scl_probe" else "embedded_python"
        request = {"job_id": manifest["job_id"], "action": action, "parameters": parameters,
                   "job_directory": str(directory), "model": str(source) if source else None,
                   "file_type": file_type}
        atomic_json(directory / "request.json", request)
        if source:
            manifest["input"] = fingerprint(source)
        bridge = Path(__file__).with_name("embedded.py").resolve()
        bootstrap = directory / "bootstrap.py"
        bootstrap.write_text("import os, runpy\nos.chdir(" + repr(str(directory)) + ")\n"
                             "bridge = runpy.run_path(" + repr(str(bridge)) + ")\n"
                             "bridge['run'](" + repr(str(directory / "request.json")) + ", "
                             + repr(str(directory / "response.json")) + ")\n", encoding="utf-8")
        commands = ["new"]
        if source and action == "scl_probe":
            opener = "openc" if file_type == "d3plot" else "open"
            commands.append(f"{opener} {file_type} {command_path(source)}")
        if action == "scl_probe":
            script = directory / "probe.scl"
            script.write_text('/*LS-SCRIPT*/\ndefine:\nvoid main(void)\n{\nInt n;\nFILE *fp;\n'
                              'n = SCLGetDataCenterInt("num_nodes");\n'
                              'fp = fopen("scl_nodes.txt", "w");\nfprintf(fp, "%d\\n", n);\n'
                              'fclose(fp);\n}\nmain();\n', encoding="ascii")
            commands.append("runscript probe.scl")
        if action != "scl_probe":
            commands.append("runpython " + command_path(bootstrap))
        if export:
            # Some Windows builds prepend a temporary basename and cannot save
            # an absolute drive path. The bootstrap pins cwd to this owned job.
            commands.append('save keyword "model.k"')
        commands.append("exit")
        cfile = directory / "commands.cfile"
        cfile.write_text("\n".join(commands) + "\n", encoding="utf-8")
        manifest.update(status="running", started_at=now(), execution_mode="graphics" if graphics else "nographics")
        atomic_json(directory / "job.json", manifest)
        try:
            process = execute(exe, cfile, directory, timeout=self.settings.timeout, graphics=graphics)
            manifest["process"] = process
            if process.get("engine_status") == "failed" or process["timed_out"] or process["returncode"] != 0:
                raise RuntimeError(failure_message(process, f"LS-PrePost process failed: returncode={process['returncode']}, timeout={process['timed_out']}"))
            reply_path = directory / "response.json"
            if action == "scl_probe":
                count = int((directory / "scl_nodes.txt").read_text().strip())
                if count <= 0:
                    raise ValueError("SCL did not report a nonempty model")
                atomic_json(reply_path, {"job_id": manifest["job_id"], "ok": True,
                                        "data": {"scl_nodes": count, "backend": "scl", "requires_python": False}})
            if not reply_path.is_file():
                raise RuntimeError("Embedded Python produced no response; inspect LS-PrePost logs and Python configuration")
            response = json.loads(reply_path.read_text(encoding="utf-8"))
            if response.get("job_id") != manifest["job_id"]:
                raise RuntimeError("Embedded response belongs to a different job")
            if not response.get("ok"):
                manifest["bridge_error"] = response.get("error")
                raise RuntimeError(response.get("error", {}).get("message", "Embedded action failed"))
            manifest["data"] = response["data"]
            if source and action == "inspect_model" and not response["data"].get("counts", {}).get("nodes"):
                raise RuntimeError("Input did not produce a nonempty model")
            for name, kind in artifacts:
                manifest["artifacts"].append(check_artifact(directory / name, kind))
            if source and fingerprint(source) != manifest["input"]:
                raise RuntimeError("Input changed during the task")
            manifest["status"] = "succeeded"
        except Exception as exc:
            manifest.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        manifest["finished_at"] = now()
        manifest["job_directory"] = str(directory)
        manifest["logs"] = [str(p) for p in directory.glob("*.log")] + [str(p) for p in directory.glob("lspost.*")]
        atomic_json(directory / "job.json", manifest)
        return manifest

    def probe_environment(self) -> dict:
        """Launch a fresh native instance and report its embedded Python; missing empty-model counters are warnings."""
        return self._native("probe", {})

    def list_installations(self) -> dict:
        """List configured executables only; file existence is not a compatibility test."""
        return {"default": str(self.settings.executable) if self.settings.executable else None,
                "profiles": [{"version": k, "executable": str(v), "exists": v.is_file(),
                              "verification": "Call an explicit probe; existence does not prove compatibility"}
                             for k, v in self.settings.profiles.items()]}

    def run_on_version(self, version: str, action: str, parameters: dict) -> dict:
        """Run an existing typed action using an explicitly configured installation; no global switch."""
        allowed = {"probe_environment", "probe_scl", "inspect_d3plot_scl", "inspect_model", "list_nodes", "list_parts",
                   "get_element_connectivity", "create_shell_plate", "export_keyword",
                   "extract_nodal_results", "extract_node_history", "render_snapshot", "measure_parts",
                   "extract_native_fields", "extract_native_stress", "extract_native_ascii_curve",
                   "extract_native_binout_curve", "native_postprocess_case", "create_tensile_shell_plate",
                   "create_solid_box", "translate_mesh_nodes", "move_elements_to_part", "extrude_shell_part",
                   "rotate_mesh_nodes", "create_solid_sphere", "native_tensile_postprocess", "native_energy_postprocess",
                   "execute_native_program", "run_native_macro"}
        if version not in self.settings.profiles:
            raise ValueError("Unknown installation profile")
        if action not in allowed:
            raise ValueError("Action cannot be dispatched through the version selector")
        scoped = Service(Settings(self.settings.workspace, self.settings.profiles[version],
                                  self.settings.allowed_roots, self.settings.timeout))
        result = getattr(scoped, action)(**parameters)
        result["installation_profile"] = version
        if result.get("job_directory"):
            atomic_json(Path(result["job_directory"]) / "job.json", result)
        return result

    def probe_scl(self, model: str) -> dict:
        """Count nodes in a keyword model through native SCL without requiring embedded Python."""
        return self._native("scl_probe", {}, model, artifacts=(("scl_nodes.txt", "text"),))

    def inspect_d3plot_scl(self, path: str) -> dict:
        """Native SCL inventory with bounded staged input for builds without Python."""
        from .scl_backend import inspect_database
        return inspect_database(self.settings, self.jobs, self.settings.input_path(path))

    def inspect_model(self, model: str, file_type: str = "keyword") -> dict:
        """Open keyword/d3plot in a fresh native Python instance; return counts, user part IDs and state times."""
        return self._native("inspect_model", {}, model, file_type)

    def list_nodes(self, model: str, file_type: str = "keyword", offset: int = 0, limit: int = 100) -> dict:
        """Page native user node IDs and reference coordinates. Offset is zero-based; coordinates are not deformed."""
        return self._native("list_nodes", {"offset": integer(offset, "offset", 0),
                            "limit": integer(limit, "limit", 1, 10000)}, model, file_type)

    def list_parts(self, model: str, file_type: str = "keyword", limit: int = 100) -> dict:
        """List native user part IDs and optional names; null names indicate an unavailable binding."""
        return self._native("list_parts", {"limit": integer(limit, "limit", 1, 10000)}, model, file_type)

    def get_element_connectivity(self, model: str, element_id: int, element_type: str = "shell",
                                 file_type: str = "keyword") -> dict:
        """Query one shell/solid/beam using a user element ID; return connected user node IDs."""
        if element_type not in ("shell", "solid", "beam"):
            raise ValueError("element_type must be shell, solid or beam")
        return self._native("connectivity", {"element_id": integer(element_id, "element_id"),
                            "element_type": element_type}, model, file_type)

    def create_shell_plate(self, nx: int, ny: int, size: list[float], units: str,
                           origin: list[float] | None = None, part_id: int = 1,
                           node_start: int = 1, element_start: int = 1) -> dict:
        """Create an XY shell mesh in native LS-PrePost, verify counts and save a new keyword mesh. Not a complete analysis deck."""
        integer(nx, "nx", 1, 500)
        integer(ny, "ny", 1, 500)
        if nx * ny > 100000:
            raise ValueError("Plate exceeds the initial-release mesh limit")
        p = {"nx": nx, "ny": ny, "size": numbers(size, 2, "size", True),
             "origin": numbers(origin or [0, 0, 0], 3, "origin"), "units": unit_label(units),
             "part_id": integer(part_id, "part_id"), "node_start": integer(node_start, "node_start"),
             "element_start": integer(element_start, "element_start")}
        return self._native("create_plate", p, artifacts=(("model.k", "keyword"),), export=True)

    def export_keyword(self, model: str) -> dict:
        """Save a standalone keyword model into a new owned job. Include-bearing export is rejected."""
        return self._native("export_keyword", {}, model, artifacts=(("model.k", "keyword"),), export=True)

    def extract_nodal_results(self, d3plot: str, node_ids: list[StrictInt], quantity: str, state: StrictInt, units: str) -> dict:
        """Extract native position/displacement/velocity at a 1-based state. Older unverified vector ABIs are blocked; use explicit reader tools."""
        return self._nodal("extract_nodal", d3plot, node_ids, quantity, [state], units)

    def extract_node_history(self, d3plot: str, node_ids: list[StrictInt], quantity: str,
                             states: list[StrictInt], units: str,
                             curve_components: list[str] | None = None, time_unit: str | None = None) -> dict:
        """Export native vectors by user ID/state, restoring the original GUI state. Optional x/y/z/magnitude scalar time,value curves feed engineering tools (100 curves maximum); requires explicit shared time_unit and increasing states. Tested on the 4.13 profile."""
        return self._nodal("node_history", d3plot, node_ids, quantity, states, units, curve_components, time_unit)

    def _nodal(self, action, d3plot, node_ids, quantity, states, units, curve_components=None, time_unit=None):
        from .field_contracts import FieldSpec, ResultSelection, SamplingSpec

        selection = ResultSelection("node", node_ids, states)
        node_ids, states = list(selection.entity_ids), list(selection.states)
        if not node_ids or not states or len(node_ids) > 10000 or len(node_ids)*len(states) > 100000:
            raise ValueError("Requested node/state matrix is empty or exceeds 100000 rows")
        if len(set(node_ids)) != len(node_ids) or len(set(states)) != len(states):
            raise ValueError("Duplicate node IDs or states")
        if quantity not in ("position", "displacement", "velocity"):
            raise ValueError("Unsupported nodal quantity")
        if curve_components is not None and (
            not isinstance(curve_components, list) or not curve_components
            or any(not isinstance(c, str) or c not in ("x", "y", "z", "magnitude") for c in curve_components)
            or len(set(curve_components)) != len(curve_components)
        ):
            raise ValueError("curve_components requires unique x/y/z/magnitude names")
        components = list(curve_components or [])
        if components:
            if len(node_ids) * len(components) > 100:
                raise ValueError("Scalar curve export is bounded to 100 curves")
            if len(states) < 2 or states != sorted(states):
                raise ValueError("Scalar curves require at least two increasing states")
            if quantity == "position" and "magnitude" in components:
                raise ValueError("Position magnitude is not a displacement")
            unit_label(time_unit)
        field_spec = FieldSpec(
            "lsprepost", tuple(quantity + "_" + axis for axis in ("x", "y", "z")), unit_label(units),
            selection, SamplingSpec.native("node", "mid"),
            "native DataCenter vector components; no additional coordinate transform",
            "native nodal values; no additional averaging",
            "requested registered nodes; no explicit alive/deletion mask",
        ).describe()
        p = {"node_ids": [integer(i, "node_id") for i in node_ids], "quantity": quantity,
             "states": [integer(i, "state") for i in states], "state": states[0], "units": unit_label(units),
             "curve_components": components, "time_unit": time_unit, "field_spec": field_spec,
             "preserve_state": True}
        artifacts = [("nodal.csv", "csv")] + [
            ("node_%d_%s.csv" % (uid, component), "csv") for uid in node_ids for component in components
        ]
        return self._native(action, p, d3plot, "d3plot", artifacts=tuple(artifacts))

    def render_snapshot(self, model: str, file_type: str = "keyword", view: str = "isometric",
                        state: int | None = None, fringe_code: int | None = None, averaging: str = "minmax") -> dict:
        """Render native PNG with default MinMax display averaging. Preserve model title and native result names. Fringe codes require d3plot/state; no implicit shell-layer override."""
        averaging_command(averaging)
        if view not in VIEWS:
            raise ValueError("Unsupported view")
        if state is not None:
            integer(state, "state")
        if fringe_code is not None:
            integer(fringe_code, "fringe_code", 1, 9999)
            if file_type != "d3plot" or state is None:
                raise ValueError("A fringe requires d3plot and an explicit native state")
        return self._native("render_snapshot", {"view": VIEWS[view], "state": state, "fringe_code": fringe_code, "averaging": averaging},
                            model, file_type, graphics=True, artifacts=(("snapshot.png", "png"),))

    def measure_parts(self, model: str, part_ids: list[int]) -> dict:
        """Return raw native part-volume command values; layout/units remain build-dependent and require interpretation."""
        if not part_ids or len(part_ids) > 1000:
            raise ValueError("part_ids must contain 1..1000 IDs")
        return self._native("measure_parts", {"part_ids": [integer(i, "part_id") for i in part_ids]}, model)

    def read_job(self, job_id: str) -> dict:
        """Read a recorded task including status, errors, log paths and validated artifacts."""
        return self.jobs.get(job_id)

    def list_jobs(self, limit: int = 20) -> list[dict]:
        """List recent task manifests in the configured workspace."""
        return self.jobs.list(limit)

    def inspect_binout(self, path: str, branch: str | None = None) -> dict:
        """List LASSO binout branches/variables from one literal file; reject incomplete MPP shard sets."""
        source = self._binout_source(path)
        with open_binout(str(source)) as db:
            values = db.read(branch) if branch else db.read()
            return {"backend": "lasso", "source": str(source), "branch": branch, "children": [str(x) for x in values]}

    def _binout_source(self, path: str) -> Path:
        source = self.settings.input_path(path)
        match = re.fullmatch(r"(binout)(\d+)", source.name, flags=re.I)
        if match:
            siblings = [p for p in source.parent.iterdir()
                        if p.is_file() and re.fullmatch(r"binout\d+", p.name, flags=re.I)]
            if len(siblings) > 1:
                raise ValueError("Multiple MPP binout shards detected; single-file extraction would be incomplete. Shard-set support is not verified in this release.")
        return source

    def inspect_d3plot_database(self, path: str) -> dict:
        """Read file metadata through optional LASSO, without launching LS-PrePost."""
        from lasso.dyna import D3plot
        source = self.settings.input_path(path)
        db = D3plot(str(source), state_array_filter=["timesteps"], buffered_reading=True)
        times = db.arrays.get("timesteps", [])
        return {"backend": "lasso", "source": str(source), "node_count": int(db.header.n_nodes),
                "shell_count": int(db.header.n_shells), "solid_count": int(db.header.n_solids),
                "state_count": len(times), "state_times": [float(t) for t in times[:10000]],
                "time_list_truncated": len(times) > 10000,
                "array_shapes": {str(k): list(v.shape) for k, v in db.arrays.items()}}

    def inspect_keyword_deck(self, model: str) -> dict:
        """Inventory a deck using PyDYNA; no solver or include expansion is performed."""
        from .deck_backend import inspect_deck
        source = self.settings.input_path(model)
        self.settings.check_keyword_includes(source)
        return inspect_deck(source)

    def create_elastic_material(self, material_id: int, density: float, young_modulus: float,
                                poisson_ratio: float, units: str) -> dict:
        """Create and reimport-check a MAT_001 fragment using optional PyDYNA."""
        return self._elastic(None, material_id, density, young_modulus, poisson_ratio, units)

    def update_elastic_material(self, model: str, material_id: int, density: float,
                                young_modulus: float, poisson_ratio: float, units: str) -> dict:
        """Modify one elastic material into a fresh deck; preserve the original file."""
        source = self.settings.input_path(model)
        self.settings.check_keyword_includes(source)
        return self._elastic(source, material_id, density, young_modulus, poisson_ratio, units)

    def _elastic(self, source, mid, density, young_modulus, poisson_ratio, units):
        from .deck_backend import create_material, material_values, update_material
        values = material_values(density, young_modulus, poisson_ratio)
        integer(mid, "material_id")
        directory, manifest = self.jobs.create("update_material" if source else "create_material",
                           {"material_id": mid, "values": values, "units": unit_label(units), "backend": "pydyna"})
        if source:
            manifest["input"] = fingerprint(source)
        try:
            output = directory / "material.k"
            data = update_material(source, output, mid, values) if source else create_material(output, mid, values)
            if source and fingerprint(source) != manifest["input"]:
                raise RuntimeError("Original deck changed")
            manifest.update(status="succeeded", data=data, artifacts=[check_artifact(output, "keyword")])
        except Exception as exc:
            manifest.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        manifest.update(finished_at=now(), job_directory=str(directory))
        atomic_json(directory / "job.json", manifest)
        return manifest

    def inspect_lsreader(self, path: str) -> dict:
        """Inspect a result using LS-Reader in its own configured Python/ABI process."""
        return self._lsreader("inspect", path, {})

    def extract_lsreader_nodal(self, path: str, node_ids: list[int], quantity: str,
                               states: list[int], units: str) -> dict:
        """Extract LS-Reader vectors with 1-based public states and true user IDs."""
        if quantity not in ("displacement", "velocity") or not node_ids or not states:
            raise ValueError("Unsupported/empty vector request")
        if len(node_ids)*len(states) > 100000:
            raise ValueError("Request exceeds 100000 rows")
        if len(set(node_ids)) != len(node_ids) or len(set(states)) != len(states):
            raise ValueError("Duplicate IDs or states")
        return self._lsreader("nodal", path, {"node_ids": [integer(i, "node_id") for i in node_ids],
                             "quantity": quantity, "states": [integer(i, "state") for i in states],
                             "units": unit_label(units)})

    def _lsreader(self, action, path, parameters):
        python = os.environ.get("LSPP_LSREADER_PYTHON")
        if not python or not Path(python).is_file():
            raise ValueError("Set LSPP_LSREADER_PYTHON to an ABI-compatible Python with lsreader installed")
        source = self.settings.input_path(path)
        directory, manifest = self.jobs.create("lsreader_"+action, {**parameters, "backend": "lsreader"})
        request = {"job_id": manifest["job_id"], "action": action, "source": str(source),
                   "parameters": parameters, "output_csv": str(directory / "nodal.csv")}
        atomic_json(directory / "request.json", request)
        try:
            worker = Path(__file__).with_name("lsreader_worker.py")
            result = subprocess.run([python, "-B", str(worker), str(directory / "request.json"),
                                     str(directory / "response.json")], cwd=directory,
                                    capture_output=True, timeout=self.settings.timeout,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            (directory / "stdout.log").write_text(decode(result.stdout), encoding="utf-8")
            (directory / "stderr.log").write_text(decode(result.stderr), encoding="utf-8")
            manifest["returncode"] = result.returncode
            if result.returncode != 0:
                raise RuntimeError("LS-Reader worker exited with code " + str(result.returncode))
            response = json.loads((directory / "response.json").read_text(encoding="utf-8"))
            if response.get("job_id") != manifest["job_id"] or not response.get("ok"):
                raise RuntimeError(str(response.get("error", "Worker response is invalid")))
            manifest.update(status="succeeded", data=response["data"])
            if action == "nodal":
                manifest["artifacts"] = [check_artifact(directory / "nodal.csv", "csv")]
        except Exception as exc:
            manifest.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        manifest.update(finished_at=now(), job_directory=str(directory))
        atomic_json(directory / "job.json", manifest)
        return manifest

    def extract_d3plot_nodal(self, path: str, node_ids: list[int], quantity: str,
                            states: list[int], units: str) -> dict:
        """Extract vectors through LASSO. Public states are 1-based, IDs are user IDs."""
        import csv

        import numpy as np
        from lasso.dyna import D3plot
        if quantity not in ("displacement", "velocity"):
            raise ValueError("LASSO vector quantity must be displacement or velocity")
        if not node_ids or not states or len(node_ids) * len(states) > 100000:
            raise ValueError("Invalid or oversized node/state request")
        ids_requested = [integer(i, "node_id") for i in node_ids]
        native_states = [integer(i, "state") for i in states]
        if len(set(ids_requested)) != len(ids_requested) or len(set(native_states)) != len(native_states):
            raise ValueError("Duplicate IDs or states")
        source = self.settings.input_path(path)
        directory, manifest = self.jobs.create("extract_d3plot_nodal", {"backend": "lasso", "quantity": quantity,
                          "node_ids": ids_requested, "states": native_states, "units": unit_label(units)})
        try:
            key = "node_" + quantity
            db = D3plot(str(source), state_array_filter=[key, "timesteps"], buffered_reading=True)
            times = np.asarray(db.arrays["timesteps"])
            vectors = lasso_vectors(db.arrays, quantity)
            user_ids = np.asarray(db.arrays["node_ids"])
            if vectors.ndim != 3 or vectors.shape != (len(times), len(user_ids), 3):
                raise ValueError("Unexpected nodal result dimensions")
            if max(native_states) > len(times):
                raise ValueError("Requested state is not in the database")
            lookup = {int(uid): i for i, uid in enumerate(user_ids)}
            if any(uid not in lookup for uid in ids_requested):
                raise ValueError("Requested user node ID is not in the database")
            output = directory / "nodal.csv"
            with output.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["state", "time", "node_id", "x", "y", "z", "magnitude"])
                for state in native_states:
                    for uid in ids_requested:
                        vec = vectors[state - 1, lookup[uid]]
                        writer.writerow([state, float(times[state - 1]), uid, *vec, float(np.linalg.norm(vec))])
            manifest.update(status="succeeded", artifacts=[check_artifact(output, "csv")],
                            data={"row_count": len(native_states)*len(ids_requested), "id_kind": "user",
                                  "state_index_base": 1, "backend": "lasso", "quantity": quantity,
                                  "displacement_reference": "initial_geometry" if quantity == "displacement" else None})
        except Exception as exc:
            manifest.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        manifest.update(finished_at=now(), job_directory=str(directory))
        atomic_json(directory / "job.json", manifest)
        return manifest

    def extract_binout_curve(self, path: str, branch: str, variable: str, units: str,
                             entity_id: int | None = None) -> dict:
        """Export a scalar or explicitly ID-selected binout curve through LASSO; never guess an entity column."""
        import csv

        import numpy as np
        if not re.fullmatch(r"[A-Za-z0-9_]+", branch) or not re.fullmatch(r"[A-Za-z0-9_]+", variable):
            raise ValueError("Use one binout branch and variable name")
        source = self._binout_source(path)
        directory, manifest = self.jobs.create("extract_binout_curve", {"branch": branch, "variable": variable,
                                             "entity_id": entity_id, "units": unit_label(units), "backend": "lasso"})
        try:
            with open_binout(str(source)) as db:
                times = np.asarray(db.read(branch, "time"))
                values = np.asarray(db.read(branch, variable))
                if values.ndim == 2:
                    if entity_id is None:
                        raise ValueError("Entity-valued arrays require an explicit user entity_id")
                    ids = np.asarray(db.read(branch, "ids")).reshape(-1)
                    matches = np.where(ids == entity_id)[0]
                    if len(matches) != 1 or values.shape[1] != len(ids):
                        raise ValueError("Cannot align requested entity ID with result columns")
                    values = values[:, int(matches[0])]
                elif entity_id is not None:
                    raise ValueError("A scalar curve does not have an entity axis")
                if times.ndim != 1 or values.ndim != 1 or len(times) != len(values):
                    raise ValueError("Unsupported result dimensions")
                if len(times) > 1000000:
                    raise ValueError("Curve exceeds one million rows")
                with (directory / "curve.csv").open("w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["time", "value"])
                    writer.writerows(zip(times, values))
            manifest.update(status="succeeded", data={"row_count": len(times), "backend": "lasso"},
                            artifacts=[check_artifact(directory / "curve.csv", "csv")])
        except Exception as exc:
            manifest.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        manifest.update(finished_at=now(), job_directory=str(directory))
        atomic_json(directory / "job.json", manifest)
        return manifest
