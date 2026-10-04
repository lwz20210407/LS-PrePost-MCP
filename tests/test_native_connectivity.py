import json
from types import SimpleNamespace

import pytest

from ls_prepost_mcp.embedded import BeamSafeDataCenter


def test_beam_readback_avoids_faulty_array_binding_and_requires_exact_registry(tmp_path):
    def get(key, **kwargs):
        if key == "element_connectivity":
            raise AssertionError("Faulty beam getter must never be called")
        if key == "element_ids":
            return [201, 202]
        return "native-pass-through"
    native = SimpleNamespace(get_data=get, Type=SimpleNamespace(BEAM=1))
    (tmp_path/"beam-count.json").write_text(json.dumps(2))
    path = tmp_path/"beam-connectivity.k"
    path.write_text("*KEYWORD\n*ELEMENT_BEAM\n201,3,9,10,0\n202,3,11,12,0\n*END\n")
    proxy = BeamSafeDataCenter(native, tmp_path)
    assert proxy.get_data("element_connectivity", type=1, id=201) == [9, 10]
    assert proxy.get_data("num_nodes") == "native-pass-through"
    for body in ("201,3,9,10,0\n", "201,3,9,10,0\n201,3,11,12,0\n", "201,3,0,10,0\n202,3,11,12,0\n"):
        path.write_text("*ELEMENT_BEAM\n"+body)
        with pytest.raises(ValueError):
            BeamSafeDataCenter(native, tmp_path)


def test_fixed_width_native_beam_export_and_missing_count(tmp_path):
    native = SimpleNamespace(get_data=lambda *a, **k: [50000101], Type=SimpleNamespace(BEAM=1))
    (tmp_path/"beam-count.json").write_text("1")
    (tmp_path/"beam-connectivity.k").write_text("*ELEMENT_BEAM\n"+"".join(f"{v:8d}" for v in (50000101, 3, 10000001, 10000002, 0))+"\n*END\n")
    assert BeamSafeDataCenter(native, tmp_path).beams == {50000101: [10000001, 10000002]}
    (tmp_path/"beam-count.json").write_text("0")
    with pytest.raises(ValueError, match="count"):
        BeamSafeDataCenter(native, tmp_path)


def test_proxy_preserves_positional_node_type_without_exposing_beam_getter(tmp_path):
    calls = []
    def get(key, *args, **kwargs):
        if key == "element_connectivity":
            raise AssertionError("Unsafe native beam getter called")
        calls.append((key, args, kwargs))
        return [201] if key == "element_ids" else [1.,2.]
    native = SimpleNamespace(get_data=get, Type=SimpleNamespace(BEAM=1, NODE=0))
    (tmp_path/"beam-count.json").write_text("1")
    (tmp_path/"beam-connectivity.k").write_text("*ELEMENT_BEAM\n201,3,9,10,0\n")
    proxy = BeamSafeDataCenter(native, tmp_path)
    assert proxy.get_data("node_x", 0, ist=2) == [1.,2.]
    assert calls[-1] == ("node_x", (0,), {"ist":2})
    assert proxy.get_data("element_connectivity", 1, id=201) == [9,10]
    with pytest.raises(ValueError, match="explicit id"):
        proxy.get_data("element_connectivity", 1, 201)
