"""A08 recipe definitions, discovery and execution; legacy names delegate here."""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Literal

import yaml
from jsonschema import Draft202012Validator, validators
from pydantic import Field, StrictInt

from ..core.contracts import Contract, JobResult, Text
from ..core.script_parameters import render_cfile
from ..core.script_request import ScriptOutput
from ..jobs import atomic_json, check_artifact, fingerprint, now
from ..knowledge_index import terms
from ..native.versions import profile
from ..outcomes import normalize_outcome
from ..program_bundle import capture_dependencies, checked_dependencies, write_dependencies
from ..programs import LANGUAGES, count_contract, numeric_parameters, output_contract, render

ROOT = Path(__file__).parents[1] / "native/recipes"
ParameterValidator = validators.extend(Draft202012Validator, type_checker=Draft202012Validator.TYPE_CHECKER.redefine_many({
    "integer": lambda checker, value: type(value) is int,
    "number": lambda checker, value: type(value) is int or type(value) is float and math.isfinite(value),
}))


class Recipe(Contract):
    schema_version: Literal[1] = 1
    id: Text
    name: Text
    task_id: Text
    channel: Literal["command", "cfile", "scl", "python"]
    template: Text
    description: Text
    parameters: dict = Field(default_factory=lambda: dict(type="object",properties={},additionalProperties=False))
    outputs: list[ScriptOutput]
    expected_counts: dict[str, StrictInt] = Field(default_factory=dict)
    versions_verified: list[str] = Field(default_factory=list)
    execution_modes: dict[str, dict]
    l2_case: str | None = None
    requires_model: bool = True
    contexts: list[Literal["batch", "session"]] = Field(default_factory=lambda: ["batch"])
    tags: list[str] = Field(default_factory=list)
    input_kind: Literal["keyword", "d3plot", "any"] = "keyword"
    dependencies: list[dict] = Field(default_factory=list)


def load_recipe(path):
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Recipe exceeds 1 MiB")
    definition_bytes = path.read_bytes()
    recipe = Recipe.model_validate(yaml.safe_load(definition_bytes))
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,79}", recipe.id) or not re.fullmatch(r"[A-Z]\d{2}", recipe.task_id):
        raise ValueError("Invalid recipe or task ID")
    source = (path.parent / recipe.template).resolve(strict=True)
    if not source.is_relative_to(path.parent) or not source.is_file() or source.stat().st_size > 1024*1024:
        raise ValueError("Recipe template must be a bounded local file")
    if set(recipe.execution_modes) != {"c_nographics", "runc"}:
        raise ValueError("Recipe must declare both native batch modes")
    for entry in recipe.execution_modes.values():
        if entry.get("status") not in ("verified", "failed", "unverified") or not entry.get("evidence"):
            raise ValueError("Execution modes require explicit status and evidence")
    template_bytes = source.read_bytes()
    identities = {name:dict(path=str(file),size=len(content),sha256=hashlib.sha256(content).hexdigest())
                  for name,file,content in (("definition",path,definition_bytes),("template",source,template_bytes))}
    return recipe, template_bytes.decode("utf-8-sig"), path, identities


def validate_parameters(schema, values):
    if values is not None and (not isinstance(values,dict) or any(not isinstance(key,str) for key in values)):
        raise ValueError("Recipe parameters must be an object with string keys")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValueError("Recipe parameter schema must forbid unknown properties")
    def local_refs(item):
        if isinstance(item, dict):
            if any(key in item and not str(item[key]).startswith("#") for key in ("$ref","$dynamicRef","$recursiveRef")):
                raise ValueError("Recipe parameter schema cannot fetch external references")
            for child in item.values():
                local_refs(child)
        elif isinstance(item, list):
            for child in item:
                local_refs(child)
    local_refs(schema)
    ParameterValidator.check_schema(schema)
    parameters = {name: entry["default"] for name,entry in schema.get("properties",{}).items() if "default" in entry}
    parameters.update(values or {})
    errors = sorted(ParameterValidator(schema).iter_errors(parameters), key=lambda error: str(error.path))
    if errors:
        raise ValueError("Recipe parameters: " + "; ".join(error.message for error in errors))
    json.dumps(parameters, allow_nan=False)
    return parameters


def load_legacy(path):
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Legacy recipe exceeds 1 MiB")
    definition = json.loads(path.read_text(encoding="utf8"))
    if definition.get("schema_version") != 1 or definition.get("kind") != "native_macro":
        raise ValueError("Unsupported legacy JSON recipe")
    numeric_parameters(definition["defaults"])
    output_contract(definition["outputs"])
    count_contract(definition["expected_counts"])
    return definition


