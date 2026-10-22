"""P11 copy an existing keyword tree byte-for-byte, then reopen and verify it natively."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from .core.contracts import Artifact, CheckResult, JobResult
from .jobs import atomic_json


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _plain(value):
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    return value


def _expectations(counts, parts):
    if counts is not None and (not isinstance(counts, dict) or not counts
            or set(counts) - {"nodes", "elements"}
            or any(type(v) is not int or v < 0 for v in counts.values())):
        raise ValueError("expected_counts requires nonnegative integer nodes/elements counts")
    if parts is not None and (not isinstance(parts, list)
            or any(type(v) is not int or v <= 0 for v in parts) or len(set(parts)) != len(parts)):
        raise ValueError("expected_part_ids requires unique positive integer IDs")


def _observe(service, model, phase, data):
    native = service._native("inspect_model", {}, model=str(model))
    values = native.get("data") or {}
    if not isinstance(values, dict):
        data["differences"].append({"phase": phase, "field": "data", "reason": "invalid native observation"})
        raise ValueError(f"{phase}: native data must be an object")
    observation = {"job_id": native.get("job_id"), "status": native.get("status"),
                   "counts": values.get("counts"), "part_ids": values.get("part_ids")}
    data.setdefault("observations", {})[phase] = _plain(observation)
    if native.get("status") != "succeeded":
        diagnostic = (native.get("error") or {}).get("message") or "Native inspect did not succeed"
        raise RuntimeError(f"{phase}: {diagnostic}")
    counts = values.get("counts") or {}
    if not isinstance(counts, dict):
        data["differences"].append({"phase": phase, "field": "counts", "reason": "invalid native observation"})
        raise ValueError(f"{phase}: native counts must be an object")
    differences = [{"phase": phase, "field": key, "actual": counts.get(key), "reason": "invalid observation"}
                   for key in ("nodes", "elements") if type(counts.get(key)) is not int or counts[key] < 0]
    parts = values.get("part_ids")
    if (not isinstance(parts, list) or any(type(v) is not int or v <= 0 for v in parts)
            or len(set(parts)) != len(parts)):
        differences.append({"phase": phase, "field": "part_ids", "actual": parts, "reason": "invalid observation"})
    if differences:
        data["differences"].extend(_plain(differences))
        raise ValueError(f"{phase}: native entity observation is incomplete or invalid")
    return {"counts": {key: counts[key] for key in ("nodes", "elements")}, "part_ids": sorted(parts)}


def _compare(expected, actual, phase):
    return [{"phase": phase, "field": key, "expected": expected[key], "actual": actual[key]}
            for key in ("counts", "part_ids") if expected[key] != actual[key]]


def save_model(service, model, expected_counts=None, expected_part_ids=None):
    """Use the existing confined keyword engine; no native export that flattens Includes."""
    from .domain.model.deck import KeywordDeck

    directory, manifest, artifacts = None, None, ()
    data = {"differences": []}
    checks, warnings = [], []
    try:
        _expectations(expected_counts, expected_part_ids)
        source = service._input(model)
        with service._guard():
            service.settings.check_keyword_includes(source)
        directory, manifest = service.jobs.create("save_model", {"model": str(source),
            "expected_counts": expected_counts, "expected_part_ids": expected_part_ids})
        with service._guard():
            deck = KeywordDeck.load(source)
            paths = [f.path for f in deck.files.values()]
            identities = {str(p): _sha(p) for p in paths}
            if any(hashlib.sha256(f.original).hexdigest() != identities[str(f.path)] for f in deck.files.values()):
                raise ValueError("Input tree changed while loading the keyword snapshot")
            listings = {p.parent: sorted(f.name for f in p.parent.iterdir()) for p in paths}
            before = _observe(service, source, "before_save", data)
            expected = {"counts": {**before["counts"], **(expected_counts or {})},
                        "part_ids": before["part_ids"] if expected_part_ids is None else sorted(expected_part_ids)}
            data["expected"] = expected
            data["differences"].extend(_compare(expected, before, "before_save"))
            if data["differences"]:
                raise ValueError("Input does not match the explicit expected entity counts or Part IDs")
            # Recheck before saving: the in-memory tree must still represent the native input.
            if identities != {str(p): _sha(p) for p in paths}:
                raise ValueError("Input tree changed before save")
            saved = deck.save_as(directory / "deck")
            data.update(main=saved["main"], external_unchanged=saved["external_unchanged"],
                        saved_files=len(saved["files"]), structure="relative layout and untouched bytes preserved")
            warnings.extend(str(w) for w in saved["reload_warnings"])
            after = _observe(service, saved["main"], "after_reopen", data)
            data["differences"].extend(_compare(expected, after, "after_reopen"))
            if data["differences"]:
                raise ValueError("Saved model native reopen differs from the expected entity counts or Part IDs")
            if (identities != {str(p): _sha(p) for p in paths}
                    or any(names != sorted(f.name for f in parent.iterdir()) for parent, names in listings.items())):
                raise ValueError("Input tree files or directory listing changed during save/reopen")
            if any(_sha(item["dest"]) != item["sha256"] for item in saved["files"]):
                raise ValueError("Saved tree changed during native reopen")
            checks = [CheckResult(name=name, status="passed") for name in
                      ("input_tree_unchanged", "saved_bytes_verified", "native_reopen_counts", "native_reopen_parts")]
            artifacts = tuple(Artifact(path=item["dest"], kind="keyword", sha256=item["sha256"],
                size_bytes=Path(item["dest"]).stat().st_size, verification="verified",
                metadata={"source": item["source"], "modified": item["modified"]}) for item in saved["files"])
        if warnings:
            raise ValueError("Saved keyword tree reload produced warnings; native counts alone cannot certify it")
        result = JobResult(operation="save_model", status="succeeded", backend="keyword-engine+lsprepost",
            job_id=manifest["job_id"], data=data, checks=tuple(checks), artifacts=artifacts,
            scope="owned keyword-tree copy; automatic headless native reopen; original files unchanged")
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, RecursionError) as error:
        message = str(error)
        result = JobResult(operation="save_model", status="failed", backend="keyword-engine+lsprepost",
            job_id=manifest["job_id"] if manifest else None, data=data,
            error={"type": type(error).__name__, "message": message if message.strip() else type(error).__name__},
            warnings=tuple(warnings))
    serialized = result.model_dump(mode="json")
    if directory is not None:
        atomic_json(directory / "job.json", {**manifest, "status": result.status, "result": serialized})
    return serialized
