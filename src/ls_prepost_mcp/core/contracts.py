"""I02 semantic requests/results; validation performs no filesystem or native I/O.

Valid requests still require backend/version capability checks. Unit strings
are declarations, never inferred units or implicit conversions.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, JsonValue, model_validator

Text = Annotated[str, Field(strict=True, min_length=1, pattern=r"\S")]
Identifier = Annotated[int, Field(strict=True, ge=1, le=2_000_000_000)]
Natural = Annotated[int, Field(strict=True, ge=0)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Positive = Annotated[Number, Field(gt=0)]
Nonnegative = Annotated[Number, Field(ge=0)]
SHA256 = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
Domain = Literal["node", "element", "shell", "solid", "tshell", "beam", "part", "interface", "global"]


def freeze_sequence(value):
    if isinstance(value, list):
        return tuple(value)
    return value


Ids = Annotated[tuple[Identifier, ...], BeforeValidator(freeze_sequence)]
Vector3 = Annotated[tuple[Number, Number, Number], BeforeValidator(freeze_sequence)]
Texts = Annotated[tuple[Text, ...], BeforeValidator(freeze_sequence)]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, allow_inf_nan=False, revalidate_instances="always"
    )


class FileIdentity(Contract):
    path: Text
    sha256: SHA256
    size_bytes: Natural


class IncludeRef(Contract):
    """Include occurrence metadata, not a keyword parser or I07 implementation."""

    id: Text
    parent_id: Text | None = None
    file_path: Text
    raw_reference: Text
    parameters: dict[str, str] = Field(default_factory=dict)


class ModelRef(Contract):
    kind: Literal["keyword", "d3plot", "binout", "ascii"]
    files: Annotated[tuple[FileIdentity, ...], BeforeValidator(freeze_sequence), Field(min_length=1)]
    units: Text | None = None
    include_tree: Annotated[tuple[IncludeRef, ...], BeforeValidator(freeze_sequence)] = ()
    include_search_paths: Texts = ()

    @model_validator(mode="after")
    def coherent_file_family(self):
        paths = [f.path for f in self.files]
        if len(set(paths)) != len(paths):
            raise ValueError("File-family paths must be unique")
        if self.kind != "keyword" and (self.include_tree or self.include_search_paths):
            raise ValueError("Include metadata belongs to keyword models")
        nodes = {node.id: node for node in self.include_tree}
        if len(nodes) != len(self.include_tree):
            raise ValueError("Include occurrence IDs must be unique")
        for node in self.include_tree:
            if node.file_path not in paths:
                raise ValueError("Include files must have declared identities")
            seen = {node.id}
            parent = node.parent_id
            while parent is not None:
                if parent not in nodes or parent in seen:
                    raise ValueError("Include parent is missing or cyclic")
                seen.add(parent)
                parent = nodes[parent].parent_id
        return self


class AllSelection(Contract):
    kind: Literal["all"] = "all"


class IdSelection(Contract):
    kind: Literal["ids"] = "ids"
    ids: Ids

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("Selection IDs must be unique")
        return self


class PartSelection(IdSelection):
    kind: Literal["parts"] = "parts"


class SetSelection(IdSelection):
    kind: Literal["sets"] = "sets"
    set_type: Literal["node", "shell", "solid", "beam", "part", "segment"]


class BoxSelection(Contract):
    kind: Literal["box"] = "box"
    minimum: Vector3
    maximum: Vector3

    @model_validator(mode="after")
    def ordered_bounds(self):
        if any(low > high for low, high in zip(self.minimum, self.maximum)):
            raise ValueError("Box minimum exceeds maximum")
        return self


class SphereSelection(Contract):
    kind: Literal["sphere"] = "sphere"
    center: Vector3
    radius: Positive


class PlaneSelection(Contract):
    kind: Literal["plane"] = "plane"
    origin: Vector3
    normal: Vector3
    tolerance: Nonnegative
    side: Literal["on", "positive", "negative"] = "on"

    @model_validator(mode="after")
    def nonzero_normal(self):
        if not any(self.normal):
            raise ValueError("Plane normal must be nonzero")
        return self


class SurfaceSelection(Contract):
    kind: Literal["surface"] = "surface"
    part_ids: Ids
    feature_angle_degrees: Annotated[Number, Field(ge=0, le=180)] | None = None

    @model_validator(mode="after")
    def unique_parts(self):
        if not self.part_ids or len(set(self.part_ids)) != len(self.part_ids):
            raise ValueError("Surface selection needs unique explicit part IDs")
        return self


class BooleanSelection(Contract):
    kind: Literal["boolean"] = "boolean"
    operator: Literal["union", "intersection", "difference"]
    operands: Annotated[
        tuple[SelectionPredicate, ...], BeforeValidator(freeze_sequence), Field(min_length=2, max_length=32)
    ]

    @model_validator(mode="after")
    def difference_is_binary(self):
        if self.operator == "difference" and len(self.operands) != 2:
            raise ValueError("Difference requires exactly two operands")
        return self


SelectionPredicate = Annotated[
    Union[
        AllSelection,
        IdSelection,
        PartSelection,
        SetSelection,
        BoxSelection,
        SphereSelection,
        PlaneSelection,
        SurfaceSelection,
        BooleanSelection,
    ],
    Field(discriminator="kind"),
]
BooleanSelection.model_rebuild()


class Selector(Contract):
    entity_type: Domain
    predicate: SelectionPredicate
    configuration: Literal["reference", "deformed"] = "reference"
    state: Identifier | None = None
    validity: Literal["all", "alive", "deleted"] = "all"

    @model_validator(mode="after")
    def coordinate_context(self):
        if (self.configuration == "deformed") != (self.state is not None):
            raise ValueError("Deformed coordinates require a 1-based state; reference coordinates omit it")
        if self.entity_type == "global" and not isinstance(self.predicate, AllSelection):
            raise ValueError("Global quantities have no entity selection")
        return self


class StateIndices(Contract):
    kind: Literal["states"] = "states"
    indices: Annotated[Ids, Field(min_length=1)]

    @model_validator(mode="after")
    def unique_states(self):
        if len(set(self.indices)) != len(self.indices):
            raise ValueError("States must be unique and 1-based")
        return self


class PhysicalTime(Contract):
    kind: Literal["time"] = "time"
    value: Number
    units: Text
    match: Literal["nearest", "exact"] = "nearest"


class Unlayered(Contract):
    kind: Literal["unlayered"] = "unlayered"


class NativeDefault(Contract):
    kind: Literal["native_default"] = "native_default"


class NativeLayer(Contract):
    kind: Literal["native_layer"] = "native_layer"
    layer: Literal["inner", "mid", "outer"]


class NativePoint(Contract):
    kind: Literal["native_point"] = "native_point"
    index: Identifier


class StoredPoint(Contract):
    kind: Literal["stored_point"] = "stored_point"
    index: Identifier


Sampling = Annotated[
    Union[Unlayered, NativeDefault, NativeLayer, NativePoint, StoredPoint], Field(discriminator="kind")
]


class FieldSpec(Contract):
    quantity: Text
    components: Annotated[Texts, Field(min_length=1)]
    units: Text
    backend: Literal["lsprepost", "lasso", "lsreader", "dpf"]
    selector: Selector
    at: Annotated[Union[StateIndices, PhysicalTime], Field(discriminator="kind")]
    sampling: Sampling
    frame: Literal["global", "material", "local"]
    coordinate_system_id: Identifier | None = None
    averaging: Literal["none", "minmax", "nodal"]

    @model_validator(mode="after")
    def consistent_sampling(self):
        if len(set(self.components)) != len(self.components):
            raise ValueError("Field components must be unique")
        if (self.frame == "local") != (self.coordinate_system_id is not None):
            raise ValueError("Only local coordinates require a coordinate-system ID")
        if self.selector.entity_type in ("node", "global", "part", "interface") and not isinstance(
            self.sampling, Unlayered
        ):
            raise ValueError("This entity domain has no layer/integration-point selector")
        if isinstance(self.sampling, NativeLayer) and self.selector.entity_type not in ("shell", "tshell"):
            raise ValueError("Named layers apply only to shell/tshell")
        native = isinstance(self.sampling, (NativeDefault, NativeLayer, NativePoint))
        if native and self.backend != "lsprepost":
            raise ValueError("Native selectors are not reader stored-point indices")
        if isinstance(self.sampling, StoredPoint) and self.backend == "lsprepost":
            raise ValueError("Stored-point indices are not native selectors")
        return self


class ButterworthFilter(Contract):
    kind: Literal["butterworth"] = "butterworth"
    order: Annotated[int, Field(strict=True, ge=1, le=16)]
    cutoff_hz: Positive


class SAEFilter(Contract):
    kind: Literal["sae"] = "sae"
    cfc: Positive


class CurveSpec(Contract):
    source: ModelRef
    database: Text
    entity_type: Domain
    entity_ids: Ids = ()
    component: Text
    units: Text
    time_units: Text
    time_column: Text = "time"
    time_range: Annotated[tuple[Number, Number], BeforeValidator(freeze_sequence)] | None = None
    sign: Literal["as_stored", "negated"] = "as_stored"
    alignment: Literal["none", "intersection_linear"] = "none"
    filter: Annotated[Union[ButterworthFilter, SAEFilter], Field(discriminator="kind")] | None = None

    @model_validator(mode="after")
    def curve_identity(self):
        if (self.entity_type == "global") != (not self.entity_ids):
            raise ValueError("Global curves omit entity IDs; other curves require them")
        if len(set(self.entity_ids)) != len(self.entity_ids):
            raise ValueError("Curve entity IDs must be unique")
        if self.time_range is not None and self.time_range[0] >= self.time_range[1]:
            raise ValueError("Curve time interval must be strictly increasing")
        return self


class Artifact(Contract):
    path: Text
    kind: Text
    sha256: SHA256 | None = None
    size_bytes: Natural | None = None
    verification: Literal["verified", "unverified"] = "unverified"
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def verified_identity(self):
        if self.verification == "verified" and (self.sha256 is None or self.size_bytes is None):
            raise ValueError("Verified artifacts require SHA256 and byte size")
        return self


class CheckResult(Contract):
    name: Text
    status: Literal["passed", "failed", "not_applicable", "missing", "invalid"]
    source_path: Annotated[
        tuple[str | Annotated[int, Field(strict=True, ge=0)], ...], BeforeValidator(freeze_sequence)
    ] = ()


class JobResult(Contract):
    contract: Literal["JobResult/v1"] = "JobResult/v1"
    operation: Text
    status: Literal["succeeded", "failed", "partial", "unverified"]
    job_id: Text | None = None
    stage: Literal["preparation", "execution"] = "execution"
    backend: Text | None = None
    scope: Text | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)
    artifacts: Annotated[tuple[Artifact, ...], BeforeValidator(freeze_sequence)] = ()
    evidence: Annotated[tuple[Artifact, ...], BeforeValidator(freeze_sequence)] = ()
    checks: Annotated[tuple[CheckResult, ...], BeforeValidator(freeze_sequence)] = ()
    warnings: Texts = ()
    error: dict[str, JsonValue] | None = None
    # Transitional envelope for existing user-authored JSON predicates only.
    # Execution/quality decisions use status/checks, never fields in this envelope.
    comparison_data: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def result_consistency(self):
        if self.status == "succeeded" and self.error is not None:
            raise ValueError("Succeeded results cannot carry an execution error")
        if len({check.name for check in self.checks}) != len(self.checks):
            raise ValueError("Check names must be unique")
        return self

    @property
    def execution_accepted(self):
        return self.status == "succeeded"

    @property
    def check_status(self):
        if not self.checks:
            return "not_reported"
        states = {check.status for check in self.checks}
        for state in ("failed", "invalid", "missing", "not_applicable"):
            if state in states:
                return state
        return "passed"
