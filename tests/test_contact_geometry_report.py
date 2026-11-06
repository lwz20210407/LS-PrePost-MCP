"""Opt-in bounded host geometry candidates; never a native Contact Check claim."""
import hashlib

import numpy as np
import pytest

pytest.importorskip("ansys.dyna.core")

from ls_prepost_mcp.config import Settings  # noqa: E402
from ls_prepost_mcp.domain.model import KeywordDeck, contact, contact_report  # noqa: E402
from ls_prepost_mcp.service import Service  # noqa: E402


@pytest.fixture
def model(tmp_path):
    xyz = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (.8, .8, .8), (.1, .1, .1)]
    rows = ["*KEYWORD", "*PART", "tetrahedron", "         1         1         1", "*SECTION_SOLID", "         1         1",
            "*MAT_ELASTIC", "         1         1         1       0.3", "*NODE"]
    rows += [f"{index:>8}" + "".join(f"{float(value):>16g}" for value in point) for index, point in enumerate(xyz, 1)]
    rows += ["*ELEMENT_SOLID", "".join(f"{value:>8}" for value in (1, 1, 1, 2, 3, 4, 4, 4, 4, 4)),
             "*SET_NODE_LIST", "         9", "         5         6",
             "*CONTACT_AUTOMATIC_NODES_TO_SURFACE", "         9         1         4         3", "", "", "*END"]
    path = tmp_path / "tetra.k"
    path.write_text("\n".join(rows) + "\n", encoding="ascii", newline="\n")
    return path, Service(Settings(tmp_path / "work", allowed_roots=(tmp_path,)))


