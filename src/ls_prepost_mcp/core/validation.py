"""Shared scalar validation; legacy Service exports remain compatibility aliases."""

import math


def integer(value: int, name: str, minimum: int = 1, maximum: int = 2_000_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def numbers(values, length: int, name: str, positive: bool = False) -> list[float]:
    if len(values) != length:
        raise ValueError(f"{name} requires {length} numbers")
    converted = [float(v) for v in values]
    if not all(math.isfinite(v) and (not positive or v > 0) for v in converted):
        raise ValueError(f"Invalid {name}")
    return converted


def unit_label(units: str) -> str:
    if not isinstance(units, str) or not units.strip() or len(units) > 100:
        raise ValueError("An explicit unit-system label is required; no units are inferred")
    return units.strip()

