"""Backend-aware result-selection/sampling contracts; no implicit layer equivalence."""

import hashlib
import json
import re
from dataclasses import dataclass

ELEMENT_SCALARS = {"area", "volume", "thickness", "internal_energy_density"}


@dataclass(frozen=True)
class EntitySelection:
    """Common ID domain used by GUI selection and exported result requests."""

    domain: str
    entity_ids: tuple[int, ...]

    def __post_init__(self):
        if self.domain not in ("node", "element", "shell", "solid", "tshell", "beam", "part", "interface", "global"):
            raise ValueError("Unsupported entity domain")
        if not isinstance(self.entity_ids, (list, tuple)):
            raise ValueError("Entity IDs must be a list or tuple")
        object.__setattr__(self, "entity_ids", tuple(self.entity_ids))
        if any(type(v) is not int or not 1 <= v <= 2_000_000_000 for v in self.entity_ids) or len(
            set(self.entity_ids)
        ) != len(self.entity_ids):
            raise ValueError("Entity IDs must be unique positive user integers")
        if self.domain == "global" and self.entity_ids:
            raise ValueError("Global quantities have no entity IDs")

    def describe(self):
        value = json.dumps(dict(domain=self.domain, entity_ids=self.entity_ids), separators=(",", ":"))
        return dict(
            domain=self.domain,
            id_kind="none" if self.domain == "global" else "user",
            entity_count=len(self.entity_ids),
            entity_id_sample=list(self.entity_ids[:20]),
            ordered_entity_sha256=hashlib.sha256(value.encode()).hexdigest(),
        )


@dataclass(frozen=True)
class ResultSelection:
    domain: str
    entity_ids: tuple[int, ...]
    states: tuple[int, ...]

    def __post_init__(self):
        entities = EntitySelection(self.domain, self.entity_ids)
        if not isinstance(self.entity_ids, (list, tuple)) or not isinstance(self.states, (list, tuple)):
            raise ValueError("Result selection IDs and states must be lists or tuples")
        object.__setattr__(self, "entity_ids", entities.entity_ids)
        object.__setattr__(self, "states", tuple(self.states))
        if self.domain not in ("node", "element", "shell", "solid", "tshell", "beam", "part", "interface", "global"):
            raise ValueError("Unsupported result entity domain")
        if not self.states or (self.domain != "global" and not self.entity_ids):
            raise ValueError("Explicit states and entity IDs are required")
        if self.domain == "global" and self.entity_ids:
            raise ValueError("Global quantities have no entity IDs")
        for values in (self.entity_ids, self.states):
            if any(type(v) is not int or not 1 <= v <= 2_000_000_000 for v in values) or len(
                set(values)
            ) != len(values):
                raise ValueError("Result IDs/states must be unique positive integers, never array positions")

    def describe(self):
        # Exact full requests remain in job.parameters; response metadata stays bounded.
        encoded = json.dumps(
            dict(domain=self.domain, entity_ids=self.entity_ids, states=self.states), separators=(",", ":")
        )
        return dict(
            entity_selection=EntitySelection(self.domain, self.entity_ids).describe(),
            domain=self.domain,
            id_kind="none" if self.domain == "global" else "user",
            state_index_base=1,
            entity_count=len(self.entity_ids),
            state_count=len(self.states),
            entity_id_sample=list(self.entity_ids[:20]),
            state_sample=list(self.states[:20]),
            ordered_selection_sha256=hashlib.sha256(encoded.encode()).hexdigest(),
            full_request_location="job.parameters",
            global_csv_entity_placeholder=0 if self.domain == "global" else None,
        )


@dataclass(frozen=True)
class SamplingSpec:
    kind: str
    value: str | int | tuple[int, ...]
    native_selector: str | None = None

    def __post_init__(self):
        if self.kind in ("stored_axes", "stored_integration_point"):
            if not isinstance(self.value, (list, tuple)) or any(
                type(v) is not int or v < 1 for v in self.value
            ):
                raise ValueError("Stored sampling uses positive 1-based indices")
            object.__setattr__(self, "value", tuple(self.value))
            if self.native_selector is not None or (
                self.kind == "stored_integration_point" and len(self.value) != 1
            ):
                raise ValueError("Invalid stored sampling definition")
        elif self.kind == "native_shell_layer":
            if self.value not in ("mid", "inner", "outer") or self.native_selector != self.value.upper():
                raise ValueError("Invalid native shell-layer selector")
        elif self.kind == "native_integration_point":
            if (
                type(self.value) is not int
                or not 1 <= self.value <= 99
                or self.native_selector != str(self.value)
            ):
                raise ValueError("Invalid native integration-point selector")
        elif self.kind == "native_default":
            if self.value != "solid_default" or self.native_selector != "0":
                raise ValueError("Invalid native solid default selector")
        elif self.kind == "native_element_scalar":
            if self.value != "element" or self.native_selector != "0":
                raise ValueError("Invalid element-scalar sampling definition")
        elif self.kind == "not_applicable":
            if self.value != "nodal" or self.native_selector != "0":
                raise ValueError("Invalid native nodal selector")
        elif self.kind == "dpf_native_location":
            if self.value not in ("Nodal", "Elemental", "TimeFreq_steps") or self.native_selector is not None:
                raise ValueError("Invalid DPF native-location sampling")
        else:
            raise ValueError("Unknown sampling kind")

    @classmethod
    def native(cls, domain, selection):
        if not isinstance(selection, str) or (
            selection not in ("mid", "inner", "outer") and not re.fullmatch(r"[1-9][0-9]?", selection)
        ):
            raise ValueError("Integration point is mid/inner/outer or a 1-based integer string 1..99")
        if domain == "node":
            if selection != "mid":
                raise ValueError(
                    "Nodal results have no shell layer/integration point; use the legacy mid/default selector"
                )
            return cls("not_applicable", "nodal", "0")
        if domain not in ("shell", "solid", "tshell"):
            raise ValueError("Native sampling supports node/shell/solid/tshell")
        if domain == "solid" and selection in ("inner", "outer"):
            raise ValueError("Inner/outer applies to shell/tshell only")
        if domain == "solid" and selection == "mid":
            return cls("native_default", "solid_default", "0")
        if selection in ("mid", "inner", "outer"):
            return cls("native_shell_layer", selection, selection.upper())
        if domain == "solid" and int(selection) > 8:
            raise ValueError("Native fully-integrated solid selectors are limited to 1..8")
        return cls("native_integration_point", int(selection), selection)

    @classmethod
    def native_fields(cls, domain, selection, fields):
        if domain != "node" and set(fields) & ELEMENT_SCALARS:
            if selection != "mid":
                raise ValueError(
                    "Element scalar quantities have no layer/point; use the native default and split layer-specific requests"
                )
            if set(fields) <= ELEMENT_SCALARS:
                return cls("native_element_scalar", "element", "0")
        return cls.native(domain, selection)

    @classmethod
    def stored(cls, indices, *, stress=False):
        if not isinstance(indices, (list, tuple)) or any(type(v) is not int or v < 1 for v in indices):
            raise ValueError("Stored component/layer indices must be positive 1-based integers")
        if stress and len(indices) != 1:
            raise ValueError("Stored stress requires exactly one integration-point index")
        return cls("stored_integration_point" if stress else "stored_axes", tuple(indices))

    def describe(self):
        return dict(
            kind=self.kind,
            value=list(self.value) if isinstance(self.value, tuple) else self.value,
            native_selector=self.native_selector,
            index_base=1
            if self.kind in ("native_integration_point", "stored_integration_point", "stored_axes")
            else None,
            cross_backend_equivalence="not_inferred",
        )


