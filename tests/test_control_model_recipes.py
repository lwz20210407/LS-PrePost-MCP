"""P10 host recipes reuse existing control upserts and one atomic transaction."""
import copy
import json
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck, controls
from ls_prepost_mcp.service import Service

IDS = {"model:control-termination", "model:control-timestep", "model:control-hourglass",
       "model:control-energy", "model:output-d3plot", "model:output-ascii", "model:control-output"}
CASES = [("model:control-termination", "*CONTROL_TERMINATION", {"endtim": 50., "endcyc": 456,
             "dtmin": .001, "endeng": .25, "endmas": .5}),
         ("model:control-timestep", "*CONTROL_TIMESTEP", {"tssfac": .77, "dtinit": .01, "isdo": 1,
             "tslimt": .02, "dt2ms": -.001, "lctm": 0, "erode": 1, "ms1st": 0}),
         ("model:control-hourglass", "*CONTROL_HOURGLASS", {"ihq": 1, "qh": .03}),
         ("model:control-energy", "*CONTROL_ENERGY", {"hgen": 2, "rwen": 1, "slnten": 2, "rylen": 1}),
         ("model:output-d3plot", "*DATABASE_BINARY_D3PLOT", {"dt": 1., "lcdt": 0, "npltc": 1, "psetid": 0})]
OLD_P03 = [
    "model:mat-001-elastic@2715a00ade3a62488eb45720e02b11d652d9970149916fd7f1a63714e728e1d5",
    "model:mat-003-plastic-kinematic@faee0870765dd744a2b3348f06d98d695995620b58769708ee6ebaf5ed1f416b",
    "model:mat-015-johnson-cook@3f23df64489be5c17da254e03bad0230d54b89341a2edccc4bb89e04dc837c56",
    "model:mat-020-rigid@4971bf722e669248230ebfae126e4cdfa10d6162de85e11e28d599a42e49d979",
    "model:mat-024-piecewise-linear-plasticity@c2e273c6ead812ce3d4e698f97255c8accaa80572b29f98aff1e1e20b1409a4a",
    "model:mat-098-simplified-johnson-cook@45b150fd0e014bf34c336d1b8e99b6dba6aaf67be9febf02050e235cc94bf60e",
    "model:eos-linear-polynomial@b94754ff1494cb919ab142fcbf72b26f95d06d107dc068e3891a5bd874cec84b",
    "model:eos-gruneisen@0913a8981229dd65c4ecd6abfc2ac5e56bdfca11c007ea0cf9feaa914f728559",
    "model:johnson-cook-solid-part@4b504896d43aabb17f60c15855f8120071762107d3be46b368f40a6859298895",
]


@pytest.fixture
def model(tmp_path, monkeypatch):
    source = tmp_path / "input.k"
    source.write_text("*KEYWORD\n*END\n", encoding="ascii")
    service = Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))
    monkeypatch.setattr(service, "run_script", lambda *a, **kw: pytest.fail("P10 host recipes never execute native"))
    return source, service


def bundle():
    # Explicit synthetic inputs, not physical recommendations or inferred defaults.
    return dict(units="g-mm-us", termination={"endtim": 50.}, d3plot={"dt": 1.},
                ascii={"names": ["glstat", "matsum", "rcforc"], "dt": .1, "binary": 0},
                hourglass={"ihq": 1, "qh": .03})


def test_p10_catalog_has_six_leaves_and_atomic_story_without_native_claims(model):
    _, service = model
    rows = service.find_recipe(task_id="P10", channel="keyword", include_candidates=True)
    assert {r["id"] for r in rows} == IDS
    assert all(r["tier"] == "candidate" and r["verification_level"] == "L1" and not r["versions_verified"] for r in rows)
    assert all(r["backend"] == "keyword" and r["task_id"] == "P10" and "@" in r["reference"] for r in rows)
    assert len(service.find_recipe(task_id="P03", channel="keyword", include_candidates=True)) == 9


@pytest.mark.parametrize("reference,keyword,params", CASES)
def test_leaf_writes_only_caller_values(model, reference, keyword, params):
    source, service = model
    before = source.read_bytes()
    result = service.run_recipe(reference, dict(units="g-mm-us", params=params), str(source))
    assert result["status"] == "succeeded" and result["data"]["recipe"]["native_executed"] is False
    saved = KeywordDeck.load(result["data"]["main"])
    block = saved.blocks(keyword)[0]
    assert {key: saved.get(block, key).value for key in params} == params
    assert source.read_bytes() == before


@pytest.mark.parametrize("reference,keyword,params", CASES)
def test_missing_required_leaf_values_never_dispatch(model, monkeypatch, reference, keyword, params):
    source, service = model
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("invalid contract dispatched"))
    incomplete = dict(params)
    incomplete.pop(next(iter(incomplete)))
    with pytest.raises(ValueError):
        service.run_recipe(reference, dict(units="g-mm-us", params=incomplete), str(source))


@pytest.mark.parametrize("reference,params", [(reference, params) for reference, _, params in CASES]
    + [("model:output-ascii", {"names": ["glstat"], "dt": .1})])
def test_each_leaf_requires_units_before_edit(model, monkeypatch, reference, params):
    source, service = model
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("units missing at dispatch"))
    with pytest.raises(ValueError):
        service.run_recipe(reference, {"params": params}, str(source))


def test_ascii_whitelist_uses_existing_34_core_names(model):
    source, service = model
    result = service.run_recipe("model:output-ascii", dict(units="g-mm-us", params=dict(names=list(controls.ASCII), dt=.1, binary=0)), str(source))
    assert result["status"] == "succeeded"
    saved = KeywordDeck.load(result["data"]["main"])
    assert len(controls.ASCII) == 34
    for name in controls.ASCII:
        block = saved.blocks("*DATABASE_" + name.upper())[0]
        assert saved.get(block, "dt").value == .1 and saved.get(block, "binary").value == 0


