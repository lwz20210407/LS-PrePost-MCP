"""Optional LASSO adapter, keeping its file handles scoped to one operation."""
from contextlib import contextmanager
from glob import escape
from importlib.metadata import version

from .native.versions import dependency_supported


def lasso_vectors(arrays: dict, quantity: str):
    """Normalize LASSO 2.0.4 raw d3plot coordinates to actual displacements.

    In 2.0.4, node_displacement stores the state x/y/z coordinates (also used
    directly by D3plot.plot). Match LS-Reader D3P_NODE_DISPLACEMENTS by
    subtracting the reference node_coordinates; never subtract for velocity.
    """
    import numpy as np
    if not dependency_supported("lasso-python", version("lasso-python")):
        raise RuntimeError("Displacement normalization is verified for lasso-python 2.0.4; validate a new version first")
    if quantity not in ("displacement", "velocity"):
        raise ValueError("Unsupported vector quantity")
    values = np.asarray(arrays["node_" + quantity], dtype=float)
    if quantity == "displacement":
        reference = np.asarray(arrays["node_coordinates"], dtype=float)
        if values.ndim != 3 or reference.shape != values.shape[1:]:
            raise ValueError("Reference coordinates do not align with state coordinates")
        values = values - reference[None, :, :]
    return values


@contextmanager
def open_binout(path: str):
    from lasso.dyna import Binout
    # Public tools accept one literal file, not an unchecked glob expression.
    db = Binout(escape(path))
    try:
        yield db
    finally:
        db.lsda.close()