@dataclass(frozen=True)
class FieldSpec:
    backend: str
    fields: tuple[str, ...]
    units: str
    selection: ResultSelection
    sampling: SamplingSpec
    frame: str
    averaging: str
    validity: str
    transformations: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.selection, ResultSelection) or not isinstance(self.sampling, SamplingSpec):
            raise ValueError("Typed result selection and sampling are required")
        if not isinstance(self.fields, (list, tuple)):
            raise ValueError("Field names must be a list or tuple")
        object.__setattr__(self, "fields", tuple(self.fields))
        if self.backend not in ("lsprepost", "lasso", "lsreader", "dpf"):
            raise ValueError("Unknown field backend")
        if not isinstance(self.units, str) or not self.units.strip() or len(self.units) > 100:
            raise ValueError("An explicit unit label is required; dimensional validation is not inferred")
        if (
            not self.fields
            or any(not isinstance(f, str) or not f for f in self.fields)
            or len(set(self.fields)) != len(self.fields)
        ):
            raise ValueError("Field names must be nonempty and unique")
        if self.backend == "lsprepost" and self.sampling.kind.startswith("stored_"):
            raise ValueError("Stored reader slots cannot be treated as native sampling selectors")
        if self.backend != "lsprepost" and self.sampling.native_selector is not None:
            raise ValueError("Native layer selectors cannot be treated as reader slots")
        if (self.backend == "dpf") != (self.sampling.kind == "dpf_native_location"):
            raise ValueError("DPF source-location sampling must stay attached to the DPF backend")
        if self.backend == "dpf" and self.selection.domain not in {
            "Nodal": {"node"}, "Elemental": {"element", "beam"},
            "TimeFreq_steps": {"global", "part", "interface"},
        }[self.sampling.value]:
            raise ValueError("DPF location does not match its selection domain")
        if self.backend == "lsprepost":
            allowed = {
                "node": {"not_applicable"},
                "solid": {"native_default", "native_integration_point", "native_element_scalar"},
                "shell": {"native_shell_layer", "native_integration_point", "native_element_scalar"},
                "tshell": {"native_shell_layer", "native_integration_point", "native_element_scalar"},
            }
            if self.sampling.kind not in allowed.get(self.selection.domain, set()):
                raise ValueError("Native sampling does not match the entity domain")
            if self.sampling.kind == "native_element_scalar" and not set(self.fields) <= ELEMENT_SCALARS:
                raise ValueError("Element-scalar sampling cannot describe layered tensor components")
        if any(not isinstance(v, str) or not v.strip() for v in (self.frame, self.averaging, self.validity)):
            raise ValueError("Frame, averaging and validity scope must be explicit")
        if not isinstance(self.transformations, (list, tuple)) or any(
            not isinstance(t, str) or not t for t in self.transformations
        ):
            raise ValueError("Transformations must be explicit text labels")
        object.__setattr__(self, "transformations", tuple(self.transformations))

    def describe(self):
        return dict(
            schema_version=1,
            backend=self.backend,
            fields=list(self.fields),
            units=dict(label=self.units, dimensional_validation=False, conversion="none"),
            selection=self.selection.describe(),
            sampling=self.sampling.describe(),
            sampling_by_field={
                field: SamplingSpec("native_element_scalar", "element", "0").describe()
                if self.backend == "lsprepost" and field in ELEMENT_SCALARS
                else self.sampling.describe()
                for field in self.fields
            },
            frame=self.frame,
            averaging=self.averaging,
            validity=self.validity,
            transformations=list(self.transformations),
            scope="Result request/provenance contract; not material-history interpretation, unit conversion or physical validation",
        )
