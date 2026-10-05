"""Result post-processing computed in Python, without LS-PrePost (tasks.yaml Q-group backends).

``curves``: Q07 curve operations (filters, calculus, resampling, spectrum, cross plot).
``invariants``: Q04 stress invariants, element masks and extrema.
``lasso_backend``: Q01/Q05/Q06 result reading with lasso-python (optional extra).
"""
from . import curves, invariants, lasso_backend

__all__ = ["curves", "invariants", "lasso_backend"]
