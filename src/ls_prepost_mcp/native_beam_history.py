"""Bounded, named DataCenter beam reference on the existing staged batch path."""

import csv
import hashlib
import json
import os
import re
from pathlib import Path

from . import native_results, runner
from .engine import environment
from .jobs import atomic_json
from .native import commands as nc
from .native import versions
from .post_backend import write_csv

IPT = "binding default; semantics not independently identified"
SCRIPT = r'''"""Owned headless beam reference: no guessed numeric field/layer selectors."""
import csv
import json
import math
import sys
import traceback
import DataCenter as dc

try:
    if sys.version_info[:2] < __MIN_ABI__:
        raise RuntimeError("Native vector ABI is unverified for this embedded Python")
    with open("beam-plan.json") as stream:
        plan = json.load(stream)
    count = dc.get_data("num_beam_elements")
    states = dc.get_data("num_states")
    if type(count) is not int or type(states) is not int:
        raise ValueError("Native model counts must be integers")
    if count != plan["beam_count"] or states != plan["state_count"]:
        raise ValueError("Native model counts differ from reader metadata")
    registry = []
    for value in dc.get_data("element_ids", type=dc.Type.BEAM):
        if isinstance(value, bool) or int(value) != value or value <= 0:
            raise ValueError("Native beam user IDs are invalid")
        registry.append(int(value))
    if len(registry) != count or len(set(registry)) != count:
        raise ValueError("Native beam user-ID registry is incomplete or ambiguous")
    # Copy the registry and times before subsequent SDK calls reuse their buffers.
    times = [float(value) for value in dc.get_data("state_times")]
    if len(times) != states or not all(math.isfinite(value) for value in times):
        raise ValueError("Native state-time registry is incomplete")
    wanted = set(plan["entity_ids"])
    indexes = {uid: n for n, uid in enumerate(registry) if uid in wanted}
    if set(indexes) != wanted:
        raise ValueError("Native beam registry lacks requested user IDs")
    rows = 0
    with open("native-beam.csv", "w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["state", "time", "entity_id", "axial_force"])
        for state in plan["states"]:
            # Omit ipt; its default semantics have not been independently identified.
            native = dc.get_data("axial_force", type=dc.Type.BEAM, ist=state)
            if len(native) != count:
                raise ValueError("Native axial_force axis differs from beam registry")
            values = [(uid, float(native[indexes[uid]])) for uid in plan["entity_ids"]]
            if not all(math.isfinite(value) for uid, value in values):
                raise ValueError("Native axial_force contains nonfinite selected values")
            writer.writerows((state, times[state-1], uid, value) for uid, value in values)
            rows += len(values)
    with open("native-beam-marker.json", "w") as stream:
        json.dump(dict(complete=True, beam_count=count, state_count=states,
            field="axial_force", entity_ids=plan["entity_ids"], requested_states=plan["states"],
            ipt="binding default; semantics not independently identified",
            python_version=list(sys.version_info[:2]), rows=rows), stream)
except Exception as exc:
    with open("native-beam-marker.json", "w") as stream:
        json.dump(dict(complete=False, error_type=type(exc).__name__,
                       error=str(exc), traceback=traceback.format_exc()), stream)
    raise
'''


def require_profile(settings):
    profile = versions.require_capability(settings.native_executable(), "batch")
    if (profile["version"] != "4.13" or profile["version_source"] != "file_version_resource"
            or profile["resource_conflict"]):
        raise ValueError("Native beam axial_force requires an unambiguous 4.13 version resource")
    return profile


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def script():
    return SCRIPT.replace("__MIN_ABI__", repr(tuple(versions.MINIMUM_VECTOR_ABI)))


