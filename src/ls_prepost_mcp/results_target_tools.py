"""M2 result-reading target tools, returning JobResult/v1 over the shared ``domain.results`` backends.

``extract_database`` (tasks.yaml Q06) reads named ASCII GLSTAT/MATSUM/NODOUT/SLEOUT/SPCFORC/RCFORC/SECFORC or a binout database (GLSTAT, MATSUM,
RCFORC, SECFORC, NODOUT, ELOUT, SLEOUT, NODFOR, SPCFORC, RBDOUT, NCFORC, DEFORC and the other
LSDA families) by its stored column name, merged across every MPP shard beside the input. The
reading and the merge rules live in :mod:`domain.results.lasso_backend` and
:mod:`domain.results.mpp_shards`; this module is a thin, recorded wrapper over them: it confines
the input path, writes a verified CSV to a job directory and returns a JobResult. Component names
are the stored column names (no UI component numbers); values stay in the model's own units and
``units`` / ``time_units`` are declarations, nothing is converted. LS-PrePost is only launched
by explicit native_check for supported ASCII force components.
"""
from __future__ import annotations

import csv
import hashlib
import re
import struct
from pathlib import Path

from pydantic import StrictBool

from .core.contracts import Artifact, JobResult
from .jobs import atomic_json, check_artifact

BACKEND = "lasso-python"
TOKEN = re.compile(r"[A-Za-z0-9_]+")
MAX_ROWS = 1_000_000
ASCII_DATABASES = frozenset(("glstat", "matsum", "nodout", "sleout", "spcforc", "rcforc", "secforc"))


def _result(status: str, data: dict, **fields: object) -> dict:
    return JobResult(operation="extract_database", status=status, backend=data.get("backend", BACKEND),
                     data=data, **fields).model_dump(mode="json")


