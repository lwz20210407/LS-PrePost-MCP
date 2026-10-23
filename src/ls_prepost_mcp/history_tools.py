"""Q05 recorded wrapper; result reading, ID resolution and MPP rules stay shared."""

from __future__ import annotations

import csv
import hashlib
import re

import numpy as np

from .core.contracts import Artifact, CheckResult, CurveSpec, FileIdentity, JobResult, ModelRef
from .core.validation import unit_label
from .domain.results import lasso_backend as lb
from .jobs import atomic_json
from .post_backend import write_csv

DOMAINS = {"node", "solid", "shell", "tshell", "beam", "part", "global"}


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _sources(service, path, kind):
    if kind == "d3plot":
        source = service.settings.input_path(path)
        return source, service._result_family(str(source))
    from .domain.results.mpp_shards import lasso_reads, shards

    source = service._database_source(path)
    return source, [
        service.settings.input_path(str(f)) for shard in shards(source) for f in lasso_reads(shard)
    ]


def _binout(source, domain, quantity, ids):
    database = "matsum" if domain == "part" else "glstat"
    raw = lb.binout_curves(source, database, quantity)
    times, values = np.asarray(raw["time"]), np.asarray(raw["values"])
    provenance = {
        "note": "stored binout component; no cross-model ID association",
        "time_policy": "shared MPP merger unites/sorts time samples and collapses identical duplicate samples; no interpolation",
        "merge": {"shards": raw["shards"], "repeated_times_dropped": raw["repeated_times_dropped"]},
        "entity_scope": "stored MATSUM IDs, not inferred from another model"
        if domain == "part"
        else "global scalar",
    }
    if domain == "global":
        if raw["ids"] is not None or values.shape != times.shape:
            raise ValueError("Global history must be one scalar column without entity IDs")
        return [{"entity": None, "time": times, "values": values, **provenance}]
    stored = raw["ids"]
    if stored is None or len(set(stored)) != len(stored):
        raise ValueError("Part histories require unique stored Part IDs")
    if values.ndim == 1 and len(stored) == 1:
        values = values[:, None]
    if values.shape != (times.size, len(stored)) or not set(ids) <= set(stored):
        raise ValueError("Requested Part IDs are missing or the history entity axis is invalid")
    return [
        {"entity": uid, "time": times, "values": values[:, stored.index(uid)], **provenance} for uid in ids
    ]


def _csv_curve(service, result):
    if result.get("status") != "succeeded":
        raise ValueError((result.get("error") or {}).get("message") or "Native history export failed")
    artifact = next(a for a in result["artifacts"] if a["kind"] == "csv")
    path = service.settings.input_path(artifact["path"])
    if _sha(path) != artifact.get("sha256"):
        raise ValueError("Native history CSV identity differs from its manifest")
    with path.open(newline="", encoding="utf8") as stream:
        return list(csv.DictReader(stream))


