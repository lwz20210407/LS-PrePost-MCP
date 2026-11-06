"""A discovered host contract cannot silently change between find and execute."""
import copy
import json
import shutil

import pytest

from ls_prepost_mcp import model_recipes
from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tests.test_model_recipes import ROOT, STEEL, specimen


@pytest.fixture
def private_registry(tmp_path, monkeypatch):
    repository = tmp_path / "registry-repository"
    package = repository / "src/ls_prepost_mcp"
    for relative in ("data/model_recipes.json", "domain/model/materials.py", "domain/model/controls.py",
                     "automation/recipes.py", "core/validation.py"):
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "src/ls_prepost_mcp" / relative, target)
    monkeypatch.setattr(model_recipes, "PACKAGE", package)
    return repository, package / "data/model_recipes.json"


def discovered(service):
    return next(row for row in service.find_recipe(task_id="P03", channel="keyword", include_candidates=True)
                if row["id"] == "model:mat-001-elastic")


@pytest.mark.parametrize("changed", ["manifest", "core", "provider"])
def test_stale_discovered_contract_is_refused_before_edit(tmp_path, monkeypatch, private_registry, changed):
    _, manifest = private_registry
    service = Service(Settings(tmp_path / "work"))
    before = discovered(service)
    if changed == "manifest":
        payload = json.loads(manifest.read_text(encoding="utf8"))
        entry = next(row for row in payload["recipes"] if row["id"] == before["id"])
        entry.update(core_recipe="rigid", keyword="*MAT_RIGID")
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf8")
    elif changed == "core":
        contract = model_recipes.PACKAGE / "domain/model/materials.py"
        contract.write_bytes(contract.read_bytes() + b"\n# private contract revision\n")
    else:
        original = model_recipes._source
        def changed_source(path, locator):
            result = original(path, locator)
            if locator.endswith("/model_recipes.py"):
                result["sha256_lf"] = "0" * 64
            return result
        monkeypatch.setattr(model_recipes, "_source", changed_source)
    calls = []
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: calls.append((a, kw)) or pytest.fail("Stale reference reached edit"))
    with pytest.raises(ValueError, match="stale|version|changed"):
        service.run_recipe(before["reference"], dict(units="mm-t-s", mid=7, params=STEEL), "unused.k")
    assert calls == [] and not (tmp_path / "work").exists()


def test_indexed_candidates_carry_the_same_pinned_contract_as_discovery(tmp_path, private_registry):
    repository, _ = private_registry
    service = Service(Settings(tmp_path / "work"))
    row = discovered(service)
    docs = list(model_recipes.knowledge_documents(repository))
    record = next(json.loads(doc.text) for doc in docs if json.loads(doc.text)["id"] == row["id"])
    assert row["reference"].startswith(row["id"] + "@")
    assert len(row["reference"].rsplit("@", 1)[1]) == 64
    assert record["reference"] == row["reference"]


def test_run_uses_one_loaded_snapshot_and_bare_latest_remains_explicit(tmp_path, monkeypatch, private_registry):
    pytest.importorskip("ansys.dyna.core")
    source = specimen(tmp_path)
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    row = discovered(service)
    original = model_recipes.load_registry
    calls = []
    def counted(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(model_recipes, "load_registry", counted)
    result = service.run_recipe(row["reference"], dict(units="mm-t-s", mid=7, params=copy.deepcopy(STEEL)), str(source))
    assert result["status"] == "succeeded" and len(calls) == 1
    assert result["data"]["recipe"]["reference_policy"] == "pinned"
    calls.clear()
    latest = service.run_recipe(row["id"], dict(units="mm-t-s", mid=8, params=copy.deepcopy(STEEL)), str(source))
    assert latest["status"] == "succeeded" and len(calls) == 1
    assert latest["data"]["recipe"]["reference_policy"] == "explicit_latest"
