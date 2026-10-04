import pytest

from ls_prepost_mcp.scene_state import fringe_coverage, require_movie_field_coverage


def test_movie_cannot_use_sparse_mixed_or_uncertain_custom_fields():
    definition = dict(domain="solid", field="stress_x", units="Pa", parts=[1])
    first = fringe_coverage(None, definition, 1, "a")
    with pytest.raises(ValueError, match="not defined"):
        require_movie_field_coverage(dict(managed_fringe=first), 2)
    second = fringe_coverage(first, definition, 2, "b")
    assert require_movie_field_coverage(dict(managed_fringe=second), 2)["frames"] == {"1": "a", "2": "b"}
    other = fringe_coverage(second, dict(definition, field="stress_y"), 3, "c")
    assert other["frames"] == {"3": "c"}
    with pytest.raises(ValueError):
        require_movie_field_coverage(dict(managed_fringe=other), 3)
    with pytest.raises(ValueError, match="uncertain"):
        require_movie_field_coverage(dict(managed_fringe=dict(second, status="changed_by_raw_command")), 2)
    assert require_movie_field_coverage({}, 2) is None


def test_static_physical_blank_is_not_a_per_state_movie_mask():
    field = fringe_coverage(None, dict(domain="solid", validity_policy="alive"), 1, "a")
    with pytest.raises(ValueError, match="per-state visibility"):
        require_movie_field_coverage(dict(managed_fringe=field), 1)
