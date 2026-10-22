"""Stress invariants for whole result fields (tasks.yaml Q04), vectorised over elements.

Components are ordered xx, yy, zz, xy, yz, zx (LS-DYNA d3plot order). Conventions follow the
single-point ``stress_metrics`` of the repository so both give the same numbers:

* von Mises sigma_vm = sqrt(3 J2); mean stress sigma_m = I1 / 3; pressure = -sigma_m
* stress triaxiality eta = sigma_m / sigma_vm
* principal stresses sigma1 >= sigma2 >= sigma3
* Lode parameter L = (2 sigma2 - sigma1 - sigma3) / (sigma1 - sigma3)  (-1 uniaxial tension, +1 equibiaxial)
* cos(3 theta) = (3 sqrt(3) / 2) J3 / J2^1.5, Lode angle theta in [0, pi/3],
  Lode angle parameter = 1 - 6 theta / pi  (+1 uniaxial tension, -1 equibiaxial tension)

Where sigma_vm is zero (hydrostatic or zero stress) the deviatoric quantities are NaN, never 0.
Element masks: "alive" (default), "all" or "deleted"; extrema return the element ID and value.
"""
from __future__ import annotations

import numpy as np

CONVENTIONS = {
    "components": ["xx", "yy", "zz", "xy", "yz", "zx"],
    "von_mises": "sqrt(3 J2)", "triaxiality": "sigma_m / sigma_vm", "pressure": "-I1/3", "mean_stress": "I1/3",
    "principal_1": "largest eigenvalue s1 of the stress tensor (s1 >= s2 >= s3)",
    "principal_2": "middle eigenvalue s2 of the stress tensor (s1 >= s2 >= s3)",
    "principal_3": "smallest eigenvalue s3 of the stress tensor (s1 >= s2 >= s3)",
    "max_shear": "(s1 - s3) / 2",
    "lode_parameter": "L = (2 s2 - s1 - s3) / (s1 - s3), s1 >= s2 >= s3 (Lode 1926); range [-1, 1]: "
                      "-1 uniaxial tension (s2 = s3), 0 pure shear / plane strain (s2 = (s1 + s3) / 2), "
                      "+1 uniaxial compression or equibiaxial tension (s2 = s1)",
    "lode_angle": "theta = acos(xi) / 3, xi = (3 sqrt3 / 2) J3 / J2^1.5 = (27/2) J3 / sigma_vm^3 "
                  "(Bai-Wierzbicki 2008); radians in [0, pi/3]: 0 uniaxial tension, pi/6 pure shear, "
                  "pi/3 uniaxial compression or equibiaxial tension",
    "lode_angle_parameter": "theta_bar = 1 - 6 theta / pi (Bai-Wierzbicki 2008); range [-1, 1]: +1 uniaxial "
                            "tension, 0 pure shear, -1 uniaxial compression or equibiaxial tension "
                            "(sign opposite to the Lode parameter L at these states)",
    "undefined": "deviatoric quantities are NaN where sigma_vm <= rel_tol * max|sigma|",
}
CONVENTIONS["lode_angle_rad"] = CONVENTIONS["lode_angle"]
MASKS = {
    "alive": "rows of elements not deleted at this state (stored deletion flag != 0)",
    "all": "rows of all elements, deleted or not",
    "deleted": "rows of elements deleted at this state (stored deletion flag == 0)",
}


def definition(quantity: str) -> str:
    """Formula / meaning of an element field quantity for result and artifact metadata."""
    if quantity in CONVENTIONS and quantity not in ("components", "undefined"):
        return CONVENTIONS[quantity]
    if quantity == "effective_plastic_strain":
        return "stored effective plastic strain (as written to d3plot)"
    if quantity.startswith("s") and quantity[1:] in CONVENTIONS["components"]:
        return f"stored stress component {quantity} (global frame, as written to d3plot)"
    return quantity
QUANTITIES = ("von_mises", "mean_stress", "pressure", "triaxiality", "principal_1", "principal_2", "principal_3",
              "max_shear", "lode_parameter", "lode_angle_rad", "lode_angle_parameter")


def invariants(stress: object, rel_tol: float = 1e-12) -> dict[str, np.ndarray]:
    """All Q04 quantities for stresses of shape (n, 6); returns arrays of length n."""
    s = np.asarray(stress, dtype=float)
    if s.ndim != 2 or s.shape[1] != 6:
        raise ValueError("stress must have shape (n, 6) ordered xx, yy, zz, xy, yz, zx")
    tensor = np.empty((s.shape[0], 3, 3))
    tensor[:, 0, 0], tensor[:, 1, 1], tensor[:, 2, 2] = s[:, 0], s[:, 1], s[:, 2]
    tensor[:, 0, 1] = tensor[:, 1, 0] = s[:, 3]
    tensor[:, 1, 2] = tensor[:, 2, 1] = s[:, 4]
    tensor[:, 0, 2] = tensor[:, 2, 0] = s[:, 5]
    mean = np.trace(tensor, axis1=1, axis2=2) / 3
    dev = tensor - mean[:, None, None] * np.eye(3)
    j2 = np.einsum("nij,nij->n", dev, dev) / 2
    j3 = np.linalg.det(dev)
    mises = np.sqrt(3 * j2)
    principal = np.linalg.eigvalsh(tensor)[:, ::-1]
    scale = np.abs(s).max(axis=1)
    defined = mises > rel_tol * np.where(scale > 0, scale, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        triax = np.where(defined, mean / mises, np.nan)
        cos3 = np.clip(np.where(defined, 1.5 * np.sqrt(3) * j3 / np.power(j2, 1.5), np.nan), -1.0, 1.0)
        spread = principal[:, 0] - principal[:, 2]
        lode = np.where(defined, (2 * principal[:, 1] - principal[:, 0] - principal[:, 2]) / spread, np.nan)
    theta = np.arccos(cos3) / 3
    return {"von_mises": mises, "mean_stress": mean, "pressure": -mean, "triaxiality": triax,
            "principal_1": principal[:, 0], "principal_2": principal[:, 1], "principal_3": principal[:, 2],
            "max_shear": spread / 2, "lode_parameter": lode, "lode_angle_rad": theta,
            "lode_angle_parameter": 1 - 6 * theta / np.pi}


def masked(alive: object, mode: str = "alive") -> np.ndarray:
    """Boolean selection for ``mode``: alive (default), all, deleted; ``alive`` as stored per element."""
    alive = np.asarray(alive, dtype=bool)
    if mode not in ("alive", "all", "deleted"):
        raise ValueError("mode must be alive, all or deleted")
    return {"alive": alive, "all": np.ones_like(alive), "deleted": ~alive}[mode]


def extrema(values: object, ids: object, selection: object | None = None) -> dict:
    """Minimum and maximum (NaN ignored) with the element IDs where they occur."""
    values, ids = np.asarray(values, dtype=float), np.asarray(ids)
    keep = np.isfinite(values) & (np.ones(values.shape, bool) if selection is None else np.asarray(selection, bool))
    if not keep.any():
        return {"count": 0, "min": None, "max": None}
    where = np.flatnonzero(keep)
    low, high = where[np.argmin(values[where])], where[np.argmax(values[where])]
    return {"count": int(where.size), "min": {"value": float(values[low]), "id": int(ids[low])},
            "max": {"value": float(values[high]), "id": int(ids[high])}}


__all__ = ["CONVENTIONS", "MASKS", "QUANTITIES", "definition", "extrema", "invariants", "masked"]
