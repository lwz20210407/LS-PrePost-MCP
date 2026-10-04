import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.entity_cards import element_set_fragment, inspect_cards, verify_cards
from ls_prepost_mcp.service import Service


@pytest.mark.parametrize("kind", ["shell", "solid", "beam"])
def test_more_than_eight_sparse_members_and_domain_specific_header(tmp_path, kind):
    members = [11, 23, 48, 55, 69, 80, 110, 201, 501, 987]
    text, attrs = element_set_fragment(kind, 41, "Multirow", members)
    path = tmp_path / "set.k"
    path.write_text(text)
    record = inspect_cards(path)["sets"][(kind, 41)]
    assert record["member_ids"] == members
    assert all(record[k] == v for k, v in attrs.items())
    assert record["attributes"] == ([0.0] * 4 if kind == "shell" else [])
    assert record["solver"] == ("MECH" if kind == "solid" else None)
    assert record["its"] == ("0" if kind == "solid" else None)


def test_same_sid_is_separate_across_node_part_and_element_set_domains(tmp_path):
    path = tmp_path / "domains.k"
    text = "*KEYWORD\n*SET_NODE_LIST\n41\n1\n*SET_PART_LIST\n41\n1\n"
    for kind in ("shell", "solid", "beam"):
        fragment, _ = element_set_fragment(kind, 41, kind, [101])
        text += fragment.removeprefix("*KEYWORD\n").removesuffix("*END\n")
    path.write_text(text + "*END\n")
    assert set(inspect_cards(path)["sets"]) == {(k, 41) for k in ("node", "part", "shell", "solid", "beam")}


@pytest.mark.parametrize(
    "kind, header", [("shell", "41,0.1,0.2,0.3,0.4"), ("solid", "41,CESE,3"), ("beam", "41")]
)
def test_existing_native_headers_are_read_without_node_header_assumptions(tmp_path, kind, header):
    keyword = {"shell": "SET_SHELL_LIST", "solid": "SET_SOLID", "beam": "SET_BEAM"}[kind]
    path = tmp_path / "set.k"
    path.write_text(f"*KEYWORD\n*{keyword}\n{header}\n1001,2002,0\n*END\n")
    record = inspect_cards(path)["sets"][(kind, 41)]
    assert record["member_ids"] == [1001, 2002]
    if kind == "shell":
        assert record["attributes"] == [0.1, 0.2, 0.3, 0.4]
    if kind == "solid":
        assert (record["solver"], record["its"]) == ("CESE", "3")


@pytest.mark.parametrize("keyword", ["SET_SHELL_LIST_GENERATE", "SET_SOLID_GENERATE", "SET_BEAM_COLLECT"])
def test_other_variants_remain_explicitly_unresolved(tmp_path, keyword):
    path = tmp_path / "variant.k"
    path.write_text(f"*KEYWORD\n*{keyword}\n41\n1,9\n*END\n")
    result = inspect_cards(path)
    assert not result["sets"] and result["unresolved"][0][0] == "*" + keyword


@pytest.mark.parametrize("kind", ["shell", "solid", "beam"])
def test_wrong_domain_and_duplicate_sid_reject_before_import(tmp_path, monkeypatch, kind):
    path = tmp_path / "before.k"
    fragment, _ = element_set_fragment(kind, 41, "Before", [10])
    path.write_text(fragment)
    service = Service(Settings(tmp_path))

    def edit(sid, action, params, commands, verify, precheck, postcheck, preflight, **kwargs):
        assert kwargs["snapshot_parameters"]["entity_type"] == kind
        with pytest.raises(ValueError, match="unknown"):
            precheck(dict(registry_matches=[]))
        preflight(path)
        pytest.fail("Colliding set must not reach native import")

    monkeypatch.setattr(service, "_gui_mesh_edit", edit)
    with pytest.raises(ValueError, match="already exists"):
        service.create_gui_entity_set("unused", kind, 41, "New", entity_ids=[10])


def test_adding_a_set_preserves_unrelated_element_sets(tmp_path):
    base, _ = element_set_fragment("shell", 1, "Existing", [101])
    new, attrs = element_set_fragment("solid", 1, "Added", [202])
    p = tmp_path / "before.k"
    p.write_text(base)
    before = inspect_cards(p)
    p = tmp_path / "after.k"
    p.write_text(base.removesuffix("*END\n") + new.removeprefix("*KEYWORD\n"))
    after = inspect_cards(p)
    expected = dict(entity_type="solid", set_id=1, title="Added", member_ids=[202], **attrs)
    assert verify_cards(before, after, new_set=expected)["unrelated_native_cards_preserved"]
    after["sets"][("shell", 1)]["member_ids"] = [999]
    with pytest.raises(ValueError, match="Unrequested set"):
        verify_cards(before, after, new_set=expected)


def test_element_set_replacement_does_not_bypass_consumer_impact_analysis(tmp_path):
    with pytest.raises(ValueError, match="consumer impact"):
        Service(Settings(tmp_path)).create_gui_entity_set(
            "unused", "solid", 1, "Changed", entity_ids=[1], mode="replace_members"
        )


def test_short_format_overflow_rejected_instead_of_truncated():
    with pytest.raises(ValueError, match="ten columns"):
        element_set_fragment("solid", 1, "Overflow", [10**10])
