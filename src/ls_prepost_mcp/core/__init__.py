"""Backend-independent contracts. This package must not import service or adapters."""

from .contracts import Artifact, CurveSpec, FieldSpec, JobResult, ModelRef, Selector

__all__ = ["Artifact", "CurveSpec", "FieldSpec", "JobResult", "ModelRef", "Selector"]