def execute_prepared(service, prepared, model, file_type, graphics, session_id, *, action, arguments, launch_mode="c", adopt=False):
    if session_id is not None:
        if model is not None or launch_mode != "c":
            raise ValueError("Session recipes use the current model and have no batch launch mode")
        from ..gui_programs import execute_prepared as in_session
        folder = service.jobs.root / prepared["job_id"]
        contract = json.loads((folder / "contract.json").read_text(encoding="utf8"))
        return in_session(service, session_id, prepared["job_id"], prepared["data"]["sha256"], contract,
                          (folder/contract["program"]).read_bytes(), checked_dependencies(folder,contract),
                          journal_action=action,journal_parameters=arguments,allow_owned_output_context=adopt)
    if launch_mode == "c":
        return service.execute_native_program(prepared["job_id"],prepared["data"]["sha256"],model,file_type,graphics)
    return service.execute_native_program(prepared["job_id"],prepared["data"]["sha256"],model,file_type,graphics,launch_mode=launch_mode)


class RecipeTools:
    def find_recipe(self, query: str = "", task_id: str | None = None, channel: str | None = None, limit: StrictInt = 20,
                    include_candidates: bool = False) -> list[dict]:
        """Find recipes by keyword, task ID or language with exact verification scope. include_candidates also lists installed templates/filters as offline adapters with channel=null, real parameter contracts and explicit unsupported reasons."""
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Recipe limit must be 1..50")
        if type(include_candidates) is not bool:
            raise ValueError("include_candidates must be Boolean")
        wanted = set(terms(query))
        hits = []
        paths = list(ROOT.glob("*/recipe.yaml"))
        if include_candidates:
            paths += list(self.jobs.root.glob("*/recipe.yaml"))
        for path in sorted(paths):
            recipe, _, _, _ = load_recipe(path)
            verified = path.is_relative_to(ROOT) and bool(recipe.versions_verified and recipe.l2_case)
            if not include_candidates and not verified:
                continue
            if task_id and recipe.task_id != task_id or channel and recipe.channel != channel:
                continue
            score = len(wanted & set(terms(recipe.name + " " + recipe.description + " " + " ".join(recipe.tags))))
            if wanted and not score:
                continue
            row = recipe.model_dump(mode="json")
            row.update(reference=recipe.id if path.is_relative_to(ROOT) else str(path), tier="T2" if verified else "candidate")
            hits.append((score,row))
        if include_candidates:
            from .installed_recipes import candidates

            hits.extend(candidates(self, wanted, task_id, channel))
            for path in sorted(self.jobs.root.glob("*/macro.json")):
                definition = load_legacy(path)
                if task_id and task_id != "A08" or channel and channel != definition["language"]:
                    continue
                score = len(wanted & set(terms(definition["name"] + " legacy JSON template")))
                if wanted and not score:
                    continue
                hits.append((score,dict(id="user-"+path.parent.name,name=definition["name"],task_id="A08",
                                        channel=definition["language"],reference=str(path),tier="candidate",
                                        parameters=definition["defaults"],outputs=definition["outputs"],
                                        versions_verified=[],l2_case=None)))
        return [row for _,row in sorted(hits,key=lambda item:(-item[0],item[1]["id"]))[:limit]]

    def run_recipe(self, recipe: str, parameters: dict | None = None, model: str | None = None,
                   file_type: Literal["keyword", "d3plot"] = "keyword", session_id: str | None = None,
                   launch_mode: Literal["c", "runc"] = "c") -> dict:
        """Validate and run a bundled ID, authorized YAML/JSON path, or installed: reference. Installed templates take values, required units and Boolean native_check (default false); filters require a keyword model and no parameters. Installed adapters reject sessions/runc/d3plot. Return JobResult with source identity and verification scope."""
        if recipe.startswith("installed:"):
            from .installed_recipes import run

            return run(self, recipe, parameters, model, file_type, session_id, launch_mode)
        bundled = bool(re.fullmatch(r"[a-z][a-z0-9_-]{0,79}", recipe)) and (ROOT/recipe/"recipe.yaml").is_file()
        path = ROOT/recipe/"recipe.yaml" if bundled else self.settings.input_path(recipe)
        if path.suffix.lower() == ".json":
            result = self._run_recipe_legacy(str(path),parameters,model,file_type,False,session_id,launch_mode)
            result.setdefault("data",{})["recipe"] = dict(origin="legacy_json",tier="candidate",
                                                           source=result["macro_source"],parameters=result["recipe_parameters"])
            outcome = normalize_outcome("run_recipe", result)
            return outcome.model_dump(mode="json",exclude={"comparison_data"})
        spec, code, source, identities = load_recipe(path)
        context = "session" if session_id else "batch"
        if context not in spec.contexts or spec.requires_model and context=="batch" and model is None:
            raise ValueError("Recipe needs a supported context and explicit model")
        actual_kind = self._session_manager().read(session_id)["model_kind"] if session_id else file_type
        if spec.input_kind != "any" and actual_kind != spec.input_kind:
            raise ValueError("Recipe has not been verified for this model kind")
        values = validate_parameters(spec.parameters,parameters)
        before = identities["definition"]
        template_identity = identities["template"]["sha256"]
        rendered = render_cfile(code,values) if spec.channel == "cfile" else render(code,numeric_parameters(values)) if spec.channel in ("command","scl") else code
        dependencies=[]
        for item in spec.dependencies:
            if set(item) != {"path","name"}:
                raise ValueError("Recipe dependencies require path and name")
            dependency=(source.parent/item["path"]).resolve(strict=True)
            if not dependency.is_relative_to(source.parent):
                raise ValueError("Recipe dependency escaped its directory")
            dependencies.append(dict(path=str(dependency),name=item["name"]))
        result = self.run_script(spec.channel, rendered, context=context, session_id=session_id, model=model,
                                 file_type=file_type, outputs=[item.model_dump() for item in spec.outputs],
                                 expected_counts=spec.expected_counts, parameters=values if spec.channel=="python" else None,
                                 launch_mode=launch_mode, dependencies=dependencies)
        try:
            unchanged = True
            for identity in identities.values():
                current = fingerprint(Path(identity["path"]))
                unchanged = unchanged and all(current[key] == value for key,value in identity.items())
        except OSError:
            unchanged = False
        if not unchanged:
            result.update(status="failed",error=dict(message="Recipe definition changed during execution"))
        result["operation"] = "run_recipe"
        outcome = JobResult.model_validate(result)
        data = dict(outcome.data,recipe=dict(id=spec.id,source=before,parameters=values,
                    template_sha256=template_identity,
                    versions_verified=spec.versions_verified,execution_modes=spec.execution_modes,
                    installed_profile=profile(self.settings.executable),origin="bundled" if bundled else "user_definition_unverified"))
        outcome = JobResult(**{**outcome.model_dump(exclude={"comparison_data"}),"data":data})
        if outcome.evidence:
            directory = Path(outcome.evidence[-1].path).parent
            atomic_json(directory/"recipe-result.json",outcome.model_dump(mode="json"))
        return outcome.model_dump(mode="json")

    def _create_recipe_legacy(self,name,language,code,defaults,outputs=None,expected_counts=None,dependencies=None):
        if not isinstance(name,str) or not name.strip() or len(name)>120 or language not in LANGUAGES:
            raise ValueError("Invalid macro name/language")
        if not isinstance(code,str) or not code.strip() or len(code.encode("utf8"))>1024*1024 or "\x00" in code:
            raise ValueError("Expected nonempty source up to 1 MiB")
        render(code,numeric_parameters(defaults))
        definition=dict(schema_version=1,kind="native_macro",name=name,language=language,code=code,defaults=defaults,
                        outputs=output_contract(outputs),expected_counts=count_contract(expected_counts))
        directory,manifest=self.jobs.create("create_native_macro",dict(name=name,language=language))
        captured=capture_dependencies(self.settings,dependencies,definition["outputs"])
        write_dependencies(directory/"assets",captured)
        definition["dependencies"]=[item for item,_ in captured]
        atomic_json(directory/"macro.json",definition)
        manifest.update(status="succeeded",job_directory=str(directory),artifacts=[check_artifact(directory/"macro.json","json")],finished_at=now())
        atomic_json(directory/"job.json",manifest)
        return manifest

    def _run_recipe_legacy(self,path,parameters=None,model=None,file_type="keyword",graphics=False,session_id=None,launch_mode="c"):
        source=self.settings.input_path(path)
        source_identity=fingerprint(source)
        definition=load_legacy(source)
        if fingerprint(source) != source_identity:
            raise ValueError("Legacy recipe changed while it was read")
        parameters=numeric_parameters(parameters or {})
        if set(parameters)-definition["defaults"].keys():
            raise ValueError("Unknown macro parameters")
        checked_dependencies(source.parent/"assets",definition)
        prepared=self.prepare_native_program(definition["language"],code=definition["code"],
            parameters={**definition["defaults"],**parameters},outputs=definition["outputs"],expected_counts=definition["expected_counts"],
            dependencies=[dict(path=str(source.parent/"assets"/item["name"]),name=item["name"]) for item in definition.get("dependencies",[])])
        expected={item["name"]:(item["sha256"],item["size"]) for item in definition.get("dependencies",[])}
        actual={item["name"]:(item["sha256"],item["size"]) for item in prepared["data"].get("dependencies",[])}
        if expected != actual:
            raise ValueError("Legacy recipe dependencies changed while staging")
        result=execute_prepared(self,prepared,model,file_type,graphics,session_id,action="run_native_macro",arguments=dict(path=path,parameters=parameters),launch_mode=launch_mode)
        result["macro_source"]=source_identity
        result["recipe_parameters"]={**definition["defaults"],**parameters}
        try:
            unchanged=fingerprint(source)==source_identity
        except OSError:
            unchanged=False
        if not unchanged:
            result.update(status="failed",error=dict(message="Legacy recipe changed during execution",previous=result.get("error")))
        atomic_json(Path(result["job_directory"])/"job.json",result)
        return result
