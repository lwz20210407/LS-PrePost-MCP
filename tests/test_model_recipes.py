"""Public T2 host recipes must reuse atomic keyword editing, never native scripts."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.service import Service

ROOT = Path(__file__).resolve().parents[1]
IDS = {
    "model:mat-001-elastic", "model:mat-003-plastic-kinematic", "model:mat-015-johnson-cook",
    "model:mat-020-rigid", "model:mat-024-piecewise-linear-plasticity", "model:mat-098-simplified-johnson-cook",
    "model:eos-linear-polynomial", "model:eos-gruneisen", "model:johnson-cook-solid-part",
}


def specimen(tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    for name in ("impact.k", "impact_mesh.k"):
        shutil.copy2(ROOT / "tests/l3/fixtures" / name, folder / name)
    return folder / "impact.k"


def jc_parameters():
    # Frozen pre03_jc_material.yaml's hand-written oracle, already in mm-t-s.
    return dict(units="mm-t-s", mid=3, eosid=1, secid=2, pid=2, part_action="set",
                material=dict(ro=7.83e-9, g=77000., a=792., b=510., n=.26, c=.014, m=1.03, tm=1793., tr=293., epso=1., cp=4.77e8),
                eos=dict(c=4.57e6, s1=1.49, gamao=1.93), section=dict(elform=1))


def test_six_materials_two_eos_and_atomic_jc_recipe_are_discoverable_as_host_candidates(tmp_path):
    service = Service(Settings(tmp_path))
    found = service.find_recipe(task_id="P03", channel="keyword", include_candidates=True)
    assert {row["id"] for row in found} == IDS
    assert all(row["backend"] == "keyword" and row["verification_level"] == "L1" for row in found)
    assert all(row["tier"] == "candidate" and not row["versions_verified"] for row in found)


def test_run_recipe_applies_the_existing_p03_oracle_in_one_keyword_transaction(tmp_path, monkeypatch):
    pytest.importorskip("ansys.dyna.core")
    source = specimen(tmp_path)
    original = {path: path.read_bytes() for path in source.parent.iterdir()}
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    monkeypatch.setattr(service, "run_script", lambda *a, **kw: pytest.fail("Host keyword recipe must never launch a native script"))
    calls = []
    execute = service.edit_keywords
    def edit(model, edits, **kwargs):
        calls.append(edits)
        return execute(model, edits, **kwargs)
    monkeypatch.setattr(service, "edit_keywords", edit)
    result = service.run_recipe("model:johnson-cook-solid-part", jc_parameters(), str(source))
    assert result["status"] == "succeeded" and result["operation"] == "run_recipe"
    assert result["backend"] == "keyword" and len(calls) == 1 and len(calls[0]) == 4
    saved = KeywordDeck.load(result["data"]["main"])
    part, row = saved.find("*PART", pid=2)[0]
    assert {name: saved.get(part, name, row=row).value for name in ("mid", "eosid", "secid")} == dict(mid=3, eosid=1, secid=2)
    material = saved.find("*MAT_JOHNSON_COOK", mid=3)[0][0]
    for key, expected in jc_parameters()["material"].items():
        assert saved.get(material, key).value == pytest.approx(expected, rel=1e-3)
    assert not saved.references(False).dangling()
    unchanged_part, unchanged_row = saved.find("*PART", pid=1)[0]
    assert {name: saved.get(unchanged_part, name, row=unchanged_row).value for name in ("mid", "eosid", "secid")} == dict(mid=1, eosid=0, secid=1)
    assert len(saved.files) == 2 and (Path(result["data"]["main"]).parent / "impact_mesh.k").read_bytes() == original[source.parent / "impact_mesh.k"]
    assert all(path.read_bytes() == content for path, content in original.items())


STEEL = dict(ro=7.8e-9, e=210000., pr=.3)
SIMPLE_CASES = [
    ("model:mat-001-elastic", "*MAT_ELASTIC", "mid", STEEL),
    ("model:mat-003-plastic-kinematic", "*MAT_PLASTIC_KINEMATIC", "mid", dict(STEEL, sigy=350., etan=1000.)),
    ("model:mat-015-johnson-cook", "*MAT_JOHNSON_COOK", "mid", jc_parameters()["material"]),
    ("model:mat-020-rigid", "*MAT_RIGID", "mid", dict(STEEL, cmo=1., con1=7., con2=7.)),
    ("model:mat-024-piecewise-linear-plasticity", "*MAT_PIECEWISE_LINEAR_PLASTICITY", "mid", dict(STEEL, sigy=350., etan=1000.)),
    ("model:mat-098-simplified-johnson-cook", "*MAT_SIMPLIFIED_JOHNSON_COOK", "mid", dict(STEEL, a=350., b=275., n=.36, c=.022)),
    ("model:eos-linear-polynomial", "*EOS_LINEAR_POLYNOMIAL", "eosid", dict(c1=100000.)),
    ("model:eos-gruneisen", "*EOS_GRUNEISEN", "eosid", dict(c=4570000., s1=1.49, gamao=1.93)),
]


@pytest.mark.parametrize("reference,keyword,ident,physical", SIMPLE_CASES)
def test_each_required_family_runs_through_public_recipe_without_physical_defaults(tmp_path, reference, keyword, ident, physical):
    pytest.importorskip("ansys.dyna.core")
    source = specimen(tmp_path)
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    values = dict(units="mm-t-s", params=copy.deepcopy(physical), **{ident: 7})
    original_values = copy.deepcopy(values)
    result = service.run_recipe(reference, values, str(source))
    assert result["status"] == "succeeded" and result["data"]["recipe"]["native_executed"] is False
    assert result["data"]["recipe"]["parameters"] == values == original_values
    saved = KeywordDeck.load(result["data"]["main"])
    block, _ = saved.find(keyword, **{ident: 7})[0]
    for field, expected in physical.items():
        assert saved.get(block, field).value == pytest.approx(expected, rel=1e-3)


@pytest.mark.parametrize("bad", [True, 1.5, 1.0, "7", 0, -1, 2_000_000_001])
def test_non_strict_or_out_of_range_header_ids_are_refused_before_edit(tmp_path, monkeypatch, bad):
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("Invalid identities must not edit"))
    with pytest.raises(ValueError):
        service.run_recipe("model:mat-001-elastic", dict(units="mm-t-s", mid=bad, params=STEEL), "unused.k")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("units", [None, True, 1, {}, [], "", "   ", "mm\n-t-s", "\x00mm", "mm\tkg"])
def test_invalid_unit_declarations_never_infer_or_generate_values(tmp_path, monkeypatch, units):
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("Invalid units must not edit"))
    with pytest.raises(ValueError):
        service.run_recipe("model:mat-001-elastic", dict(units=units, mid=7, params=STEEL), "unused.k")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("change", ["missing_units", "unknown_top", "unknown_physical", "missing_physical", "nan", "inf", "numeric_bool"])
def test_bad_schema_or_nonfinite_parameters_are_rejected_before_dispatch(tmp_path, monkeypatch, change):
    values = dict(units="mm-t-s", mid=7, params=copy.deepcopy(STEEL))
    if change == "missing_units":
        del values["units"]
    elif change == "unknown_top":
        values["ignored_request"] = 2
    elif change == "unknown_physical":
        values["params"]["invented_material_field"] = 3
    elif change == "missing_physical":
        del values["params"]["e"]
    else:
        values["params"]["e"] = dict(nan=float("nan"), inf=float("inf"), numeric_bool=True)[change]
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("Invalid parameter contract must not edit"))
    with pytest.raises(ValueError):
        service.run_recipe("model:mat-001-elastic", values, "unused.k")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("field,bad", [("pid", True), ("pid", 2.5), ("secid", 2.25)])
def test_assembly_id_validation_precedes_the_full_transaction(tmp_path, monkeypatch, field, bad):
    values = jc_parameters()
    values[field] = bad
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("Bad assembly identity must not edit"))
    with pytest.raises(ValueError):
        service.run_recipe("model:johnson-cook-solid-part", values, "unused.k")


def test_late_part_failure_keeps_the_whole_transaction_unpublished(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    source = specimen(tmp_path)
    before = {path: path.read_bytes() for path in source.parent.iterdir()}
    values = jc_parameters()
    values["pid"] = 999
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    result = service.run_recipe("model:johnson-cook-solid-part", values, str(source))
    assert result["status"] == "failed" and not result["artifacts"]
    assert not list((tmp_path / "work").rglob("*.k"))
    assert {path: path.read_bytes() for path in source.parent.iterdir()} == before


def test_explicit_add_part_mode_and_title_create_only_the_requested_part(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    source = specimen(tmp_path)
    values = dict(jc_parameters(), pid=5, part_action="add", part_title="new calibrated part")
    result = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,))).run_recipe(
        "model:johnson-cook-solid-part", values, str(source))
    assert result["status"] == "succeeded"
    saved = KeywordDeck.load(result["data"]["main"])
    block, row = saved.find("*PART", pid=5)[0]
    assert saved.get(block, "heading", row=row).value == values["part_title"]
    assert saved.get(block, "mid", row=row).value == 3
    assert len(saved.find("*PART", pid=2)) == 1


@pytest.mark.parametrize("options", [dict(file_type="d3plot"), dict(session_id="not-a-real-session"), dict(launch_mode="runc")])
def test_host_route_cannot_fall_through_to_native_contexts(tmp_path, monkeypatch, options):
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "run_script", lambda *a, **kw: pytest.fail("No native fallback"))
    with pytest.raises(ValueError, match="Host model recipes"):
        service.run_recipe("model:mat-001-elastic", dict(units="mm-t-s", mid=7, params=STEEL), "unused.k", **options)
    assert not list(tmp_path.iterdir())


def test_discovery_keeps_default_verified_native_contract_and_has_no_parameter_defaults(tmp_path):
    service = Service(Settings(tmp_path))
    assert not service.find_recipe(task_id="P03")
    assert not service.find_recipe(task_id="P03", channel="python", include_candidates=True)
    rows = service.find_recipe(task_id="P03", include_candidates=True)
    def defaults(value):
        if isinstance(value, dict):
            assert "default" not in value
            for child in value.values():
                defaults(child)
        elif isinstance(value, list):
            for child in value:
                defaults(child)
    for row in rows:
        defaults(row["parameters"])
        json.dumps(row, allow_nan=False)


@pytest.mark.parametrize("reference,identity,physical", [
    ("model:mat-024-piecewise-linear-plasticity", "mid", dict(STEEL, lcss=True)),
    ("model:mat-024-piecewise-linear-plasticity", "mid", dict(STEEL, lcsr=1.5, sigy=350.)),
    ("model:eos-gruneisen", "eosid", dict(c=4570000., s1=1.49, gamao=1.93, lcid="1")),
])
def test_provider_declared_reference_fields_are_not_truncated(tmp_path, monkeypatch, reference, identity, physical):
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("Bad typed reference must not edit"))
    with pytest.raises(ValueError):
        service.run_recipe(reference, dict(units="mm-t-s", params=physical, **{identity: 7}), "unused.k")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("change", ["missing_add_title", "ignored_set_title"])
def test_part_action_title_contract_does_not_ignore_intent(tmp_path, monkeypatch, change):
    values = jc_parameters()
    if change == "missing_add_title":
        values["part_action"] = "add"
    else:
        values["part_title"] = "must not be silently ignored"
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("Bad title/action must not edit"))
    with pytest.raises(ValueError):
        service.run_recipe("model:johnson-cook-solid-part", values, "unused.k")


def test_field_snapshot_drift_is_detected_before_backend_dispatch(tmp_path, monkeypatch):
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp import model_recipes

    original = model_recipes.load_registry
    def drifted():
        rows, types, provider, identity = original()
        types["material"]["elastic"]["e"] = "int"
        return rows, types, provider, identity
    monkeypatch.setattr(model_recipes, "load_registry", drifted)
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "edit_keywords", lambda *a, **kw: pytest.fail("Drift must not edit"))
    with pytest.raises(ValueError, match="field-type snapshot"):
        service.run_recipe("model:mat-001-elastic", dict(units="mm-t-s", mid=7, params=dict(STEEL, e=210000)), "unused.k")


@pytest.mark.parametrize("reference,physical", [
    ("model:mat-024-piecewise-linear-plasticity", STEEL),
    ("model:eos-linear-polynomial", dict(c0=0., c1=0.)),
])
def test_existing_engine_semantic_refusals_remain_atomic(tmp_path, reference, physical):
    pytest.importorskip("ansys.dyna.core")
    source = specimen(tmp_path)
    before = {p: p.read_bytes() for p in source.parent.iterdir()}
    service = Service(Settings(tmp_path / "work", allowed_roots=(source.parent,)))
    identity = "mid" if "mat-" in reference else "eosid"
    result = service.run_recipe(reference, dict(units="mm-t-s", params=physical, **{identity: 7}), str(source))
    assert result["status"] == "failed" and not result["artifacts"]
    assert not list((tmp_path / "work").rglob("*.k"))
    assert {p: p.read_bytes() for p in source.parent.iterdir()} == before
