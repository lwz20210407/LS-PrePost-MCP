"""Result post-processing computed in Python, without LS-PrePost (tasks.yaml Q-group backends).

``curves``: Q07 curve operations (filters, calculus, resampling, spectrum, cross plot).
``invariants``: Q04 stress invariants, element masks and extrema.
``lasso_backend``: Q01/Q05/Q06 result reading with lasso-python (optional extra).
``mpp_shards``: Q06 binout reading across MPP shards with explicit merge rules.
``export``: Q03 field export to CSV / NPZ with semantic metadata.
"""
from . import curves, energy, export, invariants, lasso_backend, mpp_shards, section

__all__ = ["curves", "energy", "export", "invariants", "lasso_backend", "mpp_shards", "section"]
