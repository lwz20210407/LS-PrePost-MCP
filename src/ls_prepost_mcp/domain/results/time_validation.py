"""Validate reader time metadata without repairing, sorting or truncating state arrays."""
import numpy as np


def validate_d3plot_times(values) -> np.ndarray:
    """Fail closed on corrupt metadata, including LASSO 2.0.4 EOF tail states.

    Negative start times and repeated times are valid. A decrease is ambiguous
    for state selection; report it instead of silently rearranging the family.
    Empty metadata is allowed for geometry-only inventories.
    """
    times = np.asarray(values, dtype=float)
    prefix = "Invalid d3plot time axis: "
    if times.ndim != 1:
        raise ValueError(prefix + "expected one-dimensional state metadata")
    invalid = np.flatnonzero(~np.isfinite(times))
    if invalid.size:
        raise ValueError(prefix + f"nonfinite time at state {int(invalid[0]) + 1} (1-based)")
    marker = np.flatnonzero(times == -999999.)
    if marker.size:
        raise ValueError(prefix + f"EOF marker reported as time at state {int(marker[0]) + 1} (1-based); "
                         "possible trailing data after the end marker; no states were removed")
    reversals = np.flatnonzero(times[1:] < times[:-1])
    if reversals.size:
        raise ValueError(prefix + f"time decreases at state {int(reversals[0]) + 2} (1-based); "
                         "state ordering is ambiguous; no states were reordered")
    return times
