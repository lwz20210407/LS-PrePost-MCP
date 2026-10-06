from pathlib import Path

import pytest
import yaml

from ls_prepost_mcp.automation.recipes import ROOT, load_recipe, validate_parameters
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def test_builtin_recipe_schema_and_parameter_rejection(tmp_path, monkeypatch):
    service=Service(Settings(tmp_path))
    found=service.find_recipe(task_id="A08",include_candidates=True)
    assert len(found)==5
    assert service.find_recipe("Block Mesher",channel="cfile",include_candidates=True)[0]["id"]=="box_mesh"
    monkeypatch.setattr(service,"run_script",lambda *a,**kw:pytest.fail("Bad parameters must not execute"))
    for values in (dict(width=True),dict(width="2"),dict(width=-1),dict(extra=3)):
        with pytest.raises(ValueError):
            service.run_recipe("box_mesh",values)
    assert not list(tmp_path.iterdir())


def test_recipe_template_cannot_escape_definition_directory(tmp_path):
    raw=yaml.safe_load((ROOT/"box_mesh/recipe.yaml").read_text(encoding="utf8"))
    directory=tmp_path/"definition"
    directory.mkdir()
    (tmp_path/"foreign.cfile").write_text("exit")
    raw["template"]="../foreign.cfile"
    path=directory/"recipe.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError,match="local file"):
        load_recipe(path)


def test_parameter_schema_never_fetches_external_references():
    schema=dict(type="object",additionalProperties=False,properties=dict(value={"$ref":"https://example.invalid/schema.json"}))
    with pytest.raises(ValueError,match="external"):
        validate_parameters(schema,dict(value=1))


def test_legacy_json_templates_are_candidates_and_old_names_delegate(tmp_path,monkeypatch):
    service=Service(Settings(tmp_path))
    old=service.create_native_macro("legacy width","cfile","mesh {{width}}",dict(width=2))
    path=old["artifacts"][0]["path"]
    before=Path(path).read_bytes()
    assert not service.find_recipe("legacy width")
    found=service.find_recipe("legacy width",include_candidates=True)
    assert found[0]["reference"]==path and found[0]["tier"]=="candidate"
    calls=[]
    def execute(ident,expected,*args):
        prepared=service.jobs.get(ident)
        calls.append(prepared["data"]["rendered_source"])
        directory,result=service.jobs.create("fake",{})
        return dict(result,status="succeeded",job_directory=str(directory),data=dict(ok=True))
    monkeypatch.setattr(service,"execute_native_program",execute)
    assert service.run_recipe(path,dict(width=3))["status"]=="succeeded"
    assert service.run_native_macro(path,dict(width=4))["status"]=="succeeded"
    assert calls==["mesh 3","mesh 4"] and Path(path).read_bytes()==before
