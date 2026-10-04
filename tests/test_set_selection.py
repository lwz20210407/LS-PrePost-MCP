import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import inspect_cards
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.set_selection import prepare_set_selection, union_members


def index(tmp_path, text):
    path = tmp_path / "sets.k"
    path.write_text("*KEYWORD\n" + text + "\n*END\n")
    return inspect_cards(path)


def test_union_deduplicates_members_not_set_domains_and_keeps_empty_set(tmp_path):
    data = index(
        tmp_path,
        "*SET_NODE_LIST\n1\n10,20\n*SET_NODE_LIST\n2\n20,30\n*SET_NODE_LIST\n3\n*SET_PART_LIST\n1\n999",
    )
    members, counts = union_members(data, "node", [1, 2, 3])
    assert members == [10, 20, 30] and counts == {"1": 2, "2": 2, "3": 0}
    assert union_members(data, "part", [1])[0] == [999]
    assert union_members(data, "node", [3])[0] == []
    with pytest.raises(ValueError, match="budget"):
        union_members(data, "node", [1, 2], limit=2)
    with pytest.raises(ValueError, match="does not exist"):
        union_members(data, "solid", [1])


def test_unknown_same_domain_variant_is_not_silently_expanded(tmp_path):
    data = index(tmp_path, "*SET_NODE_LIST_GENERATE\n1\n10,100")
    with pytest.raises(ValueError, match="Unsupported"):
        union_members(data, "node", [1])


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(entity_type="node", set_ids=[]),
        dict(entity_type="node", set_ids=[True]),
        dict(entity_type="node", set_ids=[1, 1]),
        dict(entity_type="element", set_ids=[1]),
        dict(entity_type="node", set_ids=[1], entity_ids=[1]),
        dict(entity_type="node", set_ids=[1], part_ids=[1]),
    ],
)
def test_invalid_set_selection_rejects_before_native_calls(tmp_path, kwargs):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).select_gui_entities("unused", **kwargs)


def test_resolver_uses_fresh_export_and_preserves_predicate_scope(tmp_path, monkeypatch):
    import ls_prepost_mcp.set_selection as module

    path = tmp_path / "model.k"
    path.write_text("*KEYWORD\n*SET_NODE_LIST\n5\n101,103\n*END\n")
    seen = []

    class Manager:
        def read(self, sid):
            return dict(model_kind="keyword")

        def dispatch(self, sid, action, params, **kwargs):
            seen.append(kwargs)
            return dict(status="succeeded", data={}, job_directory=str(tmp_path))

    monkeypatch.setattr(module, "stable_scene", lambda before, after: None)
    verification = {}
    params = dict(
        entity_type="node",
        registry_query=dict(entity_ids=None, part_ids=None, invert=True, scope="active_parts"),
    )
    assert prepare_set_selection("node", [5], verification)(Manager(), "sid", params) is None
    assert params["registry_query"] == dict(
        entity_ids=[101, 103], part_ids=None, invert=True, scope="active_parts"
    )
    assert seen[1]["export"] is True
    assert verification["set_source"]["set_ids"] == [5]
    assert verification["set_source"]["union_count"] == 2


def test_result_model_is_not_implicitly_associated_with_keyword_sets():
    class Manager:
        def read(self, sid):
            return dict(model_kind="d3plot")

        def dispatch(self, *args, **kwargs):
            pytest.fail("Result set resolution must reject before export")

    with pytest.raises(ValueError, match="keyword model"):
        prepare_set_selection("node", [1], {})(Manager(), "sid", {})


def test_selection_records_set_ids_instead_of_expanded_member_constants(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))

    def select(sid, action, arguments, kind, choose, **kwargs):
        assert arguments["set_ids"] == [5]
        assert arguments["entity_ids"] is None
        assert callable(kwargs["prepare_snapshot"])

    monkeypatch.setattr(service, "_select_gui", select)
    service.select_gui_entities("unused", "node", set_ids=[5])


def test_old_bridge_cannot_turn_a_set_selection_into_select_all(tmp_path, monkeypatch):
    service = Service(Settings(tmp_path))

    def edit(sid, action, arguments, commands, verify, precheck, **kwargs):
        precheck(dict(part_ids=[], part_visibility={}, query_selected_ids=None))
        pytest.fail("Old bridge must not use the unfiltered choose() fallback")

    monkeypatch.setattr(service, "_gui_mesh_edit", edit)
    with pytest.raises(ValueError, match="whole-scope fallback"):
        service.select_gui_entities("unused", "node", set_ids=[5])
