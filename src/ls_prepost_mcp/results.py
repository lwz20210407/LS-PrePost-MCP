"""Optional LASSO adapter, keeping its file handles scoped to one operation."""
from contextlib import contextmanager


@contextmanager
def open_binout(path: str):
    from lasso.dyna import Binout
    db = Binout(path)
    try:
        yield db
    finally:
        db.lsda.close()

