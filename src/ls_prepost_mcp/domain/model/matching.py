"""Typed scalar equality shared by model selection and semantic comparison.

The type comes from the existing AST layout, never from the spelling of the
value. An integer-looking Young's modulus is still a continuous float field.
"""
from __future__ import annotations

import math

from ._identity import exact_integer


def scalar_equal(actual: object, expected: object, kind: str | None = None, *,
                 mode: str = "compare", rel_tol: float = 1e-9, abs_tol: float = 0.0) -> bool:
    """Compare a known integer exactly while keeping each caller's text policy.

    ``find`` historically case-folds and converts mixed string/value queries to
    text. ``compare`` trims strings but remains case-sensitive. This function
    does not decode cards, resolve parameters or impose positivity/range rules.
    Boolean provider flags are not integer identities; no new Flag decoding is
    introduced here.
    """
    if mode not in ("find", "compare"):
        raise ValueError("Unknown model scalar comparison policy")
    if kind == "int":
        if expected is None:
            return actual is None
        wanted = exact_integer(expected, "Integer field query")
        return actual is not None and exact_integer(actual, "Integer field value") == wanted
    if mode == "find":
        if isinstance(expected, str) or isinstance(actual, str):
            return str(actual).strip().lower() == str(expected).strip().lower()
        if actual is None or expected is None:
            return actual is expected
        return math.isclose(float(actual), float(expected), rel_tol=rel_tol, abs_tol=abs_tol)
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and not isinstance(actual, bool):
        return math.isclose(float(actual), float(expected), rel_tol=rel_tol, abs_tol=abs_tol)
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.strip() == expected.strip()
    return actual == expected
