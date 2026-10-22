import json

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from ls_prepost_mcp.view_state import (
    PresetBinding,
    ViewRequest,
    compare_png_pixels,
    load_preset,
    preset_path,
    save_preset,
)

BINDING = PresetBinding(context="session", session_id="a" * 32, model_generation="g1", model_kind="keyword",
                        executable_sha256="e" * 64)


def test_commands_follow_view_projection_rotation_fit_then_absolute_zoom_pan():
    request = ViewRequest(view="front", projection="parallel", rotation_xyz_degrees=[15, 0, -30], fit=True,
                          zoom_scale=2.0, pan_xy=[0.1, -0.2])
    commands = request.commands()
    assert commands[:6] == ["front", "parallel", "rotang 15", "rx", "rotang -30", "rz"]
    assert commands[6:8] == ["ac", "zoom 2"]
    assert commands[8].split()[0] == "pan" and [float(v) for v in commands[8].split()[1:]] == [0.1, -0.2]
    assert request.replayable and request.content_dependent


def test_incremental_request_is_not_replayable():
    request = ViewRequest(rotation_xyz_degrees=[0, 90, 0])
    assert request.commands() == ["rotang 90", "ry"]
    assert not request.replayable and not request.content_dependent
    assert not ViewRequest(view="top").replayable


@pytest.mark.parametrize("arguments", [
    {}, dict(view="diagonal"), dict(projection="fisheye"), dict(zoom_scale=0), dict(zoom_scale=100.5),
    dict(zoom_scale=True), dict(zoom_scale=float("nan")), dict(zoom_scale=float("inf")), dict(zoom_scale="2"),
    dict(pan_xy=[0]), dict(pan_xy=[0, 101]), dict(pan_xy=[False, 0]), dict(pan_xy=[0, float("nan")]),
    dict(rotation_xyz_degrees=[0, 361, 0]), dict(rotation_xyz_degrees=[0, "15", 0]),
    dict(rotation_xyz_degrees=[0, 0]), dict(fit=1), dict(view="front", unexpected=True),
])
def test_invalid_requests_are_rejected(arguments):
    with pytest.raises(ValidationError):
        ViewRequest(**arguments)


def test_selector_is_validated_but_centering_has_no_native_command():
    selector = dict(entity_type="part", predicate=dict(kind="parts", ids=[3]))
    request = ViewRequest(center_on=selector)
    assert request.center_on.predicate.ids == (3,)
    with pytest.raises(ValueError, match="no verified native camera-target"):
        request.commands()
    with pytest.raises(ValidationError, match="1-based state"):
        ViewRequest(center_on=dict(selector, configuration="deformed"))
    with pytest.raises(ValidationError):
        ViewRequest(center_on=dict(entity_type="part", predicate=dict(kind="parts", ids=[0])))


def test_preset_round_trip_is_a_request_preset_not_a_captured_camera(tmp_path):
    request = ViewRequest(view="front", projection="parallel", zoom_scale=2.0)
    path, body = save_preset(tmp_path, "Front2x", request, BINDING, "t0")
    assert path.name == "front2x.json"
    assert body["kind"] == "request_preset" and body["native_camera_captured"] is False
    loaded, stored = load_preset(tmp_path, "Front2x", BINDING)
    assert loaded == request and stored["payload_sha256"] == body["payload_sha256"]
    assert [p.name for p in tmp_path.iterdir()] == ["front2x.json"]


def test_existing_name_is_never_overwritten_case_insensitively(tmp_path):
    request = ViewRequest(view="front", projection="parallel")
    path, _ = save_preset(tmp_path, "home", request, BINDING, "t0")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        save_preset(tmp_path, "HOME", ViewRequest(view="top", projection="parallel"), BINDING, "t1")
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["home.json"]


@pytest.mark.parametrize("name", ["", "../x", "a/b", "a.b", "1abc", "con", "LPT1", "a" * 65, None, "név"])
def test_unsafe_preset_names_are_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        preset_path(tmp_path, name)


