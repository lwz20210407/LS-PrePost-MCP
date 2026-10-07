"""Offline installation adapters. Vendor parsing and execution stay in InstallationTools."""

import os
import re
import warnings
from pathlib import Path

from ..core.contracts import Artifact
from ..installation_assets import asset, catalog, evaluate_parameters
from ..jobs import atomic_json, check_artifact, fingerprint
from ..knowledge_index import terms
from ..outcomes import normalize_outcome

REFERENCE = re.compile(r"installed:((?:template|filter)-[a-f0-9]{16})(?:@([a-f0-9]{64}))?")


def _identities(record):
    path = Path(record["path"])
    sources = [fingerprint(path)]
    if sources[0]["sha256"] is None:
        raise ValueError("Installation adapter requires a source SHA256 (maximum 64 MiB)")
    if record["kind"] == "template":
        info = path.parent / "info.txt"
        if info.is_symlink() and not info.resolve().is_relative_to(path.parent):
            raise ValueError("Installation usage file escaped its resource directory")
        if info.exists():
            if not info.resolve().is_relative_to(path.parent):
                raise ValueError("Installation usage file escaped its resource directory")
            sources.append(fingerprint(info))
    return sources


def _check_sources(service, record, sources):
    current, _ = asset(service.settings, record["id"], record["kind"])
    if current != record or _identities(current) != sources:
        raise ValueError("Installation resource changed during recipe execution")


def _schema(description):
    properties = {}
    for item in description["parameters"]:
        entry = dict(type={"R": "number", "I": "number", "S": "string"}[item["type"]],
                     default=description["defaults"][item["name"]],
                     description=item["label"], expression=item["expression"])
        if item["type"] == "I":
            entry["multipleOf"] = 1
        if item["type"] == "S":
            entry.update(maxLength=70, pattern=r"^[^\r\n\u0000]*$")
        properties[item["name"]] = entry
    return dict(type="object", additionalProperties=False, required=["units"], properties=dict(
        values=dict(type="object", additionalProperties=False, properties=properties, default={}),
        units=dict(type="string", minLength=1, maxLength=100, pattern=r"\S"),
        native_check=dict(type="boolean", default=False),
    ))


def _describe(service, record):
    sources = _identities(record)
    description = None
    if record["kind"] == "template":
        description = service.describe_installed_template(record["id"])
        if description["source"] != sources[0]:
            raise ValueError("Installation resource changed while describing parameters")
        # These are the same artifact boundary required by instantiate_installed_template.
        if not {"*KEYWORD", "*END"} <= set(description["keywords"]):
            raise ValueError("Template cannot produce the required KEYWORD/END artifact")
    else:
        Path(record["path"]).read_text(encoding="utf-8-sig")
    _check_sources(service, record, sources)
    return sources, description


def candidates(service, wanted, task_id, channel):
    """Enumerate the actual catalog, including explicit unsupported rows, without launching native code."""
    if task_id and task_id != "A08" or channel:
        return []  # Installation operations are not any of the native language channels.
    if not os.environ.get("LSPP_TEMPLATE_ROOT") and service.settings.executable is None:
        warnings.warn("Installation recipe source is not configured (LSPP_TEMPLATE_ROOT or executable)",
                      RuntimeWarning, stacklevel=2)
        return []
    try:
        records = catalog(service.settings)
    except (OSError, ValueError) as exc:
        warnings.warn("Installation recipe source unavailable: " + str(exc), RuntimeWarning, stacklevel=2)
        return []
    if not records:
        warnings.warn("Installation recipe source contains no supported catalog paths", RuntimeWarning, stacklevel=2)
    hits = []
    for record in records:
        kind = record["kind"]
        text = " ".join((record["name"], record["relative_path"], kind, "installed installation keyword A08",
                         "安装 模板 配方" if kind == "template" else "安装 过滤器 关键字选择"))
        score = len(wanted & set(terms(text)))
        if wanted and not score:
            continue
        row = dict(id="installed:" + record["id"], name=record["name"], task_id="A08", channel=None,
                   reference="installed:" + record["id"], resource=record, origin="installation",
                   adapter_kind="installed_" + kind, tier="candidate", versions_verified=[], l2_case=None,
                   contexts=["offline", "explicit_batch_reopen"] if kind == "template" else ["offline"],
                   outputs=["model.k", "parameters.json"] if kind == "template" else ["filter-result.json"],
                   support="unsupported", reason=None)
        try:
            sources, description = _describe(service, record)
            row.update(reference=row["reference"] + "@" + sources[0]["sha256"], sources=sources,
                       parameters=_schema(description) if description else
                       dict(type="object", properties={}, additionalProperties=False),
                       support="offline_adapter", validation_scope="L1 contract only; native versions unverified")
            if description:
                row["template_contract"] = description
        except (OSError, ValueError, SyntaxError, ArithmeticError) as exc:
            row["reason"] = f"{type(exc).__name__}: {exc}"
        hits.append((score, row))
    return hits


