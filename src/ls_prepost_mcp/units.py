"""Small explicit mechanical-unit algebra. No inferred solver units or affine conversions."""

import math
import re
from dataclasses import dataclass
from fractions import Fraction

# Dimensions are length, mass, time. Scales are exact rational SI factors.
BASE = {
    "1": ((0, 0, 0), 1),
    "dimensionless": ((0, 0, 0), 1),
    "%": ((0, 0, 0), Fraction(1, 100)),
    "microstrain": ((0, 0, 0), Fraction(1, 1000000)),
    "m": ((1, 0, 0), 1),
    "cm": ((1, 0, 0), Fraction(1, 100)),
    "mm": ((1, 0, 0), Fraction(1, 1000)),
    "um": ((1, 0, 0), Fraction(1, 1000000)),
    "kg": ((0, 1, 0), 1),
    "g": ((0, 1, 0), Fraction(1, 1000)),
    "tonne": ((0, 1, 0), 1000),
    "s": ((0, 0, 1), 1),
    "ms": ((0, 0, 1), Fraction(1, 1000)),
    "us": ((0, 0, 1), Fraction(1, 1000000)),
    "ns": ((0, 0, 1), Fraction(1, 1000000000)),
    "N": ((1, 1, -2), 1),
    "kN": ((1, 1, -2), 1000),
    "MN": ((1, 1, -2), 1000000),
    "Pa": ((-1, 1, -2), 1),
    "kPa": ((-1, 1, -2), 1000),
    "MPa": ((-1, 1, -2), 1000000),
    "GPa": ((-1, 1, -2), 1000000000),
    "J": ((2, 1, -2), 1),
    "kJ": ((2, 1, -2), 1000),
    "mJ": ((2, 1, -2), Fraction(1, 1000)),
}
TOKEN = re.compile(r"([A-Za-z%]+|1)(?:\^(-?\d+))?")


@dataclass(frozen=True)
class Unit:
    label: str
    dimensions: tuple[int, int, int]
    scale: Fraction

    @classmethod
    def parse(cls, label):
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 100:
            raise ValueError("An explicit supported unit is required")
        normalized = label.strip().replace("µ", "u").replace("μ", "u")
        if any(c.isspace() for c in normalized):
            raise ValueError("Use explicit * and / without internal whitespace in unit expressions")
        parts = re.split(r"([*/])", normalized)
        if len(parts) > 15:
            raise ValueError("Unit expression exceeds eight terms")
        dimensions = [0, 0, 0]
        scale = Fraction(1)
        sign = 1
        for index, part in enumerate(parts):
            if index % 2:
                sign = 1 if part == "*" else -1
                continue
            match = TOKEN.fullmatch(part)
            if not match or match[1] not in BASE:
                raise ValueError("Unsupported unit term: " + part)
            power = int(match[2] or 1)
            if not -6 <= power <= 6:
                raise ValueError("Unit powers must be between -6 and 6")
            power *= sign
            dims, factor = BASE[match[1]]
            dimensions = [a + power * b for a, b in zip(dimensions, dims)]
            scale *= Fraction(factor) ** power
        try:
            numeric = float(scale)
        except OverflowError as exc:
            raise ValueError("Unit scale exceeds floating-point range") from exc
        if not math.isfinite(numeric) or numeric <= 0:
            raise ValueError("Unit scale exceeds floating-point range")
        return cls(label.strip(), tuple(dimensions), scale)

    def factor_to(self, other):
        if self.dimensions != other.dimensions:
            raise ValueError("Incompatible unit dimensions: " + self.label + " -> " + other.label)
        try:
            factor = float(self.scale / other.scale)
        except OverflowError as exc:
            raise ValueError("Unit conversion exceeds floating-point range") from exc
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("Unit conversion exceeds floating-point range")
        return factor


def curve_conversion(time_unit, value_unit, target_time_unit, target_value_unit):
    source_time, source_value = Unit.parse(time_unit), Unit.parse(value_unit)
    target_time, target_value = Unit.parse(target_time_unit), Unit.parse(target_value_unit)
    if source_time.dimensions != (0, 0, 1) or target_time.dimensions != (0, 0, 1):
        raise ValueError("Curve time units must have time dimensions")
    time_ratio, value_ratio = source_time.scale / target_time.scale, source_value.scale / target_value.scale
    return dict(
        source_time_unit=source_time.label,
        source_value_unit=source_value.label,
        target_time_unit=target_time.label,
        target_value_unit=target_value.label,
        time_factor=source_time.factor_to(target_time),
        value_factor=source_value.factor_to(target_value),
        exact_time_factor=dict(numerator=str(time_ratio.numerator), denominator=str(time_ratio.denominator)),
        exact_value_factor=dict(
            numerator=str(value_ratio.numerator), denominator=str(value_ratio.denominator)
        ),
        sample_arithmetic="binary floating point; nonfinite/underflow/collapsed time rejected",
        value_dimensions=dict(zip(("length", "mass", "time"), target_value.dimensions)),
        dimensional_compatibility_checked=True,
        source_unit_labels_verified=False,
        scope="Multiplicative conversion of explicitly declared units; no inferred LS-DYNA unit system, temperature offsets or quantity interpretation",
    )