class ResultsTargetTools:
    """Mixed into Service: needs ``self.settings`` (input confinement) and ``self.jobs`` (job dirs)."""

    def extract_database(self, path: str, database: str, component: str, units: str,
                         branch: str | None = None, shard: str | None = None,
                         entity_ids: list[int] | None = None, time_units: str = "time",
                         native_check: StrictBool = False) -> dict:
        """Q06: named binout components across MPP shards, or explicit ASCII glstat/matsum/nodout/sleout/spcforc/rcforc/secforc.

        ``path`` is one binout file (``binout`` or ``binout0000``); the other shards beside it are
        read and merged with the documented rules (united time samples where the stored entities
        match; a time present in several shards must carry identical values). ``database`` is the
        LSDA family (``rcforc``, ``secforc``, ``glstat``, ``nodout`` ...); ``branch`` selects a
        nested level (``shell``, ``velocity/nodes``); ``component`` is the stored column name, not a
        UI number. ``entity_ids`` keeps only those stored IDs. ``shard`` reads a single named file.
        The CSV holds the time column and the component under its own name; ``units`` / ``time_units``
        are declarations and nothing is converted. ASCII input must be named glstat/matsum/nodout/sleout/spcforc/rcforc/secforc and
        match database; branch/shard are not applicable. Text components: x_force/y_force/z_force,
        x_moment/y_moment/z_moment; rcforc also mass, secforc also force_magnitude/moment_magnitude,
        x_centroid/y_centroid/z_centroid/area. Written sides, legend titles and original local-frame reference tags are retained;
        no frame transform, missing-value fill or interpolation. native_check=true independently
        exports up to 16 ASCII rcforc/secforc entity/side curves for x_force/y_force/z_force in
        headless LS-PrePost and compares all times/values. Reader values are never replaced.
        ASCII GLSTAT supports kinetic_energy/internal_energy/total_energy/hourglass_energy/time_step,
        returns a global scalar without entity IDs, and maps these explicit component aliases to
        the original dotted-line labels retained in source_column_names (not binout variable claims).
        Its source SHA256 is bound before/after reading; changed inputs fail without verified output.
        ASCII MATSUM reuses the shared energy reader for internal_energy/kinetic_energy/hourglass_energy/
        eroded_internal_energy/eroded_kinetic_energy, preserving written mat.# IDs and source labels.
        It requires complete core-energy records and aligned part/time membership; missing requested
        values are unknown and fail rather than becoming zero. No binary shard or unit inference applies.
        ASCII NODOUT reads x/y/z_displacement, x/y/z_velocity and x/y/z_acceleration from their
        literal translation fields; printed node IDs and source labels are retained. Rotation tables
        are checked for complete pairs only. Curves are raw/unmasked: deletion validity is unknown.
        ASCII SLEOUT reads side_a_energy/side_b_energy/frictional_energy from the three written
        slave/master/frictional or surfa/surfb/frictional columns, retaining raw interface IDs and
        source labels. Complete summaries are syntax-checked only, without conservation arithmetic.
        Its curves are raw/unmasked with unknown deletion validity; sides are never combined.
        ASCII SPCFORC reads x/y/z_force and x/y/z_moment as printed local vectors, retaining raw
        node IDs, setid references and record kind. The local basis is unidentified; setid is not
        interpreted as a coordinate-system ID. Missing moment records fail rather than becoming zero.
        Other modes do not launch LS-PrePost; unsupported native comparisons fail explicitly."""
        selected_backend = ("ls-dyna-ascii" if isinstance(path, str) and Path(path).name.casefold() in ASCII_DATABASES
                            else BACKEND)
        try:
            if type(native_check) is not bool:
                raise ValueError("native_check must be true or false")
            parameters = self._database_parameters(database, component, units, branch, shard, entity_ids, time_units)
        except ValueError as error:
            return _result("failed", {"database": database, "component": component, "backend": selected_backend},
                           error=_error(error))
        try:
            source = self._database_source(path, parameters)
            if source.name in ASCII_DATABASES:
                selected_backend = "ls-dyna-ascii"
            if native_check:
                from .database_native import FORCE_COMPONENTS

                if source.name not in ("rcforc", "secforc") or component not in FORCE_COMPONENTS:
                    raise ValueError("native_check currently supports explicit ASCII RCFORC/SECFORC x_force/y_force/z_force only")
        except (ValueError, OSError) as error:
            return _result("failed", {"database": database, "component": component, "backend": selected_backend},
                           error=_error(error))
        directory, manifest = self.jobs.create("extract_database", {"source": str(source), **parameters,
                                                                   "native_check": native_check})
        try:
            bounded_ascii = source.name in ("glstat", "matsum", "nodout", "sleout", "spcforc")
            max_input_bytes = None
            if bounded_ascii:
                if source.name == "spcforc":
                    from .domain.results import ascii_spcforc

                    reader = ascii_spcforc
                elif source.name == "sleout":
                    from .domain.results import ascii_sleout

                    reader = ascii_sleout
                else:
                    from .domain.results import ascii_glstat, ascii_matsum, ascii_nodout

                    reader = {"glstat": ascii_glstat, "matsum": ascii_matsum, "nodout": ascii_nodout}[source.name]
                reader.validate_size(source)
                max_input_bytes = reader.MAX_BYTES
            before = _sha256(source, max_bytes=max_input_bytes) if native_check or bounded_ascii else None
            if before is not None:
                manifest["inputs"] = [{"path": str(source), "sha256": before}]
            result = self._read_database(directory, source, parameters)
            if bounded_ascii:
                if _sha256(source, max_bytes=max_input_bytes) != before:
                    raise ValueError(f"ASCII {source.name.upper()} source changed during database extraction")
                result["data"]["source_sha256"] = before
            if native_check:
                from .database_native import compare_ascii_forces

                comparison = compare_ascii_forces(self, source, result)
                if _sha256(source) != before:
                    raise ValueError("ASCII source changed during native force comparison")
                result["data"]["native_comparison"] = comparison
                result["checks"] = [{"name": "native_force_agreement", "status": "passed"},
                                    {"name": "input_bytes_unchanged", "status": "passed"}]
                result = JobResult.model_validate(result).model_dump(mode="json")
        except (ValueError, KeyError, TypeError, OSError, IndexError, EOFError, struct.error) as error:
            result = _result("failed", {"database": database, "branch": branch, "component": component,
                                        "backend": "ls-dyna-ascii" if source.name in ASCII_DATABASES
                                        else BACKEND}, job_id=manifest["job_id"], error=_error(error))
        atomic_json(directory / "job.json", {**manifest, "status": result["status"], "result": result})
        return result

    def _database_source(self, path: str, parameters: dict | None = None) -> Path:
        """Confine explicit ASCII glstat/matsum/nodout/sleout/spcforc/rcforc/secforc or a standard binout family.

        Every binary shard/continuation passes the same allowed-root check. ASCII never
        opens companions or silently substitutes a sibling binout for the requested file.
        """
        from .domain.results.mpp_shards import SHARD, lasso_reads, shards

        source = self.settings.input_path(path)
        if source.name in ASCII_DATABASES:
            if parameters is None:
                raise ValueError("ASCII result input requires explicit extract_database parameters")
            if source.name != parameters["database"]:
                raise ValueError("ASCII filename must match the requested database")
            if parameters["branch"] is not None or parameters["shard"] is not None:
                raise ValueError("ASCII result files do not accept binout branch or shard selection")
            return source
        if not SHARD.fullmatch(source.name):
            raise ValueError("extract_database reads binout files (binout or binoutNNNN); ASCII "
                             f"input is limited to glstat/matsum/nodout/sleout/spcforc/rcforc/secforc: {source.name}")
        for shard in shards(source):
            for file in lasso_reads(shard):
                self.settings.input_path(str(file))
        return source

    def _database_parameters(self, database: str, component: str, units: str, branch: str | None,
                             shard: str | None, entity_ids: list[int] | None, time_units: str) -> dict:
        from .domain.results.mpp_shards import SHARD

        if not isinstance(units, str) or not units.strip() or len(units) > 100:
            raise ValueError("Explicit unit-system label required")
        if not isinstance(time_units, str) or not time_units.strip() or len(time_units) > 100:
            raise ValueError("Explicit time-unit label required")
        if not TOKEN.fullmatch(database or ""):
            raise ValueError("database must be one LSDA family name")
        if not TOKEN.fullmatch(component or ""):
            raise ValueError("component must be one stored column name")
        if branch is not None and (not branch or any(not TOKEN.fullmatch(part) for part in branch.split("/"))):
            raise ValueError("branch must be slash-separated level names")
        if shard is not None and not SHARD.fullmatch(shard or ""):
            raise ValueError("shard must be a binout file name (binout or binoutNNNN)")
        if entity_ids is not None:
            if (not isinstance(entity_ids, list) or not entity_ids
                    or any(type(i) is not int or i < 1 for i in entity_ids)):
                raise ValueError("entity_ids must be a non-empty list of positive stored IDs")
            if len(set(entity_ids)) != len(entity_ids):
                raise ValueError("entity_ids must be unique")
        return {"database": database, "branch": branch, "component": component, "shard": shard,
                "entity_ids": entity_ids, "units": units, "time_units": time_units}

    def _read_database(self, directory: Path, source: Path, parameters: dict) -> dict:
        from .domain.results.lasso_backend import binout_curves

        if source.name == "glstat":
            from .domain.results.ascii_glstat import read

            curve = read(source, parameters["component"])
        elif source.name == "matsum":
            from .domain.results.ascii_matsum import read

            curve = read(source, parameters["component"])
        elif source.name == "nodout":
            from .domain.results.ascii_nodout import read

            curve = read(source, parameters["component"])
        elif source.name == "sleout":
            from .domain.results.ascii_sleout import read

            curve = read(source, parameters["component"])
        elif source.name == "spcforc":
            from .domain.results.ascii_spcforc import read

            curve = read(source, parameters["component"])
        elif source.name in ("rcforc", "secforc"):
            from .domain.results.ascii_forces import read

            curve = read(source, parameters["database"], parameters["component"])
        else:
            curve = binout_curves(source, parameters["database"], parameters["component"],
                                  parameters["branch"], parameters["shard"])
        times = curve["time"]
        ids = curve["ids"]
        values = curve["values"]
        if ids is not None:  # a single stored ID comes back as a flat row; keep one list per time
            values = [row if isinstance(row, list) else [row] for row in values]
        columns, headers = self._columns(ids, values, parameters["entity_ids"], parameters["component"],
                                         curve["entity_metadata"])
        if len(times) * max(1, len(columns)) > MAX_ROWS:
            raise ValueError("Curve exceeds one million rows; select entity_ids or a narrower branch")
        output = directory / "database.csv"
        row_count = 0
        with output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            if ids is None:
                for t, v in zip(times, values):
                    writer.writerow([t, v])
                    row_count += 1
            else:
                for t, row in zip(times, values):
                    for user_id, index, tag in columns:
                        writer.writerow([t, user_id, *tag, row[index]])
                        row_count += 1
        info = check_artifact(output, "csv")
        if not info.get("sha256"):  # jobs.fingerprint skips hashing over 64 MiB; a verified CSV needs one
            info = {**info, "sha256": _sha256(output)}
        artifact = Artifact(path=str(output), kind="csv", sha256=info["sha256"], size_bytes=info["size"],
                            verification="verified", metadata={"columns": headers})
        selected = None if ids is None else [user_id for user_id, _, _ in columns]
        data = {"backend": curve["backend"], "database": parameters["database"], "branch": parameters["branch"],
                "component": parameters["component"], "column_name": parameters["component"],
                "units": parameters["units"], "time_units": parameters["time_units"], "time_column": "time",
                "ids": selected, "stored_columns": None if ids is None else [index for _, index, _ in columns],
                "column_key": headers[1:-1], "entity_metadata": curve["entity_metadata"], "shards": curve["shards"],
                "repeated_times_dropped": curve["repeated_times_dropped"], "state_count": len(times),
                "entity_count": 0 if ids is None else len(columns), "row_count": row_count,
                "merge": curve.get("merge", "per-shard read; time samples united where the stored entities match")}
        if "source_format" in curve:
            data["source_format"] = curve["source_format"]
        if "source_kind" in curve:
            data["source_kind"] = curve["source_kind"]
        if "source_column_names" in curve:
            data["source_column_names"] = curve["source_column_names"]
        return _result("succeeded", data, job_id=directory.name, artifacts=(artifact,),
                       warnings=tuple(curve.get("warnings", [])),
                       scope="explicit result database in the model's own units; no conversion")

    @staticmethod
    def _columns(ids: list[int] | None, values: list, entity_ids: list[int] | None, component: str,
                 metadata: dict) -> tuple[list[tuple[int, int, tuple]], list[str]]:
        """CSV columns (stored ID, stored column index, extra key) and header.

        Stored IDs need not be unique: RCFORC writes each interface twice (``side`` 0 = secondary,
        1 = main) under one ID. Columns are therefore addressed by stored position, never by an
        ID-keyed map; repeated IDs add a ``side`` column (or the stored ``column`` index when the
        database has no side metadata) so no two CSV series share a key."""
        if ids is None:
            if entity_ids is not None:
                raise ValueError(f"{component!r} is a scalar database column; it has no entity IDs")
            if values and isinstance(values[0], list):
                raise ValueError(f"{component!r} has no stored IDs but is not a scalar time series; "
                                 "give a branch that resolves to one column")
            return [], ["time", component]
        width = len(values[0]) if values and isinstance(values[0], list) else 1
        if width != len(ids):
            raise ValueError(f"{component!r} has {width} columns but {len(ids)} stored IDs; "
                             "inspect the branch before extraction")
        stored = [int(i) for i in ids]
        side = metadata.get("side")
        if isinstance(side, list) and len(side) == len(stored) and len(set(zip(stored, side))) == len(stored):
            key, tags = ["side"], [(int(s),) for s in side]
        elif len(set(stored)) == len(stored):
            key, tags = [], [()] * len(stored)
        else:
            key, tags = ["column"], [(index,) for index in range(len(stored))]
        if entity_ids is None:
            chosen = list(range(len(stored)))
        else:
            missing = [i for i in entity_ids if i not in stored]
            if missing:
                raise ValueError(f"entity_ids not stored in this database: {missing[:10]}")
            chosen = [index for wanted in entity_ids for index, user_id in enumerate(stored) if user_id == wanted]
        return [(stored[i], i, tags[i]) for i in chosen], ["time", "entity_id", *key, component]


def _sha256(path: Path, *, max_bytes: int | None = None) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            total += len(block)
            if max_bytes is not None and total > max_bytes:
                raise ValueError("ASCII source exceeds its input-size bound while hashing")
            digest.update(block)
    return digest.hexdigest()


def _error(error: Exception) -> dict:
    return {"type": type(error).__name__, "message": str(error).strip() or type(error).__name__}
