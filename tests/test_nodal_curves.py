import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def test_nodal_request_preserves_contract_and_curve_output_order(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(
        service, "_native", lambda action, params, *args, **kwargs: dict(params=params, **kwargs)
    )
    ids, states, components = [7, 91], [1, 3], ["z", "x"]
    result = service.extract_node_history("unused", ids, "displacement", states, "mm", components, "ms")
    ids.append(12)
    states.append(5)
    components.clear()
    assert result["params"]["node_ids"] == [7, 91]
    assert result["params"]["states"] == [1, 3]
    assert result["params"]["curve_components"] == ["z", "x"]
    assert result["params"]["field_spec"]["sampling"]["kind"] == "not_applicable"
    assert result["params"]["preserve_state"]
    assert [name for name, kind in result["artifacts"]] == [
        "nodal.csv",
        "node_7_z.csv",
        "node_7_x.csv",
        "node_91_z.csv",
        "node_91_x.csv",
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        dict(node_ids=[True]),
        dict(states=[False]),
        dict(states=[2, 1]),
        dict(states=[1]),
        dict(curve_components=["x", "x"]),
        dict(curve_components=["../escape"]),
        dict(curve_components="x"),
        dict(time_unit=None),
        dict(quantity="position", curve_components=["magnitude"]),
        dict(node_ids=list(range(1, 102))),
    ],
)
def test_invalid_scalar_curve_requests_fail_before_native_dispatch(tmp_path, overrides):
    service = Service(Settings(tmp_path))
    args = dict(
        d3plot="missing",
        node_ids=[7],
        quantity="displacement",
        states=[1, 2],
        units="mm",
        curve_components=["x"],
        time_unit="ms",
    )
    args.update(overrides)
    with pytest.raises(ValueError):
        service.extract_node_history(**args)
    assert not (tmp_path / "jobs").exists()
