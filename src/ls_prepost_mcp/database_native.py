"""Q06 independent native check of named ASCII force curves; no alternate force parser."""

import csv
import hashlib
from collections import defaultdict

import numpy as np

FORCE_COMPONENTS = {"x_force": 1, "y_force": 2, "z_force": 3}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def compare_ascii_forces(service, source, result):
    data = result["data"]
    database = data["database"]
    if (
        source.name not in ("rcforc", "secforc")
        or database != source.name
        or data["component"] not in FORCE_COMPONENTS
    ):
        raise ValueError(
            "native_check currently supports explicit ASCII RCFORC/SECFORC x_force/y_force/z_force only"
        )
    artifact = result["artifacts"][0]
    path = service.settings.input_path(artifact["path"])
    if sha(path) != artifact["sha256"]:
        raise ValueError("Reader curve identity changed before native comparison")
    groups = defaultdict(list)
    with path.open(encoding="utf8", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (int(row["entity_id"]), int(row["side"]) if database == "rcforc" else None)
            groups[key].append((float(row["time"]), float(row[data["component"]])))
    if not 1 <= len(groups) <= 16:
        raise ValueError(
            "Native force comparison requires 1..16 explicit entity/side curves; select entity_ids"
        )
    comparisons = []
    for (uid, side), rows in groups.items():
        expected = np.asarray(rows, dtype=float)
        native = service.extract_native_ascii_curve(
            str(source),
            database,
            FORCE_COMPONENTS[data["component"]],
            data["units"],
            entity_id=uid,
            side=side,
        )
        if native.get("status") != "succeeded":
            raise ValueError((native.get("error") or {}).get("message") or "Native force curve export failed")
        if native.get("data", {}).get("entity_id") != uid:
            raise ValueError("Native force response belongs to another user ID")
        if database == "rcforc" and native.get("data", {}).get("side") != side:
            raise ValueError("Native force response belongs to another contact side")
        csv_artifact = next((a for a in native["artifacts"] if a["kind"] == "csv"), None)
        if csv_artifact is None:
            raise ValueError("Native force export returned no CSV artifact")
        output = service.settings.input_path(csv_artifact["path"])
        if sha(output) != csv_artifact.get("sha256"):
            raise ValueError("Native force curve identity differs from its manifest")
        with output.open(newline="", encoding="utf8") as stream:
            observed = np.asarray(
                [(float(r["time"]), float(r["value"])) for r in csv.DictReader(stream)], dtype=float
            )
        if sha(output) != csv_artifact.get("sha256"):
            raise ValueError("Native force CSV changed while reading")
        if (
            observed.shape != expected.shape
            or not np.isfinite(observed).all()
            or not np.isfinite(expected).all()
        ):
            raise ValueError("Native force curve shape/nonfinite values disagree with reader output")
        if not np.allclose(observed[:, 0], expected[:, 0], rtol=1e-6, atol=0.0):
            raise ValueError(
                "Native force curve time axis differs; no interpolation or alignment was applied"
            )
        value_atol = 1e-6 * float(np.max(np.abs(expected[:, 1])))
        if not np.allclose(observed[:, 1], expected[:, 1], rtol=2e-5, atol=value_atol):
            raise ValueError("Native force values disagree with reader output; no replacement was applied")
        comparisons.append(
            dict(
                entity_id=uid,
                side=side,
                native_job_id=native["job_id"],
                samples=len(rows),
                value_atol=value_atol,
                max_time_absolute_error=float(np.abs(observed[:, 0] - expected[:, 0]).max()),
                max_value_absolute_error=float(np.abs(observed[:, 1] - expected[:, 1]).max()),
            )
        )
    if sha(path) != artifact["sha256"]:
        raise ValueError("Reader curve changed during native comparison")
    return dict(
        backend="lsprepost",
        component=data["component"],
        curves=comparisons,
        tolerances=dict(time=dict(rtol=1e-6, atol=0.0, reference="reader time; no time-unit floor"),
                        value=dict(rtol=2e-5, atol_rule="1e-6 * max(abs(reader curve)); zero curve has zero atol",
                                   atol_by_curve=[dict(entity_id=c["entity_id"], side=c["side"], atol=c["value_atol"]) for c in comparisons])),
        scope="Same source component, entity ID and written side; no coordinate/unit transform or native backfill",
    )
