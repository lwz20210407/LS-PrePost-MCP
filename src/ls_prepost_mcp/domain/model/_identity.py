"""Lossless identity-input normalization, not keyword text decoding or range policy."""

import numpy as np

from .fields import FieldError


def exact_integer(value: object, name: str) -> int:
    """Return a Python int without truncating a numeric scalar or accepting a flag.

    Integer strings and exact integer-valued scalars retain the existing model
    input forms. A field's caller separately decides positivity, zero and range.
    This function performs no filesystem access and does not parse keyword cards.
    """
    if isinstance(value, (bool, np.bool_, np.ndarray)):
        raise FieldError(f"{name} must be an integer identity, not a Boolean or array")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise FieldError(f"{name} must be an integer identity") from error
    if not isinstance(value, str) and value != result:
        raise FieldError(f"{name} must be an integer identity; fractional values cannot select an entity")
    return result