@pytest.mark.parametrize("params", [{"names": [], "dt": .1}, {"names": "glstat", "dt": .1},
    {"names": ["glstat", "glstat"], "dt": .1}, {"names": ["unknown"], "dt": .1},
    {"names": ["glstat"], "dt": True}, {"names": ["glstat"], "dt": float("nan")},
    {"names": ["glstat"], "dt": float("inf")}, {"names": ["glstat"], "dt": .1, "binary": True},
    {"names": ["glstat"], "dt": .1, "binary": 1.5}, {"names": ["glstat"], "dt": .1, "binary": "1"},
    {"names": ["glstat"], "dt": .1, "extra": 1}])
def test_ascii_coercions_and_unknown_values_refuse_before_edit(model, monkeypatch, params):
    source, service = model
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("ASCII contract dispatched"))
    with pytest.raises(ValueError):
        service.run_recipe("model:output-ascii", dict(units="g-mm-us", params=params), str(source))


@pytest.mark.parametrize("change", ["units", "termination", "d3plot", "ascii", "hourglass", "qh",
    "top_extra", "field_extra", "bool_int", "bool_float", "part_hourglass_qm"])
def test_composite_requires_every_explicit_component_before_edit(model, monkeypatch, change):
    source, service = model
    values = bundle()
    if change in ("units", "termination", "d3plot", "ascii", "hourglass"):
        del values[change]
    elif change == "qh":
        del values["hourglass"]["qh"]
    elif change == "top_extra":
        values["native_check"] = True
    elif change == "field_extra":
        values["termination"]["extra"] = 1
    elif change == "bool_int":
        values["hourglass"]["ihq"] = True
    elif change == "part_hourglass_qm":
        values["hourglass"] = {"ihq": 1, "qm": .03}
    else:
        values["termination"]["endtim"] = True
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("incomplete story dispatched"))
    with pytest.raises(ValueError):
        service.run_recipe("model:control-output", values, str(source))


def test_composite_dispatches_once_and_late_engine_failure_publishes_nothing(model, monkeypatch):
    source, service = model
    calls = []
    original_edit = service.edit_keywords
    def edit(*args, **kwargs):
        calls.append(copy.deepcopy(args[1]))
        return original_edit(*args, **kwargs)
    monkeypatch.setattr(service, "edit_keywords", edit)
    values = bundle()
    values.update(timestep={"tssfac": .77}, energy={"hgen": 2})
    result = service.run_recipe("model:control-output", values, str(source))
    assert result["status"] == "succeeded" and len(calls) == 1 and len(calls[0]) == 6
    saved = KeywordDeck.load(result["data"]["main"])
    assert len(saved.blocks("*DATABASE_*")) == 4 and len(saved.blocks("*CONTROL_*")) == 4
    source.write_text("*KEYWORD\n*CONTROL_ENERGY\n2\n*CONTROL_ENERGY\n2\n*END\n", encoding="ascii")
    before = source.read_bytes()
    failed = service.run_recipe("model:control-output", values, str(source))
    assert failed["status"] == "failed" and not failed["artifacts"]
    assert source.read_bytes() == before and len(calls) == 2


@pytest.mark.parametrize("old_reference", OLD_P03)
def test_real_pre_p10_content_pins_stale_before_any_edit(model, monkeypatch, old_reference):
    source, service = model
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("stale pin dispatched"))
    with pytest.raises(ValueError, match="stale.*discover"):
        service.run_recipe(old_reference, {}, str(source))


def test_newly_discovered_p03_pin_and_bare_latest_remain_functional(model):
    source, service = model
    row = next(r for r in service.find_recipe(task_id="P03", include_candidates=True) if r["id"] == "model:mat-001-elastic")
    assert row["reference"] != OLD_P03[0]
    values = dict(units="mm-t-s", mid=7, params=dict(ro=7.8e-9, e=210000., pr=.3))
    result = service.run_recipe(row["reference"], values, str(source))
    assert result["status"] == "succeeded" and result["data"]["recipe"]["reference_policy"] == "pinned"
    latest = service.run_recipe(row["id"], values, str(source))
    assert latest["status"] == "succeeded" and latest["data"]["recipe"]["reference_policy"] == "explicit_latest"


def test_positive_output_curve_reference_is_not_bypassed(model):
    source, service = model
    result = service.run_recipe("model:output-d3plot", dict(units="g-mm-us", params=dict(dt=1., lcdt=987)), str(source))
    assert result["status"] == "failed" and not result["artifacts"]


def test_p10_documents_carry_the_discovered_pin_without_building_an_index(model):
    from ls_prepost_mcp.model_recipes import knowledge_documents

    _, service = model
    rows = service.find_recipe(task_id="P10", include_candidates=True)
    docs = [json.loads(d.text) for d in knowledge_documents(Path(__file__).resolve().parents[1])]
    by_id = {d["id"]: d for d in docs}
    for row in rows:
        assert by_id[row["id"]]["reference"] == row["reference"]
        assert by_id[row["id"]]["task_id"] == "P10"


def test_control_provider_type_drift_refuses_before_edit(model, monkeypatch):
    from ls_prepost_mcp import model_recipes

    source, service = model
    original = model_recipes.load_registry
    def drifted():
        rows, types, provider, identity = original()
        types["control"]["energy"]["hgen"] = "float"
        return rows, types, provider, identity
    monkeypatch.setattr(model_recipes, "load_registry", drifted)
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("provider drift dispatched"))
    with pytest.raises(ValueError, match="field-type snapshot"):
        service.run_recipe("model:control-energy", dict(units="g-mm-us", params={"hgen": 2.}), str(source))
