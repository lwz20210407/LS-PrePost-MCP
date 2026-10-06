"""Per-context native routing; no monkeypatching or replacement Service."""

from contextlib import contextmanager
from contextvars import ContextVar


class NativeContext:
    def __init__(self):
        self._executor = ContextVar("native_executor", default=None)

    @property
    def executor(self):
        return self._executor.get()

    @contextmanager
    def using(self, executor):
        token = self._executor.set(executor)
        try:
            yield
        finally:
            self._executor.reset(token)
