"""Tiny coordinate round-off: detection, and the move-far-and-back cleanup used in LS-PrePost.

Noise is a coordinate that differs from a value it should equal by far less than the model
size (``rel_tol`` x size, default 1e-9): a near-zero value (0 < |x| <= tol), a broken mirror
pair (0 < |x + y| <= tol) or a split plane (distinct values closer than tol). Translating
there and back is a common source, because x + d - d is not x in floating point.

The cleanup follows the LS-PrePost practice (Transform: move along the noisy direction by a
very large D, then back). In double precision x + D - D rounds x to a multiple of ulp(D): noise
below half a grid step disappears, +x/-x pairs become exactly symmetric and near-zero values
become 0. Every other coordinate also moves by at most half a grid step; that bound and the
largest actual change are reported. The shift is computed once in memory and written once,
so no intermediate text rounding is added.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from .fields import FieldError
from .geometry import _node_block, nodes
from .mesh import _apply, _plan_rows

if TYPE_CHECKING:
    from .deck import KeywordDeck

AXES = "xyz"


def _mirror_partners(unique: np.ndarray, tol: float) -> tuple[np.ndarray, np.ndarray]:
    """Positive values and negative values that form near-but-not-exact mirror pairs."""
    positive = unique[unique > tol]
    magnitudes = np.sort(-unique[unique < -tol])
    if not positive.size or not magnitudes.size:
        return np.empty(0), np.empty(0)
    exact = np.isin(positive, magnitudes)
    near = np.searchsorted(magnitudes, positive)
    hits_pos, hits_neg = [], []
    for candidate in (near - 1, near):
        valid = (candidate >= 0) & (candidate < magnitudes.size)
        partner = magnitudes[np.clip(candidate, 0, magnitudes.size - 1)]
        gap = np.abs(positive - partner)
        hit = valid & ~exact & (gap > 0) & (gap <= tol)
        hits_pos.append(positive[hit])
        hits_neg.append(-partner[hit])
    return np.unique(np.concatenate(hits_pos)), np.unique(np.concatenate(hits_neg))


def _axis_noise(values: np.ndarray, tol: float) -> tuple[np.ndarray, dict]:
    """Mask of noisy nodes on one axis and its summary."""
    near_zero = (values != 0) & (np.abs(values) <= tol)
    unique = np.unique(values)
    gaps = np.diff(unique)
    close = np.flatnonzero(gaps <= tol)
    split = np.union1d(unique[close], unique[close + 1])
    mirror_pos, mirror_neg = _mirror_partners(unique, tol)
    mask = near_zero | np.isin(values, split) | np.isin(values, mirror_pos) | np.isin(values, mirror_neg)
    deviations = [np.abs(values[near_zero]).max() if near_zero.any() else 0.0, gaps[close].max() if close.size else 0.0]
    if mirror_pos.size:
        deviations.append(float(np.max([np.min(np.abs(p + mirror_neg)) for p in mirror_pos])))
    return mask, {"near_zero": int(near_zero.sum()), "split_values": int(split.size),
                  "broken_mirror_pairs": int(mirror_pos.size), "nodes": int(mask.sum()),
                  "max_deviation": float(max(deviations))}


def coordinate_noise(deck: KeywordDeck, rel_tol: float = 1e-9, max_report: int = 20) -> dict:
    """Read-only report of tiny coordinate round-off per axis (see the module docstring)."""
    ids, xyz = nodes(deck)
    if not ids.size:
        return {"nodes": 0, "noisy_axes": [], "nodes_affected": 0, "axes": {}}
    size = float(np.ptp(xyz, axis=0).max()) or float(np.abs(xyz).max()) or 1.0
    tol = rel_tol * size
    axes, any_noise = {}, np.zeros(ids.size, dtype=bool)
    for i, axis in enumerate(AXES):
        mask, summary = _axis_noise(xyz[:, i], tol)
        axes[axis] = {**summary, "sample_nodes": ids[mask][:max_report].tolist()}
        any_noise |= mask
    return {"nodes": int(ids.size), "model_size": size, "tolerance": tol,
            "noisy_axes": [axis for axis in AXES if axes[axis]["nodes"]], "nodes_affected": int(any_noise.sum()),
            "axes": axes}


def _magnitude(largest: float, deviation: float, tol: float) -> float:
    """``1.5 * 2**k``: every x + D stays inside the one binade [2**k, 2**(k+1)), so positive and
    negative coordinates are rounded on the same grid. (With D = 2**k, D - |x| falls in the binade
    below, whose grid is twice as fine, and mirror pairs come out unequal.) The grid step 2**(k-52)
    is >= 200 x the noise and >= 1e4 x the largest coordinate's ulp, but never coarser than the
    detection tolerance (coordinates move by at most half a step)."""
    step = max(200.0 * deviation, 1e4 * math.ulp(largest or 1.0))
    exponent = math.ceil(math.log2(step))
    if 2.0 ** exponent > tol:
        exponent = math.floor(math.log2(tol))
    k = max(exponent + 52, math.ceil(math.log2(2 * (largest or 1.0))) + 1)  # |x| <= 2**(k-2) < 2**(k-1)
    return 1.5 * 2.0 ** k


def _one_binade(shift: float, largest: float) -> bool:
    """x + shift for |x| <= largest lies in one binade, i.e. on one uniform grid."""
    return math.frexp(shift - largest)[1] == math.frexp(shift + largest)[1]


def clean_coordinates(deck: KeywordDeck, axes: str | None = None, magnitude: float | None = None,
                      rel_tol: float = 1e-9) -> dict:
    """Move the noisy axes by ``magnitude`` and back (x + D - D), writing only changed coordinates.

    ``axes`` defaults to the axes where :func:`coordinate_noise` finds noise; ``magnitude``
    defaults to 1.5 x a power of two chosen from the detected deviation (see :func:`_magnitude`);
    a given magnitude whose x + D range straddles a power of two is refused.
    """
    before = coordinate_noise(deck, rel_tol)
    axes = axes if axes is not None else "".join(before["noisy_axes"])
    if not axes:
        return {"axes": "", "changed_nodes": 0, "noise_before": before, "note": "no coordinate noise found"}
    if set(axes) - set(AXES):
        raise FieldError("axes must be letters from 'xyz'")
    _, all_xyz = nodes(deck)
    largest = float(np.abs(all_xyz).max())
    deviation = max(before["axes"][axis]["max_deviation"] for axis in axes)
    shift = float(magnitude) if magnitude else _magnitude(largest, deviation, before["tolerance"])
    if shift <= 2 * largest:
        raise FieldError(f"magnitude {shift:g} must be much larger than the largest coordinate {largest:g}")
    if not _one_binade(shift, largest):
        suggestion = 1.5 * 2.0 ** math.frexp(shift)[1]
        raise FieldError(f"magnitude {shift:g} +/- {largest:g} straddles a power of two, so positive and negative "
                         f"coordinates would be rounded on different grids (mirror pairs broken); use e.g. "
                         f"{suggestion:g}")
    plans, changed, biggest = [], 0, 0.0
    for block in deck.blocks("*NODE"):
        keys, xyz = _node_block(deck, block)
        updates: dict[int, dict[str, object]] = {}
        for i, axis in enumerate(AXES):
            if axis not in axes:
                continue
            column = xyz[:, i]
            moved = (column + shift) - shift
            for row in np.flatnonzero(moved != column):
                updates.setdefault(int(keys[row]), {})[axis] = float(moved[row])
                biggest = max(biggest, abs(float(moved[row] - column[row])))
        if updates:
            edits, _ = _plan_rows(deck, block, deck.layout(block).rows, updates, "float")
            plans.append((block, edits))
            changed += len(updates)
    _apply(deck, plans, f"clean coordinate round-off ({axes}: move {shift:g} and back)")
    return {"axes": axes, "magnitude": shift, "grid_step": math.ulp(shift), "bound": math.ulp(shift) / 2,
            "max_change": biggest, "changed_nodes": changed, "noise_before": before,
            "noise_after": coordinate_noise(deck, rel_tol)}


__all__ = ["clean_coordinates", "coordinate_noise"]
