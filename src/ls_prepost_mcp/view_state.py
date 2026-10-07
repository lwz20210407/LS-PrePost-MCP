"""G01 view request, named request-preset and pixel-identity contracts; no native I/O.

A ViewRequest describes native commands to send; it is never evidence of the resulting camera.
No native camera-matrix readback exists, so a named preset stores only a replayable request
("request_preset"), never a captured current camera. zoom_scale and pan_xy are absolute native
settings (pan is a native view offset, not a model length); rotations are incremental global
X, Y, Z view steps applied after the standard view and before fit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from PIL import Image
from pydantic import BeforeValidator, model_validator

from .core.contracts import Contract, Number, Selector, Text, freeze_sequence
from .gui_controls import camera_commands
from .native.commands import VIEWS

PRESET_SCHEMA = "ViewPreset/v1"
PRESET_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
DEVICE_NAMES = re.compile(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])")
VIEW_FRAME = dict(
    coordinate_frame="native_global_view_axes",
    zoom="native_absolute_scale",
    pan="native_view_offset",
    rotation="incremental_global_xyz_degrees",
    state="unchanged_by_request",
)

StandardView = Literal["isometric", "top", "bottom", "front", "back", "left", "right"]


class ViewRequest(Contract):
    view: StandardView | None = None
    projection: Literal["parallel", "perspective"] | None = None
    rotation_xyz_degrees: Annotated[tuple[Number, Number, Number], BeforeValidator(freeze_sequence)] | None = None
    zoom_scale: Number | None = None
    pan_xy: Annotated[tuple[Number, Number], BeforeValidator(freeze_sequence)] | None = None
    fit: bool = False
    center_on: Selector | None = None

    @model_validator(mode="after")
    def bounded_camera(self):
        self.camera()
        if not self.fit and all(getattr(self, key) is None for key in (
                "view", "projection", "rotation_xyz_degrees", "zoom_scale", "pan_xy", "center_on")):
            raise ValueError("Request at least one view change")
        return self

    def camera(self):
        return camera_commands(self.zoom_scale, None if self.pan_xy is None else list(self.pan_xy),
                               None if self.rotation_xyz_degrees is None else list(self.rotation_xyz_degrees))

    def commands(self):
        if self.center_on is not None:
            raise ValueError("Selector centering has no verified native camera-target command")
        rotations, after_fit = self.camera()
        commands = [VIEWS[self.view]] if self.view is not None else []
        commands += [self.projection] if self.projection is not None else []
        return commands + rotations + (["ac"] if self.fit else []) + after_fit

    @property
    def replayable(self):
        """Replays reach the same request only from an explicit standard view and projection."""
        return self.view is not None and self.projection is not None

    @property
    def content_dependent(self):
        return self.fit


class PresetBinding(Contract):
    context: Literal["batch", "session"]
    backend: Literal["lsprepost"] = "lsprepost"
    executable_sha256: Text | None = None
    session_id: Text | None = None
    model_generation: Text | None = None
    model_kind: Literal["keyword", "d3plot"]
    model_sha256: Text | None = None

    @model_validator(mode="after")
    def identity(self):
        if self.context == "session" and (self.session_id is None or self.model_generation is None):
            raise ValueError("Session presets bind the session and its model generation")
        if self.context == "batch" and (self.model_sha256 is None or self.session_id is not None):
            raise ValueError("Batch presets bind the input model bytes, not a session")
        return self


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def preset_path(root, name):
    if not isinstance(name, str) or not PRESET_NAME.fullmatch(name) or DEVICE_NAMES.fullmatch(name):
        raise ValueError("Preset name must match [A-Za-z][A-Za-z0-9_-]{0,63} and not be a device name")
    root = Path(root)
    path = (root / (name.lower() + ".json")).resolve()
    if path.parent != root.resolve():
        raise ValueError("Preset path escapes the preset directory")
    return path


def save_preset(root, name, request, binding, created_at):
    """Create a request preset; an existing name (case-insensitive) is never overwritten."""
    if not isinstance(request, ViewRequest) or not isinstance(binding, PresetBinding):
        raise TypeError("Expected a ViewRequest and PresetBinding")
    if not request.replayable or request.center_on is not None:
        raise ValueError("Presets require an explicit standard view and projection and no Selector centering")
    path = preset_path(root, name)
    body = dict(schema=PRESET_SCHEMA, name=name, kind="request_preset", verification="request_only",
                native_camera_captured=False, request=request.model_dump(mode="json"),
                commands=request.commands(), content_dependent=request.content_dependent, frame=VIEW_FRAME,
                binding=binding.model_dump(mode="json"), created_at=created_at)
    body["payload_sha256"] = hashlib.sha256(canonical(body).encode("utf8")).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(canonical(body), encoding="utf8")
    try:
        os.link(temporary, path)
    except FileExistsError:
        raise ValueError("A preset with this name already exists; choose another name") from None
    finally:
        temporary.unlink()
    return path, body


def load_preset(root, name, binding):
    """Return a verified request preset; corruption or a changed binding is rejected."""
    path = preset_path(root, name)
    if not path.is_file():
        raise ValueError("Unknown view preset")
    try:
        body = json.loads(path.read_text(encoding="utf8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("View preset is corrupt") from None
    if not isinstance(body, dict) or body.get("schema") != PRESET_SCHEMA:
        raise ValueError("Unsupported view preset schema")
    stored = body.pop("payload_sha256", None)
    if stored != hashlib.sha256(canonical(body).encode("utf8")).hexdigest():
        raise ValueError("View preset is corrupt or was edited")
    if body.get("name") != name:
        raise ValueError("View preset name differs from its file")
    if body.get("kind") != "request_preset" or body.get("native_camera_captured") is not False:
        raise ValueError("Only request presets are supported")
    request = ViewRequest.model_validate(body["request"])
    if body["commands"] != request.commands():
        raise ValueError("View preset commands differ from its request")
    if PresetBinding.model_validate(body["binding"]) != binding:
        raise ValueError("View preset belongs to a different model, session or build")
    body["payload_sha256"] = stored
    return request, body


def _decoded(path):
    data = Path(path).read_bytes()
    with Image.open(Path(path)) as image:
        if image.format != "PNG":
            raise ValueError("Pixel identity requires PNG files")
        mode = image.mode
        pixels = np.asarray(image.convert("RGBA"))
    return data, mode, pixels


def compare_png_pixels(first, second):
    """Exact decoded RGBA comparison; no tolerance, file names or compressed bytes decide identity."""
    results = []
    for path in (first, second):
        data, mode, pixels = _decoded(path)
        results.append(dict(path=str(path), file_sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
                            mode=mode, width=int(pixels.shape[1]), height=int(pixels.shape[0]),
                            pixel_sha256=hashlib.sha256(pixels.tobytes()).hexdigest(), pixels=pixels))
    a, b = results[0].pop("pixels"), results[1].pop("pixels")
    same_shape = a.shape == b.shape
    differing = int(np.any(a != b, axis=2).sum()) if same_shape else None
    delta = int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max()) if same_shape else None
    return dict(identical=same_shape and differing == 0, same_dimensions=same_shape, differing_pixels=differing,
                max_channel_delta=delta, comparison="decoded_rgba_exact", images=results)
