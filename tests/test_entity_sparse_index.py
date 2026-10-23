"""G04/G03 sparse user IDs must not allocate by maximum ID."""

import numpy as np
import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck, geometry
from ls_prepost_mcp.domain.model.selectors import resolve


def bounded_allocations(monkeypatch):
    full = np.full

    def limited(shape, *args, **kwargs):
        size = int(np.prod(shape))
        assert size <= 1_000_000, "Refused dangerous dense allocation before touching memory"
        return full(shape, *args, **kwargs)

    monkeypatch.setattr(np, "full", limited)


def test_sparse_lookup_preserves_order_missing_and_nd_connectivity_without_large_allocation(monkeypatch):
    bounded_allocations(monkeypatch)
    lookup = geometry._index(np.array([2_000_000_000, 5, 9]))
    np.testing.assert_array_equal(lookup[np.array([[5, 9], [2_000_000_000, 6]])], [[1, 2], [0, -1]])
    assert lookup.size == 2_000_000_001


def test_sparse_keyword_selector_uses_compact_id_map(tmp_path, monkeypatch):
    pytest.importorskip("ansys.dyna.core")
    bounded_allocations(monkeypatch)
    ids = [1, 2, 3, 4, 5, 6, 7, 90_000_000]
    xyz = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    path = tmp_path / "main.k"
    path.write_text(
        "*KEYWORD\n*NODE\n"
        + "".join(f"{uid},{x},{y},{z}\n" for uid, (x, y, z) in zip(ids, xyz))
        + "*ELEMENT_SOLID\n1,1,"
        + ",".join(map(str, ids))
        + "\n*END\n"
    )
    deck = KeywordDeck.load(path)
    chosen = resolve(deck, {"entity_type": "solid", "predicate": {"kind": "ids", "ids": [1]}})
    assert chosen.tolist() == [1]
    assert geometry.exterior_segments(deck).shape == (6, 4)


@pytest.mark.parametrize("ids", [np.array([1, 1]), np.array([0, 2]), np.array([1.5, 2.5])])
def test_geometry_index_rejects_duplicate_nonpositive_or_fractional_ids(ids):
    with pytest.raises(FieldError):
        geometry._index(ids)


def test_small_dense_lookup_keeps_previous_values():
    lookup = geometry._index(np.array([4, 1, 2]))
    np.testing.assert_array_equal(lookup, [-1, 1, 2, -1, 0])
