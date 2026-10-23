"""Q03 six-component wrapper over shared LASSO field, validity math and exports."""
from __future__ import annotations

import csv
import hashlib

import numpy as np

from .core.contracts import Artifact, CheckResult, JobResult
from .domain.results import export as exp
from .domain.results import invariants as inv
from .domain.results import lasso_backend as lb
from .jobs import atomic_json


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _native_agreement(service, source, raw, selector):
    if raw["sampling"]["kind"] != "stored_point" and raw["sampling"]["count"] != 1:
        raise ValueError("Native comparison of stored-point means needs exactly one stored point; no shell layer equivalence is inferred")
    ids = [int(v) for v in raw["ids"]]
    if not 1 <= len(ids) <= 1000:
        raise ValueError("Native field comparison requires 1..1000 explicitly returned entities")
    fields = ["stress_x", "stress_y", "stress_z", "stress_xy", "stress_yz", "stress_zx"]
    native = service.extract_native_fields(str(source), raw["family"], ids, [raw["state"]], fields, selector, raw["units"])
    if native.get("status") != "succeeded":
        raise ValueError((native.get("error") or {}).get("message") or "Native field export failed")
    artifact = next(a for a in native["artifacts"] if a["kind"] == "csv")
    path = service.settings.input_path(artifact["path"])
    if _sha(path) != artifact.get("sha256"):
        raise ValueError("Native comparison CSV identity differs from its manifest")
    with path.open(encoding="utf8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    observed = {int(r["entity_id"]): r for r in rows}
    if len(observed) != len(rows) or set(observed) != set(ids):
        raise ValueError("Native comparison must contain exactly the requested user IDs")
    values = []
    for uid in ids:
        row = observed[uid]
        if int(row["state"]) != raw["state"] or not np.isclose(float(row["time"]), raw["time"], rtol=1e-6, atol=1e-9):
            raise ValueError("Native comparison state/time differs from reader selection")
        values.append([float(row[k]) for k in fields])
    values = np.asarray(values)
    if not np.all(np.isfinite(values)) or not np.allclose(values, raw["values"], rtol=2e-5, atol=1e-6):
        raise ValueError("Native/LASSO six-component stress disagreement; check sampling and frame")
    return {"backend": "lsprepost", "job_id": native["job_id"], "entities": len(ids),
            "components": list(lb.STRESS), "rtol": 2e-5, "atol": 1e-6,
            "max_absolute_error": float(np.max(np.abs(values - raw["values"]))),
            "native_selector": selector, "reader_sampling": raw["sampling"],
            "sampling": "numerical agreement for this explicit selection; no general shell layer remapping"}


def tensor_field(service, path, family, state, mask, units, output_format, parts, native_check, stored_point, native_sampling):
    if not isinstance(units, str) or not units.strip() or len(units) > 100:
        raise ValueError("Six-component stress extraction requires explicit units (up to 100 characters)")
    if native_check:
        from .field_contracts import SamplingSpec

        SamplingSpec.native_fields(family, native_sampling, ["stress_x"])
    elif native_sampling != "mid":
        raise ValueError("native_sampling requires native_check=true")
    source = service.settings.input_path(path)
    with service._guard():
        sources = service._result_family(str(source))
        before = {str(p): _sha(p) for p in sources}
    parameters = dict(path=str(source), family=family, quantity="stress", state=state, mask=mask,
                      units=units, output_format=output_format, part_ids=parts, native_check=native_check,
                      stored_point=stored_point, native_sampling=native_sampling)
    directory, manifest = service.jobs.create("extract_field", parameters)
    manifest["inputs"] = [{"path": path, "sha256": sha} for path, sha in before.items()]
    artifacts, checks, data = [], [], {}
    try:
        with service._guard():
            raw = lb.field(source, family, "stress", state=-1 if state == -1 else state-1, mask=mask,
                           part_ids=parts, stored_point=stored_point)
        ids = np.asarray(raw["ids"])
        values, alive = np.asarray(raw["values"], dtype=float), np.asarray(raw["alive"], dtype=bool)
        if (ids.ndim != 1 or ids.dtype.kind not in "iu" or len(set(map(int, ids))) != ids.size
                or np.any(ids <= 0) or values.shape != (ids.size, 6) or alive.shape != ids.shape):
            raise ValueError("Stress entity axes must contain aligned unique positive user IDs")
        if ids.size > 1_000_000:
            raise ValueError("Tensor export exceeds one million entities")
        keep = inv.masked(alive, mask)
        if not np.all(np.isfinite(values[keep])):
            raise ValueError("Nonfinite stress component in returned entities")
        raw = {**raw, "ids": ids[keep], "values": values[keep], "alive": alive[keep],
               "state": int(raw["state"])+1, "state_index_base": 1, "units": units,
               "coordinate_system": "as stored; no coordinate transformation or inferred global/material frame"}
        raw["extrema"] = {key: inv.extrema(raw["values"][:,i], raw["ids"], np.ones(keep.sum(), bool))
                          for i,key in enumerate(lb.STRESS)}
        raw["mask_policy"] = {"mode": mask, "rule": inv.MASKS[mask], "elements": int(ids.size),
                              "rows": int(keep.sum()), "excluded": int((~keep).sum()),
                              "deletion_status": "stored" if raw["deletion_data"] else "unknown"}
        data = {k: raw[k] for k in ("backend", "family", "quantity", "components", "state", "time",
                                    "units", "sampling", "mask_policy", "extrema", "part_ids", "note")}
        data.update(shape=list(raw["values"].shape), row_count=int(keep.sum()), state_index_base=1,
                    coordinate_system=raw["coordinate_system"],
                    active_count=int(raw["alive"].sum()) if raw["deletion_data"] else None,
                    preview={"ids": raw["ids"][:20].tolist(), "values": raw["values"][:20].tolist()},
                    preview_truncated=int(keep.sum()) > 20, full_data="CSV/NPZ artifacts; no full tensor array in MCP")
        if native_check:
            data["native_comparison"] = _native_agreement(service, source, raw, native_sampling)
            checks.append(CheckResult(name="native_components_agree", status="passed"))
        formats = ("csv", "npz") if output_format in ("both", "all") else (() if output_format == "none" else (output_format,))
        for fmt in formats:
            output = directory / ("stress." + fmt)
            exported = exp.export_field(raw, output, units=units, fmt=fmt)
            back = exp.read_field(output)
            if not (np.array_equal(back["ids"], raw["ids"]) and np.array_equal(back["values"], raw["values"])
                    and np.array_equal(back["alive"], raw["alive"])):
                raise ValueError("Tensor export round trip changed entity IDs, values or validity")
            artifacts.append(Artifact(path=str(output), kind=fmt, sha256=exported["sha256"],
                                      size_bytes=output.stat().st_size, verification="verified", metadata=exported["meta"]))
        with service._guard():
            after = {str(p): _sha(p) for p in service._result_family(str(source))}
        if before != after:
            raise ValueError("Input result family changed during tensor extraction")
        checks.extend(CheckResult(name=name, status="passed") for name in ("input_family_unchanged", "mask_applied"))
        result = JobResult(operation="extract_field", status="succeeded", backend=lb.backend(),
                           job_id=manifest["job_id"], data=data, checks=tuple(checks), artifacts=tuple(artifacts),
                           scope="Six stored stress components; mean of stored points; no coordinate transform")
    except Exception as error:
        result = JobResult(operation="extract_field", status="failed", backend=lb.backend(),
                           job_id=manifest["job_id"], data=data,
                           error={"type": type(error).__name__, "message": str(error) or type(error).__name__})
    payload = result.model_dump(mode="json")
    atomic_json(directory / "job.json", {**manifest, "status": result.status, "result": payload})
    return payload
