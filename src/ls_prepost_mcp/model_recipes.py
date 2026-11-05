"""P03 host keyword recipes: frozen contracts, existing atomic AST operations.

These L1 candidates are not embedded Python/native programs.  No physical
default or unit conversion is supplied by this registry.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import math
import re
from pathlib import Path

from .core.contracts import JobResult
from .core.validation import unit_label
from .domain.model import access
from .domain.model.materials import EOS, MATERIALS, SECTIONS
from .jobs import atomic_json

PACKAGE = Path(__file__).resolve().parent
MANIFEST_RELATIVE = "src/ls_prepost_mcp/data/model_recipes.json"
REFERENCE = re.compile(r"model:[a-z][a-z0-9_-]{0,79}")
VERSIONED_REFERENCE = re.compile(r"(model:[a-z][a-z0-9_-]{0,79})(?:@([a-f0-9]{64}))?")
MAX_BYTES = 1024 * 1024
FAMILIES = {"material": MATERIALS, "eos": EOS, "section": SECTIONS}
ID_FIELDS = {"material": "mid", "eos": "eosid", "section": "secid"}
JSON_TYPES = {"int": "integer", "float": "number", "str": "string"}
SCOPE = "Host keyword AST creation/reference checks only; no unit conversion, native Part Data readback or physical calibration verification"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _source(path, locator):
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Model recipe provider source exceeds 1 MiB")
    return dict(locator=locator, sha256=_sha(raw), sha256_lf=_sha(raw.replace(b"\r\n", b"\n")), bytes=len(raw))


def load_registry(repository=None):
    """Read a bounded bundled registry; metadata discovery needs no optional SDK."""
    package = Path(repository) / "src/ls_prepost_mcp" if repository is not None else PACKAGE
    path = package / "data/model_recipes.json"
    guard = access.root_guard((package,))
    guard(path)
    before = path.stat()
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    after = path.stat()
    if len(raw) > MAX_BYTES or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Model recipe registry exceeds 1 MiB or changed while being read")
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise ValueError("Unsupported model recipe registry schema")
    types = payload["parameter_types"]
    provider = payload["provider_metadata"]
    if not isinstance(types, dict) or not isinstance(payload["recipes"], list) or not isinstance(provider, dict):
        raise ValueError("Model recipe registry has invalid containers")
    if provider.get("license") != "MIT" or provider.get("private_manual_used") is not False:
        raise ValueError("Model recipe field snapshot must use public permitted provider metadata")
    if provider.get("package") != "ansys-dyna-core" or not isinstance(provider.get("version"), str) or not provider["version"]:
        raise ValueError("Model recipe field snapshot must identify its schema provider")
    for family, group in types.items():
        if family not in FAMILIES or not isinstance(group, dict):
            raise ValueError("Unknown model recipe field family")
        for name, fields in group.items():
            if name not in FAMILIES[family] or not isinstance(fields, dict):
                raise ValueError("Unknown underlying model recipe")
            _, required, optional = FAMILIES[family][name]
            if set(fields) != set(required + optional) or any(not isinstance(kind, str) or kind not in JSON_TYPES for kind in fields.values()):
                raise ValueError("Model recipe field snapshot drifted from its existing core contract")
    found = {}
    for row in payload["recipes"]:
        if (not isinstance(row, dict) or not all(isinstance(row.get(key), str) and row[key].strip()
                                               for key in ("id", "name", "description", "family"))
                or not isinstance(row.get("tags"), list) or not all(isinstance(tag, str) for tag in row["tags"])):
            raise ValueError("Model recipe metadata must use explicit text fields and tags")
        ident, family = row.get("id"), row.get("family")
        if not isinstance(ident, str) or REFERENCE.fullmatch(ident) is None or ident in found:
            raise ValueError("Invalid or duplicate host model recipe reference")
        if family in ("material", "eos"):
            name = row["core_recipe"]
            if name not in types[family] or row["keyword"] != FAMILIES[family][name][0]:
                raise ValueError("Host model recipe keyword differs from its core contract")
        elif family == "assembly":
            if row.get("components") != dict(material="johnson_cook", eos="gruneisen", section="solid"):
                raise ValueError("Unregistered host model assembly")
        else:
            raise ValueError("Unregistered host model recipe family")
        found[ident] = copy.deepcopy(row)
    identity = dict(definition=dict(locator="repo://" + MANIFEST_RELATIVE, sha256=_sha(raw),
                                    sha256_lf=_sha(raw.replace(b"\r\n", b"\n")), bytes=len(raw)),
                    provider=_source(Path(__file__), "repo://src/ls_prepost_mcp/model_recipes.py"),
                    field_contract=_source(PACKAGE / "domain/model/materials.py", "repo://src/ls_prepost_mcp/domain/model/materials.py"),
                    parameter_validation=_source(PACKAGE / "automation/recipes.py", "repo://src/ls_prepost_mcp/automation/recipes.py"),
                    unit_validation=_source(PACKAGE / "core/validation.py", "repo://src/ls_prepost_mcp/core/validation.py"))
    return found, types, payload["provider_metadata"], identity


def _object(properties, required):
    return dict(type="object", additionalProperties=False, properties=properties, required=list(required))


def _text(maximum=70):
    return dict(type="string", minLength=1, maxLength=maximum, pattern=r"^[^\r\n\u0000]*$")


def _id():
    return dict(type="integer", minimum=1, maximum=2_000_000_000,
                description="Strict integer identity; Boolean, string and float inputs are not coerced")


def _field_schema(types, family, name):
    _, required, optional = FAMILIES[family][name]
    properties = {}
    for field in required + optional:
        kind = types[family][name][field]
        properties[field] = _text() if kind == "str" else dict(type=JSON_TYPES[kind])
    result = _object(properties, required)
    if family == "material" and name == "piecewise_linear_plasticity":
        result["description"] = "The existing keyword engine also requires SIGY or an existing LCSS curve; final reference/semantic checks remain in that engine."
    elif family == "eos" and name == "linear_polynomial":
        result["description"] = "The existing keyword engine requires at least one non-zero C0..C6; no coefficient is supplied by this registry."
    return result


def parameter_schema(row, types):
    properties = dict(units=dict(type="string", minLength=1, maxLength=100, pattern=r"\S",
                                description="Caller-declared unit system; no unit inference or conversion"))
    if row["family"] in ("material", "eos"):
        family = row["family"]
        ident = ID_FIELDS[family]
        properties.update({ident: _id(), "params": _field_schema(types, family, row["core_recipe"]), "title": _text()})
        return _object(properties, ("units", ident, "params"))
    properties.update({name: _id() for name in ("mid", "eosid", "secid", "pid")})
    properties.update(part_action=dict(type="string", enum=["add", "set"]), part_title=_text())
    for family, name in row["components"].items():
        properties[family] = _field_schema(types, family, name)
    result = _object(properties, ("units", "mid", "eosid", "secid", "pid", "part_action", "material", "eos", "section"))
    result["allOf"] = [{"if": {"properties": {"part_action": {"const": "add"}}, "required": ["part_action"]},
                        "then": {"required": ["part_title"]}, "else": {"not": {"required": ["part_title"]}}}]
    return result


def pinned_reference(row, schema, provider, identity):
    """Content-version one selected contract; normalize source line endings only."""
    contract = dict(recipe=row, parameters=schema, provider_snapshot=provider,
                    source_versions={key: value["sha256_lf"] for key, value in identity.items()})
    version = _sha(json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf8"))
    return row["id"] + "@" + version


def describe(row, types, provider, identity):
    schema = parameter_schema(row, types)
    return dict(schema_version=1, id=row["id"], reference=pinned_reference(row, schema, provider, identity),
                reference_policy="pinned", name=row["name"], description=row["description"],
                task_id="P03", channel="keyword", backend="keyword", tier="candidate", verification_level="L1",
                parameters=schema, tags=row["tags"], input_kind="keyword", contexts=["host"],
                versions_verified=[], l2_case=None, native_executed=False, requires_model=True, scope=SCOPE,
                requirements=dict(optional_extra="pydyna", package="ansys-dyna-core", field_schema_snapshot_version=provider["version"]),
                provider_snapshot=provider, source=identity,
                execution_modes=dict(host_keyword=dict(status="verified_offline", evidence="P03 host AST tests; no native Part Data readback")))


def candidates(wanted, task_id, channel):
    if task_id and task_id != "P03" or channel and channel != "keyword":
        return []
    from .knowledge_index import terms

    rows, types, provider, identity = load_registry()
    hits = []
    for row in rows.values():
        score = len(wanted & set(terms(" ".join((row["id"], row["name"], row["description"], *row["tags"])))))
        if not wanted or score:
            hits.append((score, describe(row, types, provider, identity)))
    return hits


def _provider_check(row, types, provider):
    """Confirm the snapshot against the existing public schema provider, not a parser."""
    from .domain.model.keyword_docs import _cards
    from .domain.model.schema import _pydyna_class

    try:
        version = importlib.metadata.version(provider["package"])
    except importlib.metadata.PackageNotFoundError as error:
        raise ValueError("Host model recipe requires the project's pydyna extra") from error
    if version != provider["version"]:
        raise ValueError("Host model recipe schema-provider version changed; refresh its registered field snapshot")
    components = ({row["family"]: row["core_recipe"]} if row["family"] != "assembly" else row["components"])
    for family, name in components.items():
        keyword = FAMILIES[family][name][0]
        cls, _ = _pydyna_class(keyword)
        actual = {}
        for card in _cards(cls, keyword):
            for field in card["fields"]:
                actual.setdefault(field["name"], set()).add(field["type"])
        if any(actual.get(field) != {kind} for field, kind in types[family][name].items()):
            raise ValueError("Model recipe field-type snapshot differs from the current schema provider")


def _finite_and_printable(value):
    if isinstance(value, dict):
        for child in value.values():
            _finite_and_printable(child)
    elif isinstance(value, list):
        for child in value:
            _finite_and_printable(child)
    elif isinstance(value, str):
        if not value.isprintable():
            raise ValueError("Model recipe text and unit labels must contain printable single-line text")
    elif type(value) in (int, float):
        try:
            finite = math.isfinite(float(value))
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("Model recipe numbers must be finite and representable")


def _operations(row, values):
    if row["family"] != "assembly":
        family = row["family"]
        ident = ID_FIELDS[family]
        operation = dict(op="add_" + family, recipe=row["core_recipe"], params=values["params"],
                         units=values["units"], **{ident: values[ident]})
        if "title" in values:
            operation["title"] = values["title"]
        return [operation]
    result = [dict(op="add_" + family, recipe=name, params=values[family], units=values["units"],
                   **{ID_FIELDS[family]: values[ID_FIELDS[family]]}) for family, name in row["components"].items()]
    part = dict(op="add_part" if values["part_action"] == "add" else "set_part", pid=values["pid"],
                mid=values["mid"], eosid=values["eosid"], secid=values["secid"])
    if values["part_action"] == "add":
        part["title"] = values["part_title"]
    return result + [part]


def run(service, reference, parameters, model, file_type, session_id, launch_mode):
    match = VERSIONED_REFERENCE.fullmatch(reference)
    if match is None:
        raise ValueError("Invalid model: recipe reference")
    if session_id is not None or file_type != "keyword" or launch_mode != "c" or model is None:
        raise ValueError("Host model recipes require an explicit keyword model, no session or native launch mode")
    rows, types, provider, identity = load_registry()
    ident, selected_version = match.groups()
    if ident not in rows:
        raise ValueError("Unknown host model recipe")
    from .automation.recipes import validate_parameters

    try:
        raw = json.dumps(parameters, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("Model recipe parameters must be a finite JSON object") from error
    if len(raw.encode("utf8")) > MAX_BYTES:
        raise ValueError("Model recipe parameters exceed 1 MiB")
    row = rows[ident]
    schema = parameter_schema(row, types)
    current_reference = pinned_reference(row, schema, provider, identity)
    if selected_version is not None and reference != current_reference:
        raise ValueError("Host model recipe reference is stale: definition/provider/parameter contract version changed; discover it again")
    values = validate_parameters(schema, copy.deepcopy(parameters))
    _finite_and_printable(values)
    values["units"] = unit_label(values["units"])
    _provider_check(row, types, provider)
    # Freeze the complete validated definition/values before dispatch.  This is
    # exactly one existing AST transaction, never incremental output writes.
    operations = _operations(row, values)
    result = service.edit_keywords(model, operations)
    outcome = JobResult.model_validate(result)
    metadata = dict(id=ident, reference=current_reference, requested_reference=reference,
                    reference_policy="pinned" if selected_version is not None else "explicit_latest",
                    origin="bundled_model_registry_snapshot", backend="keyword", verification_level="L1",
                    source=identity, provider_snapshot=provider, parameters=values, native_executed=False,
                    versions_verified=[], scope=SCOPE)
    outcome = JobResult(**{**outcome.model_dump(exclude={"comparison_data"}), "operation": "run_recipe", "backend": "keyword",
                          "data": dict(outcome.data, recipe=metadata)})
    if outcome.job_id:
        atomic_json(service.jobs.root / outcome.job_id / "recipe-result.json", outcome.model_dump(mode="json"))
    return outcome.model_dump(mode="json")


def knowledge_documents(repository):
    """Index every candidate honestly, even though default find excludes them."""
    from .knowledge_index import Document

    rows, types, provider, identity = load_registry(repository)
    version = "model-registry-v1:" + ":".join(identity[key]["sha256_lf"] for key in sorted(identity))
    for row in rows.values():
        schema = parameter_schema(row, types)
        body = dict(id=row["id"], reference=pinned_reference(row, schema, provider, identity), reference_policy="pinned",
                    keyword=row.get("keyword"), description=row["description"], tags=row["tags"],
                    channel="keyword", backend="keyword", input_kind="keyword", requires_model=True,
                    verification_level="L1", tier="candidate", versions_verified=[], native_executed=False, scope=SCOPE,
                    requirements=dict(optional_extra="pydyna", package="ansys-dyna-core", field_schema_snapshot_version=provider["version"]),
                    parameters=schema, field_provider_snapshot=provider)
        yield Document("model-recipe-registry", "recipe", row["name"], json.dumps(body, ensure_ascii=False, sort_keys=True),
                       "repo://" + MANIFEST_RELATIVE + "#" + row["id"], "MIT", "public", version)
