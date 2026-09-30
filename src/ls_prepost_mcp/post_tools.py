"""Result tools shared by MCP and CLI; each export has a recorded, isolated job."""
import math
import re

from .jobs import atomic_json, fingerprint, now
from .post_backend import (
    ascii_table,
    binout_tokens,
    field_domain,
    ids,
    result_ids,
    selected_database,
    write_csv,
)
from .stress import CONVENTIONS, NULLABLE, stress_metrics


class PostTools:
    def extract_native_binout_curve(self, path: str, branch: str, quantity: str, units: str,
                                    entity_id: int | None = None) -> dict:
        """Read nodout components or glstat energy through LS-PrePost SCLBinout, opening a staged copy. Single-file binout only."""
        from .native_results import native_binout
        return native_binout(self.settings, self.jobs, self._binout_source(path), branch, quantity, entity_id, units)

    def native_postprocess_case(self, path: str, units: str) -> dict:
        """Native 4.13 acceptance workflow: all saved states, three sample entities/type, stress invariants, ASCII curves and PNG. Stages then removes source copies; preserves evidence."""
        from .native_batch import run_case
        if not isinstance(units, str) or not units.strip():
            raise ValueError("Explicit units required")
        return run_case(self.settings, self.jobs, self.settings.input_path(path), units)

    def extract_native_fields(self, path: str, entity_type: str, entity_ids: list[int],
                               states: list[int], fields: list[str], integration_point: str, units: str) -> dict:
        """Use LS-PrePost SCL to export native stress/strain/plastic-strain or nodal components. Opens staged copies only; states/user IDs are explicit."""
        from .native_results import native_fields
        return native_fields(self.settings, self.jobs, self.settings.input_path(path), entity_type,
                             entity_ids, states, fields, integration_point, units)

    def extract_native_stress(self, path: str, element_type: str, element_ids: list[int],
                               states: list[int], integration_point: str, units: str) -> dict:
        """LS-PrePost SCL six-component stresses and native Mises crosscheck, then derive triaxiality and both Lode conventions. Opens staged copies only."""
        from .native_results import STRESS_KEYS, native_fields
        if element_type == "node":
            raise ValueError("Stress requires element results")
        return native_fields(self.settings, self.jobs, self.settings.input_path(path), element_type,
                             element_ids, states, STRESS_KEYS + ["von_mises"], integration_point, units, derived=True)

    def extract_native_ascii_curve(self, path: str, database: str, component: int, units: str,
                                   entity_id: int | None = None) -> dict:
        """Use native LS-PrePost ASCII/XYPlot to export GLSTAT or an explicit entity history. Component codes come from the native ASCII dialog; source is staged."""
        from .native_results import native_ascii
        return native_ascii(self.settings, self.jobs, self.settings.input_path(path), database, component, entity_id, units)

    def _post_job(self, action, parameters, sources, callback):
        units = parameters.get("units", "")
        if not isinstance(units, str) or not units.strip() or len(units) > 100:
            raise ValueError("Explicit unit-system label required")
        directory, manifest = self.jobs.create(action, parameters)
        manifest["inputs"] = [fingerprint(p) for p in sources]
        try:
            data, artifacts = callback(directory)
            if [fingerprint(p) for p in sources] != manifest["inputs"]:
                raise RuntimeError("Source changed during extraction")
            manifest.update(status="succeeded", data=data, artifacts=artifacts)
        except Exception as exc:
            manifest.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        manifest.update(finished_at=now(), job_directory=str(directory))
        atomic_json(directory / "job.json", manifest)
        return manifest

    def _result_family(self, path):
        source = self.settings.input_path(path)
        family = [source] + sorted(p for p in source.parent.iterdir()
                                   if p.name.startswith(source.name) and p.name[len(source.name):].isdigit())
        return [self.settings.input_path(str(p)) for p in family]

    def compute_stress_invariants(self, stresses: list[list[float]], units: str,
                                  relative_tolerance: float = 1e-12) -> dict:
        """Six components xx,yy,zz,xy,yz,xz -> principals, Mises, triaxiality and two explicit Lode conventions. Hydrostatic ratios are null."""
        if not stresses or len(stresses) > 10000:
            raise ValueError("Provide 1..10000 stress tensors")
        if not isinstance(units, str) or not units.strip():
            raise ValueError("Explicit stress unit required")
        return {"units": units, "conventions": CONVENTIONS, "relative_tolerance": relative_tolerance,
                "results": [stress_metrics(s, relative_tolerance) for s in stresses]}

    def inspect_result_fields(self, path: str, state: int = 1) -> dict:
        """Inventory LASSO fields at one 1-based state, stored axis sizes and bounded user-ID samples. Missing fields cannot be reconstructed."""
        from lasso.dyna import ArrayType
        source = self.settings.input_path(path)
        db, _ = selected_database(source, [state], ArrayType.get_state_array_names())
        fields = []
        for key, value in db.arrays.items():
            try:
                domain = field_domain(key)
            except ValueError:
                continue
            entry = {"field": key, "domain": domain, "shape": list(value.shape),
                     "component_frame": "as_stored; no coordinate transformation"}
            try:
                if domain != "global":
                    uids = result_ids(db.arrays, domain, value.shape[1])
                    entry.update(id_sample=[int(i) for i in uids[:50]], trailing_axis_sizes=list(value.shape[2:]))
                else:
                    entry["trailing_axis_sizes"] = list(value.shape[1:])
                entry["extractable"] = True
            except (ValueError, KeyError, IndexError) as exc:
                entry.update(extractable=False, reason=str(exc))
            fields.append(entry)
        return {"backend": "lasso", "state": state, "time": float(db.arrays["timesteps"][0]), "fields": fields,
                "selection": "slot indices are 1-based stored indices; no shell top/bottom or material-history meaning inferred"}

    def extract_d3plot_field(self, path: str, field: str, states: list[int], units: str,
                             entity_ids: list[int] | None = None,
                             component_indices: list[int] | None = None) -> dict:
        """Export any supported stored node/element/part/global scalar slice. Explicit 1-based trailing indices select component, layer or history slot; no averaging."""
        import numpy as np
        domain = field_domain(field)
        ids(states, "states", 10000)
        if domain != "global":
            ids(entity_ids, "entity_ids")
        elif entity_ids:
            raise ValueError("Global fields have no entity IDs")
        indices = component_indices or []
        if any(type(i) is not int or i < 1 for i in indices):
            raise ValueError("Component indices are 1-based")
        if len(states)*max(1, len(entity_ids or [])) > 1000000:
            raise ValueError("Requested export exceeds one million rows")
        sources = self._result_family(path)
        def work(directory):
            db, mapping = selected_database(sources[0], states, [field])
            values = np.asarray(db.arrays[field])
            if field == "node_displacement":
                from .results import lasso_vectors
                values = lasso_vectors(db.arrays, "displacement")
            offset = 1 if domain == "global" else 2
            trailing = values.shape[offset:]
            if len(indices) != len(trailing) or any(i > n for i, n in zip(indices, trailing)):
                raise ValueError(f"Provide one 1-based index per trailing axis {trailing}")
            lookup = {} if domain == "global" else {int(v): i for i, v in enumerate(result_ids(db.arrays, domain, values.shape[1]))}
            requested = entity_ids or [0]
            if domain != "global" and any(v not in lookup for v in requested):
                raise ValueError("User entity ID absent from this result field (possibly rigid/no result)")
            def rows():
                for state in states:
                    for uid in requested:
                        prefix = (mapping[state],) if domain == "global" else (mapping[state], lookup[uid])
                        yield [state, float(db.arrays["timesteps"][mapping[state]]), uid,
                               float(values[prefix + tuple(i-1 for i in indices)])]
            artifact = write_csv(directory / "field.csv", ["state", "time", "entity_id", "value"], rows())
            return {"backend": "lasso", "field": field, "domain": domain, "state_index_base": 1,
                    "component_indices": indices, "stored_axis_sizes": list(trailing), "averaging": "none",
                    "frame": "as_stored", "history_meaning": "consult material manual; raw stored slot only",
                    "row_count": artifact["row_count"]}, [artifact]
        return self._post_job("extract_d3plot_field", {"field": field, "states": states, "units": units,
                              "entity_ids": entity_ids, "component_indices": indices}, sources, work)

    def extract_d3plot_stress(self, path: str, element_type: str, element_ids: list[int],
                              states: list[int], integration_point: int, units: str,
                              relative_tolerance: float = 1e-12) -> dict:
        """Export shell/solid/tshell six stresses, principals, Mises, triaxiality and Lode metrics at one explicit stored integration point. No averaging/rotation."""
        import numpy as np
        if element_type not in ("shell", "solid", "tshell"):
            raise ValueError("Stress tensor extraction supports shell, solid and tshell")
        ids(element_ids, "element_ids")
        ids(states, "states", 10000)
        ids([integration_point], "integration_point")
        if len(element_ids)*len(states) > 100000:
            raise ValueError("Stress export exceeds 100000 tensors")
        sources = self._result_family(path)
        field = "element_" + element_type + "_stress"
        def work(directory):
            db, mapping = selected_database(sources[0], states, [field])
            values = np.asarray(db.arrays[field])
            if values.ndim != 4 or values.shape[-1] != 6 or integration_point > values.shape[2]:
                raise ValueError("Invalid stress tensor layout or integration point")
            lookup = {int(v): i for i, v in enumerate(result_ids(db.arrays, element_type, values.shape[1]))}
            if any(v not in lookup for v in element_ids):
                raise ValueError("Element has no stress record (absent or rigid)")
            names = list(stress_metrics([0]*6))
            undefined = 0
            def rows():
                nonlocal undefined
                for state in states:
                    for uid in element_ids:
                        metrics = stress_metrics(values[mapping[state], lookup[uid], integration_point-1], relative_tolerance)
                        undefined += not metrics["deviatoric_defined"]
                        yield [state, float(db.arrays["timesteps"][mapping[state]]), uid, integration_point,
                               *[metrics[n] for n in names]]
            artifact = write_csv(directory / "stress.csv", ["state", "time", "element_id", "integration_point", *names], rows(), NULLABLE)
            return {"backend": "lasso", "conventions": CONVENTIONS, "frame": "as_stored; invariants require consistent orthonormal tensor frame",
                    "integration_point": integration_point, "stored_integration_points": int(values.shape[2]),
                    "averaging": "none", "undefined_ratio_rows": undefined, "relative_tolerance": relative_tolerance,
                    "deletion_policy": "stored stresses retained; inspect element_is_alive separately",
                    "row_count": artifact["row_count"]}, [artifact]
        return self._post_job("extract_d3plot_stress", {"element_type": element_type, "element_ids": element_ids,
                              "states": states, "integration_point": integration_point, "units": units}, sources, work)

    def inspect_binout_variable(self, path: str, branch: str, variable: str) -> dict:
        """Inspect a nested binout variable's shape, time alignment and ID sample before extraction; single-file input."""
        import numpy as np

        from .results import open_binout
        parts = binout_tokens(branch)
        binout_tokens(variable)
        if "/" in variable or not variable:
            raise ValueError("Use a single variable name")
        source = self._binout_source(path)
        with open_binout(str(source)) as db:
            data = np.asarray(db.read(*parts, variable))
            info = {"backend": "lasso", "branch": branch, "variable": variable, "shape": list(data.shape)}
            for name in ("ids", "time"):
                try:
                    arr = np.asarray(db.read(*parts, name))
                    info[name + "_shape"] = list(arr.shape)
                    info[name + "_sample"] = arr.reshape(-1)[:50].tolist()
                except (KeyError, ValueError):
                    info[name + "_sample"] = None
            return info

    def extract_binout_table(self, path: str, branch: str, variables: list[str], units: str,
                             entity_ids: list[int] | None = None) -> dict:
        """Export multiple scalar or ID-aligned binout variables from one nested branch. No flattened-axis guessing; single-file input."""
        import numpy as np

        from .results import open_binout
        parts = binout_tokens(branch)
        if not variables or len(variables) > 100 or len(set(variables)) != len(variables):
            raise ValueError("Provide 1..100 unique variables")
        if any(not re.fullmatch(r"[A-Za-z0-9_]+", v) or v in ("time", "entity_id") for v in variables):
            raise ValueError("Invalid/reserved variable name")
        if entity_ids is not None:
            ids(entity_ids, "entity_ids")
        source = self._binout_source(path)
        def work(directory):
            with open_binout(str(source)) as db:
                times = np.asarray(db.read(*parts, "time"))
                if times.ndim != 1:
                    raise ValueError("Invalid binout time axis")
                arrays = [np.asarray(db.read(*parts, v)) for v in variables]
                expected = (len(times),)
                lookup = {}
                if entity_ids:
                    user_ids = np.asarray(db.read(*parts, "ids"))
                    if user_ids.ndim != 1 or len(set(map(int, user_ids))) != len(user_ids):
                        raise ValueError("Ambiguous binout IDs; use a more specific branch")
                    lookup = {int(v): i for i, v in enumerate(user_ids)}
                    if any(v not in lookup for v in entity_ids):
                        raise ValueError("Requested binout ID not found")
                    expected = (len(times), len(user_ids))
                if any(v.shape != expected for v in arrays):
                    raise ValueError("Variables must share explicit time/entity axes; inspect_binout_variable first")
                requested = entity_ids or [0]
                if len(times)*len(requested) > 1000000:
                    raise ValueError("Binout table exceeds one million rows")
                def rows():
                    for i, t in enumerate(times):
                        for uid in requested:
                            index = (i, lookup[uid]) if entity_ids else (i,)
                            yield [t, uid, *[v[index] for v in arrays]]
                artifact = write_csv(directory / "binout.csv", ["time", "entity_id", *variables], rows())
            return {"backend": "lasso", "row_count": artifact["row_count"], "variables": variables}, [artifact]
        return self._post_job("extract_binout_table", {"branch": branch, "variables": variables,
                              "entity_ids": entity_ids, "units": units}, [source], work)

    def extract_ascii_curve(self, path: str, time_column: int, value_column: int, units: str,
                             delimiter: str = "whitespace", skip_rows: int = 0) -> dict:
        """Read an explicit numeric ASCII/CSV curve, including Fortran D exponents. Not a parser for solver glstat/nodout/elout block files."""
        source = self.settings.input_path(path)
        def work(directory):
            rows = ascii_table(source, delimiter, skip_rows, [time_column, value_column])
            artifact = write_csv(directory / "curve.csv", ["time", "value"], rows)
            return {"backend": "numeric_ascii", "row_count": len(rows)}, [artifact]
        return self._post_job("extract_ascii_curve", {"time_column": time_column, "value_column": value_column,
                              "delimiter": delimiter, "skip_rows": skip_rows, "units": units}, [source], work)

    def process_curve(self, path: str, operation: str, units: str, time_column: int = 1,
                       value_column: int = 2, delimiter: str = "comma", skip_rows: int = 1) -> dict:
        """Differentiate (nonuniform spacing), trapezoid-integrate from zero, or summarize a numeric history curve. Requires strictly increasing finite time."""
        import numpy as np
        if operation not in ("differentiate", "integrate", "summary"):
            raise ValueError("Unsupported curve operation")
        source = self.settings.input_path(path)
        def work(directory):
            table = np.asarray(ascii_table(source, delimiter, skip_rows, [time_column, value_column]))
            t, v = table.T
            if len(t) < 2 or np.any(np.diff(t) <= 0):
                raise ValueError("Curve requires at least two strictly increasing times; split ID histories before processing")
            integral = np.concatenate(([0.0], np.cumsum(np.diff(t)*(v[:-1]+v[1:])/2)))
            summary = {"minimum": float(v.min()), "maximum": float(v.max()),
                       "time_at_minimum": float(t[v.argmin()]), "time_at_maximum": float(t[v.argmax()]),
                       "time_average": float(integral[-1]/(t[-1]-t[0])),
                       "integral": float(integral[-1]), "duration": float(t[-1]-t[0]),
                       "rms_time_weighted": math.sqrt(float(np.trapezoid(v*v, t)/(t[-1]-t[0])))}
            if not all(math.isfinite(v) for v in summary.values()):
                raise ValueError("Curve calculation overflow")
            output = np.gradient(v, t, edge_order=2 if len(t) > 2 else 1) if operation == "differentiate" else integral if operation == "integrate" else v
            artifact = write_csv(directory / "curve.csv", ["time", "value"], zip(t, output))
            return {"operation": operation, "summary": summary, "input_units": units,
                    "output_units": units + (" / time" if operation == "differentiate" else " * time" if operation == "integrate" else ""),
                    "method": "finite differences / trapezoidal quadrature; no filtering"}, [artifact]
        return self._post_job("process_curve", {"operation": operation, "units": units, "time_column": time_column,
                              "value_column": value_column, "delimiter": delimiter, "skip_rows": skip_rows}, [source], work)
