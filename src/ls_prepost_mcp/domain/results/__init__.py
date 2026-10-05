"""Result post-processing computed in Python, without LS-PrePost (tasks.yaml Q-group backends).

``curves``: Q07 curve operations (filters, calculus, resampling, spectrum, cross plot).
``invariants``: Q04 stress invariants, element masks and extrema.
"""
from . import curves, invariants

__all__ = ["curves", "invariants"]