def _native(service, source, family, source_kind, domain, quantity, records, units):
    expected = {r["entity"]: r for r in records}
    if source_kind == "binout":
        if len(family) != 1:
            raise ValueError(
                "Native history comparison supports a single binout file; no shard/continuation fallback"
            )
        errors, time_errors, jobs = [], [], []
        for record in records:
            result = service.extract_native_binout_curve(
                str(source),
                "matsum" if domain == "part" else "glstat",
                quantity,
                units,
                entity_id=record["entity"],
            )
            rows = _csv_curve(service, result)
            actual = np.asarray([[float(row["time"]), float(row["value"])] for row in rows])
            wanted = np.column_stack((record["time"], record["values"]))
            if (
                actual.shape != wanted.shape
                or not np.allclose(actual[:, 0], wanted[:, 0], rtol=1e-6, atol=1e-9)
                or not np.allclose(actual[:, 1], wanted[:, 1], rtol=2e-5, atol=1e-6)
            ):
                raise ValueError("Native/LASSO binout history disagreement")
            errors.append(float(np.max(np.abs(actual[:, 1] - wanted[:, 1]))))
            time_errors.append(float(np.max(np.abs(actual[:, 0] - wanted[:, 0]))))
            jobs.append(result["job_id"])
        return {
            "backend": "lsprepost",
            "job_ids": jobs,
            "max_absolute_error": max(errors),
            "max_time_absolute_error": max(time_errors),
            "curves": len(records),
        }
    if domain not in {"node", "solid", "shell", "tshell"}:
        raise ValueError("Native Part/global history comparison requires explicit source_kind=binout")
    if any(re.search(r"mean of (?!1\b)\d+ stored points", r.get("note", "")) for r in records):
        raise ValueError("Native history comparison cannot infer equivalence to a multiple-point mean")
    from .field_contract_adapter import NATIVE_NODE_MAP, NATIVE_STRESS_MAP

    if domain == "node":
        name, _, component = quantity.rpartition("_")
        field = NATIVE_NODE_MAP[(name, component)]
    else:
        field = NATIVE_STRESS_MAP[quantity[1:] if quantity in lb.STRESS else quantity]
    times = np.asarray(records[0]["time"])
    if times.size > 1000:
        raise ValueError("Native history comparison supports at most 1000 states")
    result = service.extract_native_fields(
        str(source), domain, list(expected), list(range(1, times.size + 1)), [field], "mid", units
    )
    rows = _csv_curve(service, result)
    seen, error = set(), 0.0
    for row in rows:
        uid, state = int(row["entity_id"]), int(row["state"])
        key = (uid, state)
        if uid not in expected or not 1 <= state <= times.size or key in seen:
            raise ValueError("Native history has unexpected/duplicate state or user ID")
        seen.add(key)
        value, time = float(row[field]), float(row["time"])
        wanted = expected[uid]["values"][state - 1]
        if (
            not np.isclose(time, times[state - 1], rtol=1e-6, atol=1e-9)
            or not np.isfinite(value)
            or not np.isclose(value, wanted, rtol=2e-5, atol=1e-6)
        ):
            raise ValueError("Native/LASSO d3plot history disagreement")
        error = max(error, abs(value - wanted))
    if len(seen) != len(expected) * times.size:
        raise ValueError("Native history omitted requested states/entities")
    return {
        "backend": "lsprepost",
        "job_ids": [result["job_id"]],
        "max_absolute_error": error,
        "curves": len(records),
    }