def test_non_replayable_or_selector_requests_cannot_be_saved(tmp_path):
    for request in (ViewRequest(view="front"), ViewRequest(rotation_xyz_degrees=[0, 0, 5])):
        with pytest.raises(ValueError, match="explicit standard view"):
            save_preset(tmp_path, "x", request, BINDING, "t0")
    assert not list(tmp_path.iterdir())


def test_corrupt_edited_or_rebound_presets_are_rejected(tmp_path):
    request = ViewRequest(view="front", projection="parallel")
    path, _ = save_preset(tmp_path, "p", request, BINDING, "t0")
    original = path.read_bytes()
    body = json.loads(original)
    body["request"]["zoom_scale"] = 3.0
    path.write_text(json.dumps(body), encoding="utf8")
    with pytest.raises(ValueError, match="corrupt or was edited"):
        load_preset(tmp_path, "p", BINDING)
    path.write_bytes(original[:-5])
    with pytest.raises(ValueError, match="corrupt"):
        load_preset(tmp_path, "p", BINDING)
    path.write_bytes(original)
    rebound = BINDING.model_copy(update=dict(model_generation="g2"))
    with pytest.raises(ValueError, match="different model"):
        load_preset(tmp_path, "p", PresetBinding.model_validate(rebound.model_dump()))
    body = json.loads(original)
    body["schema"] = "ViewPreset/v0"
    path.write_text(json.dumps(body), encoding="utf8")
    with pytest.raises(ValueError, match="schema"):
        load_preset(tmp_path, "p", BINDING)
    with pytest.raises(ValueError, match="Unknown"):
        load_preset(tmp_path, "missing", BINDING)


def test_binding_requires_identity_for_its_context():
    with pytest.raises(ValidationError):
        PresetBinding(context="session", session_id="a" * 32, model_kind="keyword")
    with pytest.raises(ValidationError):
        PresetBinding(context="batch", model_kind="keyword")


def _png(path, pixels, **options):
    Image.fromarray(pixels).save(path, format="PNG", **options)
    return path


def test_pixel_identity_ignores_compression_but_not_one_pixel(tmp_path):
    pixels = np.full((40, 40, 4), 255, dtype=np.uint8)
    pixels[10:20, 10:20] = [100, 0, 0, 255]
    first = _png(tmp_path / "a.png", pixels, compress_level=1)
    second = _png(tmp_path / "b.png", pixels, compress_level=9)
    assert first.read_bytes() != second.read_bytes()
    same = compare_png_pixels(first, second)
    assert same["identical"] and same["differing_pixels"] == 0
    assert same["images"][0]["pixel_sha256"] == same["images"][1]["pixel_sha256"]
    changed = pixels.copy()
    changed[0, 0] = [254, 255, 255, 255]
    one = compare_png_pixels(first, _png(tmp_path / "c.png", changed))
    assert not one["identical"] and one["differing_pixels"] == 1 and one["max_channel_delta"] == 1
    alpha = pixels.copy()
    alpha[5, 5, 3] = 0
    assert not compare_png_pixels(first, _png(tmp_path / "d.png", alpha))["identical"]


def test_pixel_identity_rejects_dimension_changes_and_non_png(tmp_path):
    first = _png(tmp_path / "a.png", np.zeros((40, 40, 3), dtype=np.uint8))
    wider = _png(tmp_path / "b.png", np.zeros((40, 41, 3), dtype=np.uint8))
    result = compare_png_pixels(first, wider)
    assert not result["identical"] and not result["same_dimensions"] and result["differing_pixels"] is None
    Image.fromarray(np.zeros((40, 40, 3), dtype=np.uint8)).save(tmp_path / "c.bmp", format="BMP")
    with pytest.raises(ValueError, match="PNG"):
        compare_png_pixels(first, tmp_path / "c.bmp")
