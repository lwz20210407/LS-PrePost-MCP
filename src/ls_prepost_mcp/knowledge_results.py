"""List-compatible reference hits with separate query/index diagnostics."""
from copy import deepcopy


class ReferenceResults(list):
    """Python callers keep their list contract; diagnostics are never reference hits."""

    def __init__(self, rows=(), *, diagnostics=None):
        super().__init__(rows)
        self.diagnostics = deepcopy(diagnostics or {})