def extract_history(service, path, domain, quantity, ids, units, time_units, source_kind, native_check):
    units, time_units = unit_label(units), unit_label(time_units)
    if not isinstance(domain, str) or domain not in DOMAINS or source_kind not in ("d3plot", "binout"):
        raise ValueError("Unknown history domain/source_kind")
    if not isinstance(quantity, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", quantity):
        raise ValueError("quantity must be a named stored/engineering component")
    if type(native_check) is not bool:
        raise ValueError("native_check must be Boolean")
    if domain == "global":
        if ids is not None:
            raise ValueError("Global history has no entity IDs; omit entity_ids")
    elif (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 100
        or any(type(v) is not int or not 1 <= v <= 2_000_000_000 for v in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("History needs 1..100 unique positive user entity IDs")
    if source_kind == "binout" and domain not in ("part", "global"):
        raise ValueError("Binout history supports explicit Part/MATSUM or global/GLSTAT modes")
    with service._guard():
        source, family = _sources(service, path, source_kind)
        before = {str(p): _sha(p) for p in family}
        identities = tuple(
            FileIdentity(path=str(p), sha256=before[str(p)], size_bytes=p.stat().st_size) for p in family
        )
    spec = CurveSpec(
        source=ModelRef(kind=source_kind, units=units, files=identities),
        database=source_kind if source_kind == "d3plot" else ("matsum" if domain == "part" else "glstat"),
        entity_type=domain,
        entity_ids=tuple(ids or ()),
        component=quantity,
        units=units,
        time_units=time_units,
    )
    parameters = dict(
        path=str(source),
        domain=domain,
        quantity=quantity,
        entity_ids=ids,
        units=units,
        time_units=time_units,
        source_kind=source_kind,
        native_check=native_check,
    )
    directory, manifest = service.jobs.create("extract_history", parameters)
    manifest["parameters"]["curve_spec"] = spec.model_dump(mode="json")
    manifest["inputs"] = [{"path": p, "sha256": h} for p, h in before.items()]
    data, artifacts = {}, []
    try:
        with service._guard():
            records = (
                lb.history(source, domain, quantity, ids)
                if source_kind == "d3plot"
                else _binout(source, domain, quantity, ids)
            )
        if [r["entity"] for r in records] != (ids if ids is not None else [None]):
            raise ValueError("History reader omitted, reordered or duplicated requested entity IDs")
        total = 0
        for record in records:
            t, y = np.asarray(record["time"], dtype=float), np.asarray(record["values"], dtype=float)
            if (
                t.ndim != 1
                or y.shape != t.shape
                or t.size == 0
                or not np.all(np.isfinite(t))
                or not np.all(np.isfinite(y))
                or np.any(np.diff(t) < 0)
            ):
                raise ValueError("History requires finite aligned samples and nondecreasing original times")
            total += t.size
            if total > 1_000_000:
                raise ValueError("History exceeds one million total samples")
            record.update(time=t, values=y)
        comparison = (
            _native(service, source, family, source_kind, domain, quantity, records, units)
            if native_check
            else None
        )
        if comparison is not None:
            comparison["tolerances"] = {
                "time": {"rtol": 1e-6, "atol": 1e-9, "units": time_units},
                "value": {"rtol": 2e-5, "atol": 1e-6, "units": units},
            }
        summaries = []
        for record in records:
            name = (
                domain
                + "_"
                + (str(record["entity"]) if record["entity"] is not None else "global")
                + "_"
                + quantity
            )
            output = directory / (name + ".csv")
            exported = write_csv(
                output, ["time", "value"], zip(record["time"].tolist(), record["values"].tolist())
            )
            meta = {
                "domain": domain,
                "entity_id": record["entity"],
                "quantity": quantity,
                "backend": lb.backend(),
                "source_kind": source_kind,
                "units": {"time": time_units, "value": units},
                "samples": int(record["time"].size),
                "sampling": record.get("note", "as stored; no interpolation"),
                "validity": "raw stored history; no deletion filtering",
                "time_policy": record.get(
                    "time_policy", "original order and duplicate times retained; no sorting/resampling"
                ),
                "entity_scope": record.get("entity_scope", "user IDs stored in this d3plot"),
                "merge": record.get("merge"),
            }
            artifacts.append(
                Artifact(
                    path=str(output),
                    kind="csv",
                    sha256=exported["sha256"],
                    size_bytes=output.stat().st_size,
                    verification="verified",
                    metadata=meta,
                )
            )
            summaries.append(
                {
                    **meta,
                    "time_range": [float(record["time"][0]), float(record["time"][-1])],
                    "artifact": str(output),
                }
            )
        with service._guard():
            _, after_family = _sources(service, path, source_kind)
            after = {str(p): _sha(p) for p in after_family}
        if before != after or any(_sha(service.settings.input_path(a.path)) != a.sha256 for a in artifacts):
            raise ValueError("History inputs or outputs changed during extraction")
        data = dict(
            curves=summaries,
            source_kind=source_kind,
            backend=lb.backend(),
            total_samples=int(total),
            native_comparison=comparison,
            full_samples="CSV artifacts; no full arrays in MCP",
            request_contract="core.contracts.CurveSpec",
            full_request="job.parameters.curve_spec",
        )
        checks = [
            CheckResult(name=n, status="passed")
            for n in ("input_family_unchanged", "output_identity", "entities_complete")
        ]
        if native_check:
            checks.append(CheckResult(name="native_histories_agree", status="passed"))
        result = JobResult(
            operation="extract_history",
            status="succeeded",
            backend=lb.backend(),
            job_id=manifest["job_id"],
            data=data,
            artifacts=tuple(artifacts),
            checks=tuple(checks),
            scope="Stored histories; shared merge policy reported; no unit conversion or added resampling",
        )
    except Exception as error:
        result = JobResult(
            operation="extract_history",
            status="failed",
            backend=lb.backend(),
            job_id=manifest["job_id"],
            data=data,
            error={"type": type(error).__name__, "message": str(error) or type(error).__name__},
        )
    payload = result.model_dump(mode="json")
    atomic_json(directory / "job.json", {**manifest, "status": result.status, "result": payload})
    return payload