def native_beam_history(settings, jobs, source, records, units, source_sha256):
    """A private reference producer, not a new public result tool or execution engine."""
    profile = require_profile(settings)
    counts = {r.get("stored_entity_count") for r in records}
    if len(counts) != 1 or any(type(n) is not int or n <= 0 for n in counts):
        raise ValueError("Beam history lacks an unambiguous stored user-ID registry count")
    entity_ids = [r["entity"] for r in records]
    state_count = len(records[0]["time"])
    if not 1 <= len(entity_ids) <= 100 or not 1 <= state_count <= 1000:
        raise ValueError("Native beam history is limited to 100 entities and 1000 states")
    plan = dict(beam_count=next(iter(counts)), state_count=state_count,
                entity_ids=entity_ids, states=list(range(1, state_count + 1)))
    expected_sources = {Path(path).name: value for path, value in source_sha256.items()}
    expected_staged = {"d3plot" + name[len(source.name):]: value
                       for name, value in expected_sources.items()}
    identity = {}

    def staged_hashes(directory):
        paths = [p for p in directory.iterdir() if re.fullmatch(r"d3plot\d*", p.name)]
        if any(p.is_symlink() or p.resolve() != p for p in paths):
            raise ValueError("Native staged result identity contains a link")
        return {p.name: sha(p) for p in paths}

    def source_hashes():
        return {p.name: sha(p) for p in native_results.input_family(settings, source, family=True)}

    def build(directory):
        atomic_json(directory / "beam-plan.json", plan)
        (directory / "beam-reference.py").write_text(script(), encoding="utf8", newline="\n")
        nc.write_cfile(directory / "commands.cfile", ["new", nc.open_model("d3plot", "d3plot", openc=True),
            nc.run_script("beam-reference.py", "python"), "exit"])

    def execute(directory, manifest):
        executable = settings.native_executable()
        config = environment.locate_config(executable, os.environ)
        if config is None:
            raise ValueError("An initialized LS-PrePost configuration is required")
        identity.update(binary_sha256=sha(executable), configuration_sha256=sha(config), profile=profile)
        listing = sorted(p.name for p in source.parent.iterdir())
        checks, primary = {}, None
        try:
            if staged_hashes(directory) != expected_staged:
                raise ValueError("Native staged family identity differs from reader inputs")
            execution = runner.run_batch(executable, directory / "commands.cfile", directory,
                timeout=settings.timeout, graphics=False, operation=manifest["action"])
            runner.record_batch_result(execution, manifest, directory)
        except Exception as error:
            primary = error
        finally:
            guards = dict(
                input_family_unchanged=lambda: source_hashes() == expected_sources,
                staged_family_unchanged=lambda: staged_hashes(directory) == expected_staged,
                source_directory_unchanged=lambda: sorted(p.name for p in source.parent.iterdir()) == listing,
                binary_unchanged=lambda: sha(executable) == identity["binary_sha256"],
                configuration_unchanged=lambda: sha(config) == identity["configuration_sha256"],
            )
            for name, check in guards.items():
                try:
                    checks[name] = bool(check())
                except Exception:
                    checks[name] = False
            manifest.update(native_identity=identity, native_identity_checks=checks)
        if not all(checks.values()):
            message = "Native identity guard failed: " + ", ".join(k for k, v in checks.items() if not v)
            if primary is not None:
                message = str(primary) + "; " + message
            raise ValueError(message) from primary
        if primary is not None:
            raise primary

    def parse(directory):
        marker_path = directory / "native-beam-marker.json"
        if marker_path.stat().st_size > 64 * 1024:
            raise ValueError("Native beam marker exceeds 64 KiB")
        marker = json.loads(marker_path.read_text(encoding="utf8"))
        expected_rows = len(entity_ids) * state_count
        expected = dict(complete=True, beam_count=plan["beam_count"], state_count=state_count,
                        field="axial_force", entity_ids=entity_ids, requested_states=plan["states"],
                        ipt=IPT, rows=expected_rows)
        if (not isinstance(marker, dict) or any(marker.get(k) != v for k, v in expected.items())
                or any(type(marker.get(k)) is not int for k in ("beam_count", "state_count", "rows"))
                or marker.get("complete") is not True):
            raise ValueError("Native beam completion marker differs from the request")
        abi = marker.get("python_version")
        if not isinstance(abi, list) or len(abi) != 2 or any(type(n) is not int for n in abi):
            raise ValueError("Native beam marker lacks its embedded Python ABI")
        versions.require_vector_abi(abi)
        columns = ["state", "time", "entity_id", "axial_force"]
        rows = []
        with (directory / "native-beam.csv").open(encoding="utf8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != columns:
                raise ValueError("Native beam CSV schema differs from the request")
            for row in reader:
                if len(rows) >= expected_rows or None in row or any(row.get(k) is None for k in columns):
                    raise ValueError("Native beam CSV contains extra or malformed rows")
                rows.append([row[k] for k in columns])
        if len(rows) != expected_rows:
            raise ValueError("Native beam CSV omitted requested samples")
        artifact = write_csv(directory / "results.csv", columns, rows)
        data = dict(backend="lsprepost", native_channel="embedded_python", field="axial_force",
                    row_count=expected_rows, ipt=IPT, coordinate_frame="as stored", native_identity=identity,
                    read_only="Only staged copies were opened", native_marker=marker)
        return data, [artifact]

    return native_results.finish_native(settings, jobs, "extract_native_beam_history",
        dict(units=units, **plan, ipt=IPT), source, build, parse, family=True,
        channel="embedded_python", executor=execute)
