"""Shared exact-integer input semantics; no deck, native process or range policy."""

from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest

from ls_prepost_mcp.domain.model._identity import exact_integer
from ls_prepost_mcp.domain.model.fields import FieldError


@pytest.mark.parametrize("value,expected", [
    (1, 1), (0, 0), (-1, -1), (10**30, 10**30), (1., 1), (-0., 0),
    ("10", 10), (" +0010 ", 10), ("-10", -10),
    (np.int64(10), 10), (np.uint64(10), 10), (np.float32(10), 10),
    (np.float64(10), 10), (Decimal("10.000"), 10), (Fraction(20, 2), 10),
])
def test_exact_scalar_forms_are_preserved_without_imposing_a_range(value, expected):
    normalized = exact_integer(value, "fixture ID")
    assert type(normalized) is int and normalized == expected


@pytest.mark.parametrize("value", [
    True, False, np.bool_(True), np.bool_(False), .25, np.float32(10.5), np.float64(10.5),
    Decimal("10.0001"), Fraction(21, 2), float("nan"), float("inf"), -float("inf"),
    np.array([10]), np.array(10), [10], None, b"10", "10.0", "&pid", "1D0", "", "not an ID",
])
def test_ambiguous_or_noninteger_inputs_never_silently_change_an_identity(value):
    with pytest.raises(FieldError, match="fixture ID must be an integer identity"):
        exact_integer(value, "fixture ID")


def test_an_arbitrary_int_protocol_cannot_hide_truncation():
    class Truncated:
        def __int__(self):
            return 10

    with pytest.raises(FieldError, match="integer identity"):
        exact_integer(Truncated(), "fixture ID")
