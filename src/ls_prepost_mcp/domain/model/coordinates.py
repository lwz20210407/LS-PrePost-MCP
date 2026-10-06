"""Tiny coordinate round-off: detection, one-pass cleanup, and the LS-PrePost move-far-and-back.

Noise is a coordinate that differs from a value it should equal by far less than the model size
(tol = ``rel_tol`` x size, default 1e-9, at least 4096 ulp of the largest coordinate): a
near-zero value (0 < |x| <= tol), a broken mirror pair (0 < |x + y| <= tol) or a split plane
(distinct values closer than tol). Sources: translating there and back (x + d - d is not x),
cos/sin, CAD exports with float32-level noise.

Detection and cleanup work per axis on the magnitudes |x| (signs together, so mirror pairs are
handled with planes): sorted magnitudes chained by gaps <= tol form a cluster, a one-dimensional
single-linkage that has no grid and therefore no values straddling a grid point. A cluster is
noise when it holds several magnitudes or reaches 0; one wider than SNAP_SPAN x tol is left
alone. On a dense axis (expected chance pairs n^2 tol / R >= 1, e.g. an unstructured mesh with a
million distinct coordinates) a cluster also needs evidence (it reaches 0, holds both signs, a
member is shared by two or more nodes, or it spans at most 4096 ulp); the others are reported as
rejected, not changed.

The cleanup gives every member of a noisy cluster the decimal with the fewest significant digits
inside the cluster's range (0 when it reaches 0, written as +0.0), with its own sign: one pass is
enough (the gaps to other values stay above tol), mirror pairs become exact, values outside
clusters keep their bytes. This follows the open-source mesh libraries (VTK, trimesh, CGAL,
OpenFOAM, SMESH, ...: neighbourhood queries, no global quantisation); see the research note of
2026-10-06 in temp/20261006-node-tolerance-research.

:func:`quantize_coordinates` keeps the LS-PrePost practice (Transform: move along the noisy
direction by a very large D, then back): x + D - D rounds every value of the axis to a binary
grid of ulp(D). It rewrites clean values too (3.3 -> 3.2999999970197678 on a coarse grid) and
cannot join values on either side of a grid point, so it is an explicit operation, not the
default cleanup.
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
SNAP_SPAN = 1000  # x tol (1e-6 of the model size): a chain of gaps <= tol this wide is still round-off
ULP_FLOOR = 4096  # tol >= this many ulp of the largest coordinate; also the "pure arithmetic" span


def _tolerance(xyz: np.ndarray, rel_tol: float) -> tuple[float, float]:
    size = float(np.ptp(xyz, axis=0).max()) or float(np.abs(xyz).max()) or 1.0
    return size, max(rel_tol * size, ULP_FLOOR * math.ulp(float(np.abs(xyz).max()) or 1.0))


def _cleanest(low: float, high: float) -> float:
    """The decimal with the fewest significant digits inside [low, high]."""
    middle = (low + high) / 2
    for digits in range(1, 18):
        candidate = float(f"{middle:.{digits}g}")
        if low <= candidate <= high:
            return candidate
    return middle


def _axis_clusters(values: np.ndarray, tol: float) -> dict:
    """Clusters of one axis: per unique magnitude its target (NaN = untouched) and the summary."""
    magnitudes, inverse, counts = np.unique(np.abs(values), return_inverse=True, return_counts=True)
    positive = np.zeros(magnitudes.size, dtype=bool)
    negative = np.zeros(magnitudes.size, dtype=bool)
    positive[inverse[~np.signbit(values)]] = True
    negative[inverse[np.signbit(values)]] = True
    target = np.full(magnitudes.size, np.nan)
    summary = {"near_zero": 0, "split_values": 0, "broken_mirror_pairs": 0, "rejected_clusters": 0,
               "max_deviation": 0.0}
    if not magnitudes.size:
        return {"magnitudes": magnitudes, "inverse": inverse, "target": target, **summary}
    span_range = float(magnitudes[-1] - magnitudes[0]) or 1.0
    dense = magnitudes.size ** 2 * tol / span_range >= 1.0
    breaks = np.flatnonzero(np.diff(magnitudes) > tol) + 1
    for start, end in zip(np.concatenate([[0], breaks]), np.concatenate([breaks, [magnitudes.size]])):
        low, high = float(magnitudes[start]), float(magnitudes[end - 1])
        zero = low <= tol and high > 0
        if end - start < 2 and not zero:
            continue
        if high - low > SNAP_SPAN * tol:
            summary["rejected_clusters"] += 1
            continue
        both = bool(positive[start:end].any() and negative[start:end].any())
        evidence = zero or both or bool((counts[start:end] >= 2).any()) or high - low <= ULP_FLOOR * math.ulp(high)
        if dense and not evidence:
            summary["rejected_clusters"] += 1
            continue
        target[start:end] = 0.0 if zero else _cleanest(low, high)
        nonzero = magnitudes[start:end] > 0
        summary["near_zero"] += int(counts[start:end][nonzero & (magnitudes[start:end] <= tol)].sum()) if zero else 0
        summary["split_values"] += sum(int(sign[start:end].sum()) for sign in (positive, negative)
                                       if sign[start:end].sum() >= 2)
        summary["broken_mirror_pairs"] += int(both and end - start >= 2)
        summary["max_deviation"] = max(summary["max_deviation"], high - low if not zero else high)
    return {"magnitudes": magnitudes, "inverse": inverse, "target": target, **summary}


def _axis_noise(values: np.ndarray, tol: float) -> tuple[np.ndarray, dict]:
    """Mask of noisy nodes on one axis (members of a noisy cluster) and its summary."""
    clusters = _axis_clusters(values, tol)
    mask = ~np.isnan(clusters["target"][clusters["inverse"]])
    summary = {k: clusters[k] for k in ("near_zero", "split_values", "broken_mirror_pairs", "rejected_clusters",
                                        "max_deviation")}
    return mask, {**summary, "nodes": int(mask.sum())}


def coordinate_noise(deck: KeywordDeck, rel_tol: float = 1e-9, max_report: int = 20) -> dict:
    """Read-only report of tiny coordinate round-off per axis (see the module docstring)."""
    ids, xyz = nodes(deck)
    if not ids.size:
        return {"nodes": 0, "noisy_axes": [], "nodes_affected": 0, "axes": {}}
    size, tol = _tolerance(xyz, rel_tol)
    axes, any_noise = {}, np.zeros(ids.size, dtype=bool)
    for i, axis in enumerate(AXES):
        mask, summary = _axis_noise(xyz[:, i], tol)
        axes[axis] = {**summary, "sample_nodes": ids[mask][:max_report].tolist()}
        any_noise |= mask
    return {"nodes": int(ids.size), "model_size": size, "tolerance": tol,
            "noisy_axes": [axis for axis in AXES if axes[axis]["nodes"]], "nodes_affected": int(any_noise.sum()),
            "axes": axes}


def _rewrite(deck: KeywordDeck, axes: str, new_values, description: str) -> tuple[int, float]:
    """Write ``new_values(axis, column) -> column`` for the given axes, changed rows only."""
    plans, changed, biggest = [], 0, 0.0
    for block in deck.blocks("*NODE"):
        keys, xyz = _node_block(deck, block)
        updates: dict[int, dict[str, object]] = {}
        for i, axis in enumerate(AXES):
            if axis not in axes:
                continue
            column = xyz[:, i]
            moved = new_values(axis, column)
            differs = (moved != column) | (np.signbit(moved) != np.signbit(column))
            for row in np.flatnonzero(differs):
                updates.setdefault(int(keys[row]), {})[axis] = float(moved[row])
                biggest = max(biggest, abs(float(moved[row] - column[row])))
        if updates:
            edits, _ = _plan_rows(deck, block, deck.layout(block).rows, updates, "float")
            plans.append((block, edits))
            changed += len(updates)
    _apply(deck, plans, description)
    return changed, biggest


def _axes(before: dict, axes: str | None) -> str:
    axes = axes if axes is not None else "".join(before["noisy_axes"])
    if set(axes) - set(AXES):
        raise FieldError("axes must be letters from 'xyz'")
    return axes


def clean_coordinates(deck: KeywordDeck, axes: str | None = None, rel_tol: float = 1e-9) -> dict:
    """Give every member of a noisy cluster its cluster value (sign kept); one pass, idempotent.

    ``axes`` defaults to the axes where :func:`coordinate_noise` finds noise. Only coordinates in
    noisy clusters change, by at most the cluster span; everything else keeps its bytes.
    """
    before = coordinate_noise(deck, rel_tol)
    axes = _axes(before, axes)
    if not axes:
        return {"axes": "", "changed_nodes": 0, "noise_before": before, "note": "no coordinate noise found"}
    tol = before["tolerance"]
    _, all_xyz = nodes(deck)
    maps, snapped, rejected = {}, {}, {}
    for i, axis in enumerate(AXES):
        if axis in axes:
            clusters = _axis_clusters(all_xyz[:, i], tol)
            keep = ~np.isnan(clusters["target"])
            maps[axis] = (clusters["magnitudes"][keep], clusters["target"][keep])
            snapped[axis] = int(np.count_nonzero(clusters["magnitudes"][keep] != clusters["target"][keep]))
            rejected[axis] = clusters["rejected_clusters"]

    def new_values(axis: str, column: np.ndarray) -> np.ndarray:
        old, new = maps[axis]
        if not old.size:
            return column
        magnitude = np.abs(column)
        where = np.clip(np.searchsorted(old, magnitude), 0, old.size - 1)
        hit = old[where] == magnitude
        out = column.copy()
        out[hit] = np.where(np.signbit(column[hit]) & (new[where[hit]] != 0), -new[where[hit]], new[where[hit]])
        return out

    changed, biggest = _rewrite(deck, axes, new_values, f"clean coordinate round-off ({axes}: snap clusters)")
    return {"axes": axes, "tolerance": tol, "snapped_values": snapped, "rejected_clusters": rejected,
            "max_change": biggest, "changed_nodes": changed, "noise_before": before,
            "noise_after": coordinate_noise(deck, rel_tol)}


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


def quantize_coordinates(deck: KeywordDeck, axes: str | None = None, magnitude: float | None = None,
                         rel_tol: float = 1e-9) -> dict:
    """LS-PrePost move-far-and-back: every coordinate of ``axes`` becomes x + D - D.

    Rounds all values of the axes (clean ones too) to the binary grid ulp(D); use it to make a
    model insensitive to a later translate-and-back, not as the round-off cleanup. ``magnitude``
    defaults to 1.5 x a power of two chosen from the detected deviation; a magnitude whose x + D
    range straddles a power of two is refused (it would round + and - values on different grids).
    """
    before = coordinate_noise(deck, rel_tol)
    axes = _axes(before, axes)
    if not axes:
        return {"axes": "", "changed_nodes": 0, "noise_before": before, "note": "no axes given and no noise found"}
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
    changed, biggest = _rewrite(deck, axes, lambda axis, column: (column + shift) - shift,
                                f"quantize coordinates ({axes}: move {shift:g} and back)")
    return {"axes": axes, "magnitude": shift, "grid_step": math.ulp(shift), "bound": math.ulp(shift) / 2,
            "max_change": biggest, "changed_nodes": changed, "noise_before": before,
            "noise_after": coordinate_noise(deck, rel_tol)}


__all__ = ["SNAP_SPAN", "clean_coordinates", "coordinate_noise", "quantize_coordinates"]
