"""Selector's legacy coercion must not silently turn booleans into entity identities."""
from copy import deepcopy

import pytest

from ls_prepost_mcp.domain.model.selectors import selector


@pytest.mark.parametrize("predicate", [
    dict(kind="ids", ids=[True]),
    dict(kind="parts", ids=[True]),
    dict(kind="sets", set_type="node", ids=[True]),
    dict(kind="surface", part_ids=[True]),
    dict(kind="boolean", operator="union", operands=[dict(kind="ids", ids=[True]), dict(kind="none")]),
])
def test_selector_rejects_bool_in_every_identity_predicate(predicate):
    with pytest.raises(ValueError):
        selector(dict(entity_type="node", predicate=predicate))


def test_selector_rejects_boolean_state_identity():
    with pytest.raises(ValueError):
        selector(dict(entity_type="node", predicate=dict(kind="all"), configuration="deformed", state=True))


@pytest.mark.parametrize("values", [[1, 2], [1.0, 2.0], ["1", "2"]])
def test_legacy_exact_integer_structures_still_normalize_without_mutating_input(values):
    raw = dict(entity_type="node", predicate=dict(kind="ids", ids=values))
    before = deepcopy(raw)
    assert selector(raw).predicate.ids == (1, 2)
    assert raw == before