def test_opt_in_uses_true_tetrahedron_not_only_its_axis_aligned_box(model):
    path, service = model
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = service.check_model(str(path), contact_geometry={})
    assert result["status"] == "succeeded"
    report = result["data"]["contact_geometry"]
    assert report["method"] == "keyword_triangle_gap" and report["native_verified"] is False
    # Node5 is inside [0,1]^3 but x+y+z>1; node6 is inside the actual tetrahedron.
    assert [row["node"] for row in report["candidates"]] == [6]
    assert report["candidates"][0]["depth"] == pytest.approx(.1)
    assert report["coverage"]["evaluated_contacts"] == 1 and not report["not_checked"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_default_and_explicit_none_do_not_call_contact_geometry(model, monkeypatch):
    path, service = model
    monkeypatch.setattr(contact, "check_penetration", lambda *a, **kw: pytest.fail("Opt-in only"))
    original = service.check_model(str(path), None, None, True)
    assert "contact_geometry" not in original["data"]
    assert service.check_model(str(path), contact_geometry=None) == original


def test_candidates_only_add_warning_and_never_an_objective_defect(model):
    path, service = model
    baseline = service.check_model(str(path))
    result = service.check_model(str(path), contact_geometry={})
    assert result["data"]["errors"] == baseline["data"]["errors"]
    assert result["checks"] == baseline["checks"]
    assert result["warnings"] and any("geometr" in item.lower() for item in result["warnings"])


@pytest.mark.parametrize("options", [False, True, [], "on", 0, {"enabled": True}, {"unknown": 1},
    {"tolerance": True}, {"tolerance": -1}, {"tolerance": float("nan")}, {"tolerance": float("inf")}, {"tolerance": 10**1000},
    {"max_contacts": True}, {"max_contacts": 0}, {"max_contacts": 101}, {"max_slave_nodes": 100001},
    {"max_master_triangles": 200001}, {"max_cells": 1000001}, {"max_pairs": 1000001},
    {"max_pairs": 1.0}, {"max_report": 51}, {"max_report": -1}])
def test_bad_options_reject_before_loading_any_deck(model, monkeypatch, options):
    path, service = model
    monkeypatch.setattr(KeywordDeck, "load", lambda *a, **kw: pytest.fail("Validate options before deck IO"))
    result = service.check_model(str(path), contact_geometry=options)
    assert result["status"] == "failed" and result["error"]


def test_explicit_geometry_conflicts_with_include_mesh_false_before_io(model, monkeypatch):
    path, service = model
    monkeypatch.setattr(KeywordDeck, "load", lambda *a, **kw: pytest.fail("Conflict must precede deck IO"))
    result = service.check_model(str(path), include_mesh=False, contact_geometry={})
    assert result["status"] == "failed"


def test_opt_in_reuses_the_one_loaded_deck(model, monkeypatch):
    path, service = model
    original = KeywordDeck.load
    calls = []

    def load(*a, **kw):
        result = original(*a, **kw)
        calls.append(result)
        return result

    monkeypatch.setattr(KeywordDeck, "load", load)
    assert service.check_model(str(path), contact_geometry={})["status"] == "succeeded"
    assert len(calls) == 1


def estimate(model, **options):
    return contact_report.estimate(KeywordDeck.load(model[0]), contact_report.options(options, True))


def test_zero_report_limit_still_evaluates_and_counts_candidates(model):
    report = estimate(model, max_report=0)
    assert report["coverage"]["candidate_nodes_found"] == 1
    assert report["coverage"]["evaluated_contacts"] == 1
    assert report["candidates"] == []


def test_tolerance_uses_model_coordinates_and_filters_the_candidate(model):
    report = estimate(model, tolerance=.11)
    assert report["evaluated"][0]["penetrating"] == 0
    assert report["units"] == "model_coordinates"
    assert not report["candidates"]


@pytest.mark.parametrize("keyword", ["*CONTACT_AUTOMATIC_SINGLE_SURFACE", "*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE_MORTAR"])
def test_unsupported_and_single_surface_are_not_checked(model, keyword):
    path, _ = model
    path.write_text(path.read_text().replace("*CONTACT_AUTOMATIC_NODES_TO_SURFACE", keyword), encoding="ascii")
    report = estimate(model)
    assert report["not_checked"][0]["checked"] is False
    assert "unsupported" in report["not_checked"][0]["reason"]
    assert report["coverage"]["evaluated_contacts"] == 0
    assert "penetrating" not in report["not_checked"][0]


def test_unsupported_surface_type_is_not_checked(model):
    path, _ = model
    path.write_text(path.read_text().replace("         9         1         4         3", "         9         1         4         5"), encoding="ascii")
    assert "surface types" in estimate(model)["not_checked"][0]["reason"]


def test_missing_master_and_empty_slave_are_not_false_zero(model):
    path, _ = model
    path.write_text(path.read_text().replace("         9         1         4         3", "         9        99         4         3"), encoding="ascii")
    row = estimate(model)["not_checked"][0]
    assert row["checked"] is False and "Empty" in row["reason"]
    assert "penetrating" not in row and "max_depth" not in row


@pytest.mark.parametrize("field,limit,reason", [("max_slave_nodes", 1, "max_slave_nodes"),
    ("max_master_triangles", 1, "max_master_triangles"), ("max_cells", 1, "max_cells"), ("max_pairs", 1, "max_pairs")])
def test_each_calculation_budget_reports_not_checked(model, field, limit, reason):
    report = estimate(model, **{field: limit})
    assert reason in report["not_checked"][0]["reason"]
    assert report["not_checked"][0]["checked"] is False
    assert not report["evaluated"] and not report["candidates"]


def test_contact_limit_aggregates_omissions_without_running_kernel(model, monkeypatch):
    path, _ = model
    text = path.read_text()
    card = text[text.index("*CONTACT_"):text.index("*END")]
    path.write_text(text.replace("*END", card * 3 + "*END"), encoding="ascii")
    report = estimate(model, max_contacts=1)
    assert report["coverage"]["total_contacts"] == 4
    assert report["coverage"]["evaluated_contacts"] == 1
    assert report["coverage"]["not_checked_contacts"] == 3
    assert report["not_checked"][0]["omitted_contacts"] == 3


def test_far_slave_is_unsearched_and_not_a_zero_result(model):
    path, _ = model
    text = path.read_text()
    text = text.replace("             0.8             0.8             0.8", "             100             100             100")
    path.write_text(text, encoding="ascii")
    report = estimate(model)
    assert report["not_checked"][0]["coverage"]["unsearched_slave_nodes"] == 1
    assert report["not_checked"][0]["checked"] is False
    assert report["candidates"][0]["node"] == 6
    assert report["coverage"]["candidate_nodes_found"] == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_geometry_is_not_checked(model, monkeypatch, value):
    real_nodes = contact.nodes

    def bad_nodes(deck):
        ids, xyz = real_nodes(deck)
        xyz[0, 0] = value
        return ids, xyz

    monkeypatch.setattr(contact, "nodes", bad_nodes)
    assert "Non-finite" in estimate(model)["not_checked"][0]["reason"]


def test_degenerate_master_is_not_checked(model, monkeypatch):
    monkeypatch.setattr(contact, "_surface", lambda *a, **kw: (np.array([[1, 1, 1, 1]]), np.zeros(1), np.zeros(1, dtype=bool)))
    assert "Degenerate" in estimate(model)["not_checked"][0]["reason"]


def test_pair_budget_precedes_pair_repeat_and_narrow_phase(model, monkeypatch):
    repeat = np.repeat

    def guarded_repeat(values, count, *args, **kwargs):
        if values.ndim == 1 and np.array_equal(values, np.arange(2)):
            pytest.fail("Pair repeat must be refused before expansion")
        return repeat(values, count, *args, **kwargs)

    monkeypatch.setattr(contact.np, "repeat", guarded_repeat)
    assert "max_pairs" in estimate(model, max_pairs=1)["not_checked"][0]["reason"]


@pytest.mark.parametrize("high", [1e20, float("inf"), float("nan")])
def test_cell_budget_and_overflow_guard_precede_repeat(monkeypatch, high):
    monkeypatch.setattr(contact.np, "repeat", lambda *a, **kw: pytest.fail("Cell repeat must not run"))
    budget = contact.GeometryBudget(contact.HARD_LIMITS)
    with pytest.raises(contact.GeometryBudgetError):
        contact._cells(np.zeros((1, 3)), np.full((1, 3), high), 1.0, budget)


def test_cell_product_cannot_overflow_into_a_small_allocation(monkeypatch):
    monkeypatch.setattr(contact.np, "repeat", lambda *a, **kw: pytest.fail("Cell repeat must not run"))
    budget = contact.GeometryBudget(contact.HARD_LIMITS)
    with pytest.raises(contact.GeometryBudgetError, match="max_cells"):
        contact._cells(np.zeros((1, 3)), np.full((1, 3), 2**30), 1.0, budget)


@pytest.mark.parametrize("keyword", ["*ELEMENT_SOLID", "*ELEMENT_SOLID_ORTHO"])
def test_surface_budget_precedes_existing_face_expansion(model, monkeypatch, keyword):
    path, _ = model
    text = path.read_text().replace("*ELEMENT_SOLID", keyword)
    if keyword == "*ELEMENT_SOLID_ORTHO":
        head, body = text.split(keyword + "\n", 1)
        element, tail = body.split("\n", 1)
        text = head + keyword + "\n" + element[:16] + "\n" + element[16:] + "\n0\n0\n" + tail
    path.write_text(text, encoding="ascii")
    monkeypatch.setattr(contact, "exterior_segments", lambda *a, **kw: pytest.fail("Face expansion must not run"))
    assert "max_master_triangles" in estimate(model, max_master_triangles=1)["not_checked"][0]["reason"]
