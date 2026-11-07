"""G03 reference-coordinate predicates must count each triangular shell corner once."""
from copy import deepcopy
from importlib import metadata

import numpy as np
import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck
from ls_prepost_mcp.domain.model.geometry import elements, select_elements
from ls_prepost_mcp.domain.model.selectors import resolve, selector


@pytest.fixture
def keyword_sdk():
    pytest.importorskip("ansys.dyna.core")


def _text(n4=33, quad=False):
    points = [(11, 0, 0, 0), (22, 3, 0, 0), (33, 0, 3, 0)]
    if quad:
        points.append((44, 3, 3, 0))
    lines = ["*KEYWORD", "*NODE"]
    lines += [f"{nid:8d}{x:16.8f}{y:16.8f}{z:16.8f}" for nid, x, y, z in points]
    conn = (11, 22, 44, 33) if quad else (11, 22, 33, n4)
    lines += ["*ELEMENT_SHELL", "".join(" " * 8 if v is None else f"{v:8d}" for v in (41, 7, *conn)),
              "*PART", "owned plate", f"{7:10d}{8:10d}{9:10d}",
              "*SECTION_SHELL", f"{8:10d}{2:10d}", "       0.1       0.1       0.1       0.1",
              "*MAT_ELASTIC", "         9    7.8e-9  210000.0       0.3", "*END", ""]
    return "\n".join(lines)


def _load(tmp_path, n4=33, quad=False):
    path = tmp_path / "input.k"
    path.write_bytes(_text(n4, quad).encode("ascii"))
    return path, KeywordDeck.load(path)


def _predicate(kind, center):
    if kind == "box":
        return dict(kind=kind, minimum=[center[0] - .01, center[1] - .01, -.01],
                    maximum=[center[0] + .01, center[1] + .01, .01])
    if kind == "sphere":
        return dict(kind=kind, center=center, radius=.01)
    return dict(kind="plane", origin=center, normal=[0, 1, 0], tolerance=.01)


@pytest.mark.parametrize("n4", [33, 0, None], ids=["repeat", "zero", "blank"])
@pytest.mark.parametrize("kind", ["box", "sphere", "plane"])
def test_triangle_predicates_use_three_corners_without_mutation(tmp_path, keyword_sdk, n4, kind):
    path, deck = _load(tmp_path, n4)
    before = path.read_bytes()
    conn_before = elements(deck, "*ELEMENT_SHELL", 4)[2].copy()
    refs_before = deck.references(True)
    # Handwritten oracle: the triangle (0,0), (3,0), (0,3) is centered at (1,1).
    # The former four-slot mean (.75,1.5) must not select this element.
    for center, expected in (([1, 1, 0], [41]), ([.75, 1.5, 0], [])):
        raw = dict(entity_type="shell", predicate=_predicate(kind, center))
        original_selector = deepcopy(raw)
        assert resolve(deck, raw).tolist() == expected
        assert raw == original_selector
    assert path.read_bytes() == before
    assert np.array_equal(elements(deck, "*ELEMENT_SHELL", 4)[2], conn_before)
    refs_after = deck.references(True)
    assert refs_after.defined == refs_before.defined
    assert refs_after.dangling_count == refs_before.dangling_count == 0
    assert refs_after.unverified_count == refs_before.unverified_count == 0
    assert refs_after.unchecked == refs_before.unchecked == {}


@pytest.mark.parametrize("kind", ["box", "sphere", "plane"])
def test_quad_spatial_predicates_keep_four_corner_mean(tmp_path, keyword_sdk, kind):
    path, deck = _load(tmp_path, quad=True)
    before = path.read_bytes()
    assert resolve(deck, dict(entity_type="shell", predicate=_predicate(kind, [1.5, 1.5, 0]))).tolist() == [41]
    assert resolve(deck, dict(entity_type="shell", predicate=_predicate(kind, [1, 1, 0]))).tolist() == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("n4", [33, 0, None], ids=["repeat", "zero", "blank"])
def test_legacy_triangle_box_matches_selector_without_mutation(tmp_path, keyword_sdk, n4):
    path, deck = _load(tmp_path, n4)
    before = path.read_bytes()
    conn_before = elements(deck, "*ELEMENT_SHELL", 4)[2].copy()
    refs_before = deck.references(True)
    for center, expected in (([1, 1, 0], [41]), ([.75, 1.5, 0], [])):
        predicate = _predicate("box", center)
        box = predicate["minimum"] + predicate["maximum"]
        assert select_elements(deck, "*ELEMENT_SHELL", box=box).tolist() == expected
        assert resolve(deck, dict(entity_type="shell", predicate=predicate)).tolist() == expected
    assert path.read_bytes() == before
    assert np.array_equal(elements(deck, "*ELEMENT_SHELL", 4)[2], conn_before)
    assert deck.references(True).defined == refs_before.defined


def test_legacy_quad_box_and_element_order_remain_unchanged(tmp_path, keyword_sdk):
    path, _ = _load(tmp_path, quad=True)
    # Reading order is intentionally different from sorted user-ID order.
    row = "".join(f"{v:8d}" for v in (41, 7, 11, 22, 44, 33))
    path.write_bytes(path.read_bytes().replace(row.encode(), (row.replace(f"{41:8d}", f"{81:8d}", 1) + "\n" + row).encode()))
    before = path.read_bytes()
    predicate = _predicate("box", [1.5, 1.5, 0])
    box = predicate["minimum"] + predicate["maximum"]
    assert select_elements(KeywordDeck.load(path), "*ELEMENT_SHELL", box=box).tolist() == [81, 41]
    assert path.read_bytes() == before


@pytest.mark.parametrize("n4", [33, 0, None], ids=["repeat", "zero", "blank"])
def test_triangle_identity_and_part_predicates_do_not_require_node_zero(tmp_path, keyword_sdk, n4):
    _, deck = _load(tmp_path, n4)
    for predicate in (dict(kind="all"), dict(kind="ids", ids=[41]), dict(kind="parts", ids=[7])):
        assert resolve(deck, dict(entity_type="shell", predicate=predicate)).tolist() == [41]


@pytest.mark.parametrize("n4", [99, 0, None])
def test_triangle_normalization_does_not_hide_missing_real_nodes(tmp_path, keyword_sdk, n4):
    path, _ = _load(tmp_path, n4)
    if n4 != 99:
        # A zero/blank fourth slot does not excuse a missing third corner.
        path.write_text(_text(n4).replace(f"{33:8d}{0:16.8f}{3:16.8f}{0:16.8f}\n", ""), encoding="ascii")
    deck = KeywordDeck.load(path)
    with pytest.raises(FieldError, match="undefined nodes"):
        resolve(deck, dict(entity_type="shell", predicate=dict(kind="all")))


def test_spatial_selector_contract_does_not_require_keyword_sdk_metadata(monkeypatch):
    real_version = metadata.version

    def without_sdk(name):
        if name.replace("_", "-").lower() == "ansys-dyna-core":
            raise metadata.PackageNotFoundError(name)
        return real_version(name)

    monkeypatch.setattr(metadata, "version", without_sdk)
    with pytest.raises(metadata.PackageNotFoundError):
        metadata.version("ansys-dyna-core")
    for kind in ("box", "sphere", "plane"):
        raw = dict(entity_type="shell", predicate=_predicate(kind, [1, 1, 0]))
        original = deepcopy(raw)
        chosen = selector(raw)
        assert chosen.configuration == "reference" and chosen.state is None
        assert chosen.predicate.kind == kind and raw == original