def run(service, reference, parameters, model, file_type, session_id, launch_mode):
    """Reuse installation operations; reject unsupported contexts before creating any jobs."""
    from .recipes import validate_parameters

    if session_id is not None or launch_mode != "c" or file_type != "keyword":
        raise ValueError("Installed recipes require keyword input, no session, and launch_mode='c'")
    match = REFERENCE.fullmatch(reference)
    if not match:
        raise ValueError("Invalid installed recipe reference")
    record, path = asset(service.settings, match[1])
    sources, description = _describe(service, record)
    if match[2] is not None and match[2] != sources[0]["sha256"]:
        raise ValueError("Installation resource changed since discovery; find_recipe again")
    if parameters is not None and not isinstance(parameters, dict):
        raise ValueError("Installed recipe parameters must be an object")
    requested = dict(parameters or {})
    if description:
        values = requested.get("values", {})
        if not isinstance(values, dict) or any(not isinstance(key, str) for key in values):
            raise ValueError("Template values must be an object with string keys")
        normalized = {key.upper(): value for key, value in values.items()}
        if len(normalized) != len(values):
            raise ValueError("Duplicate case-insensitive template parameters")
        requested["values"] = normalized
        requested = validate_parameters(_schema(description), requested)
        # Evaluate expressions with only explicit overrides, never inject evaluated defaults.
        actual = evaluate_parameters(description["parameters"], requested["values"])
    else:
        requested = validate_parameters(dict(type="object", properties={}, additionalProperties=False), requested)
        if model is None:
            raise ValueError("Installed filter requires an explicit keyword model")
        actual = {}
    if model is not None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Installed recipe model must be an explicit keyword path")
        source = service.settings.input_path(model)
        sources.append(fingerprint(source))
    else:
        source = None
    installation_sources = sources[:-1] if source is not None else sources
    _check_sources(service, record, installation_sources)
    if description:
        raw = service.instantiate_installed_template(record["id"], requested["values"], requested["units"],
                                                     model=model, native_check=requested["native_check"])
    else:
        def work(directory):
            selected = service.apply_keyword_filter(model, record["id"])
            if selected["source"] != sources[-1]:
                raise ValueError("Keyword model changed during filter selection")
            selected.update(filter_source=sources[0], solver_validated=False, native_mesh_verified=False,
                            verification_scope="Keyword-category selection only; no model modification or native execution")
            output = directory / "filter-result.json"
            atomic_json(output, selected)
            return selected, [check_artifact(output, "json")]

        raw = service._post_job("run_recipe", dict(filter_id=record["id"], model=model, units="dimensionless"),
                                [path, source], work)
    try:
        _check_sources(service, record, installation_sources)
        if source is not None and fingerprint(source) != sources[-1]:
            raise ValueError("Keyword model changed during recipe execution")
        expected_inputs = [sources[0]] + ([sources[-1]] if source is not None else [])
        if raw.get("inputs") != expected_inputs:
            raise ValueError("Recipe inputs changed before installation job capture")
        if description and raw["status"] == "succeeded" and (
            raw["data"]["source_hash"] != sources[0] or raw["data"]["parameters"] != actual
        ):
            raise ValueError("Template execution differs from the validated recipe contract")
        if description and raw["status"] == "succeeded":
            raw["artifacts"].append(check_artifact(Path(raw["job_directory"]) / "parameters.json", "json"))
    except (OSError, ValueError) as exc:
        raw.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
        raw.setdefault("data", {})["native_mesh_verified"] = False
    data = raw.setdefault("data", {})
    data.update(inputs=sources, backend="installation_adapter", recipe=dict(
        reference=reference, resource=record, origin="installation", tier="candidate",
        adapter_kind="installed_" + record["kind"], source=sources[0], parameters=requested,
        actual_values=actual, native_check_requested=requested.get("native_check", False),
        versions_verified=[], l2_case=None,
    ))
    data.setdefault("solver_validated", False)
    data.setdefault("native_mesh_verified", False)
    data.setdefault("verification_scope", "Installation adapter contract; failed jobs certify no generated model")
    data["native_reopen"] = ("verified" if data["native_mesh_verified"] else
                             "not_requested" if not requested.get("native_check") else
                             "not_applicable_fragment" if "native_check_note" in data else "unverified")
    directory = Path(raw["job_directory"])
    atomic_json(directory / "job.json", raw)
    outcome = normalize_outcome("run_recipe", raw)
    identity = fingerprint(directory / "job.json")
    outcome = outcome.model_copy(update={"evidence": (Artifact(
        path=identity["path"], kind="json", sha256=identity["sha256"], size_bytes=identity["size"],
        verification="verified"),)})
    result = outcome.model_dump(mode="json", exclude={"comparison_data"})
    atomic_json(directory / "recipe-result.json", result)
    return result
