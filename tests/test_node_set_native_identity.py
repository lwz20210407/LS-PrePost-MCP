"""Independent exact ID mapping; neither numbering base nor vector ownership is guessed."""
import copy
import json
import sys
from types import SimpleNamespace

import pytest

from tools.verify_node_set_user_ids import EXPECTED, NODE_IDS, PROGRAM, validate


def capture(base=1):
    # Deliberately unrelated to array order, user ID magnitude or sorted members.
    mapping = dict(zip(NODE_IDS, (base + 2, base, base + 3, base + 1)))
    return dict(protocol="named_node_id_roundtrip_v1", node_ids=[89, 121, 11, 37],
        mapping=[dict(user_id=uid, internal_id=i, roundtrip_user_id=uid) for uid, i in mapping.items()],
        sets=[dict(sid=sid, raw_ids_inset=[mapping[uid] for uid in members]) for sid, members in EXPECTED.items()])


@pytest.mark.parametrize("base", [0, 1])
def test_mapping_uses_the_observed_inverse_without_guessing_a_base(base):
    result = validate(capture(base))
    assert result["status"] == "passed"
    assert [row["native_user_ids"] for row in result["sets"]] == list(EXPECTED.values())
    assert all(row["membership_equal"] and row["definition_order_equal"] for row in result["sets"])


def test_membership_and_native_order_are_reported_separately():
    raw = capture()
    raw["sets"][2]["raw_ids_inset"].reverse()
    result = validate(raw)
    assert result["sets"][2]["membership_equal"] is True
    assert result["sets"][2]["definition_order_equal"] is False


@pytest.mark.parametrize("bad", [True, False, 1.5, "1", None, -1, 5])
def test_malformed_internal_identity_is_not_coerced_or_rebased(bad):
    raw = capture()
    raw["mapping"][0]["internal_id"] = bad
    with pytest.raises(ValueError):
        validate(raw)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(error=dict(type="RuntimeError", message="mapping failed")),
    lambda r: r.update(node_ids=[11, 37, 89]),
    lambda r: r.update(node_ids=[11, 37, 89, True]),
    lambda r: r["mapping"].pop(),
    lambda r: r["mapping"][0].update(roundtrip_user_id=37),
    lambda r: r["mapping"][0].update(roundtrip_user_id=True),
    lambda r: r["mapping"][0].update(user_id=37),
    lambda r: r["mapping"][0].update(internal_id=r["mapping"][1]["internal_id"]),
    lambda r: r["sets"].pop(),
    lambda r: r["sets"][0].update(sid=999),
    lambda r: r["sets"][0].update(sid=True),
    lambda r: r["sets"][0].update(sid=202),
    lambda r: r["sets"][0].update(raw_ids_inset=[0, 1]),
    lambda r: r["sets"][0].update(raw_ids_inset=[1, 1]),
    lambda r: r["sets"][0].update(raw_ids_inset=[True, 2]),
    lambda r: r["sets"][0].update(raw_ids_inset=["1", 2]),
    lambda r: r["sets"][0]["raw_ids_inset"].pop(),
])
def test_incomplete_or_ambiguous_native_proofs_fail_closed(mutation):
    raw = copy.deepcopy(capture())
    mutation(raw)
    with pytest.raises(ValueError):
        validate(raw)


def test_embedded_capture_owns_vectors_before_the_next_sdk_call(tmp_path, monkeypatch):
    raw = capture()
    mapping = {r["user_id"]: r["internal_id"] for r in raw["mapping"]}
    inverse = {i: uid for uid, i in mapping.items()}
    sets = {row["sid"]: row["raw_ids_inset"] for row in raw["sets"]}
    shared = []
    calls = []

    def get_data(name, **kwargs):
        calls.append((name, kwargs))
        shared.clear()
        if name == "num_nodes":
            return 4
        if name == "node_ids":
            shared.extend(raw["node_ids"])
            return shared
        if name == "internal_id":
            return mapping[kwargs["id"]]
        if name == "user_id":
            return inverse[kwargs["id"]]
        if name == "ids_inset":
            shared.extend(sets[kwargs["id"]])
            return shared
        raise AssertionError("Unexpected native API")

    monkeypatch.setitem(sys.modules, "DataCenter", SimpleNamespace(get_data=get_data, Type=SimpleNamespace(NODE="node")))
    monkeypatch.chdir(tmp_path)
    exec(compile(PROGRAM, "owned-node-set-capture", "exec"), {})
    observed = json.loads((tmp_path / "node-set-identities.json").read_text())
    assert observed["node_ids"] == raw["node_ids"]
    assert observed["sets"] == raw["sets"]
    assert validate(observed)["status"] == "passed"
    assert len(calls) == 13  # count, registry, four exact inverse pairs, three sets.


def test_embedded_capture_does_not_send_a_bad_index_to_native(tmp_path, monkeypatch):
    calls = []

    def get_data(name, **kwargs):
        calls.append(name)
        return {"num_nodes": 4, "node_ids": list(NODE_IDS), "internal_id": -1}[name]

    monkeypatch.setitem(sys.modules, "DataCenter", SimpleNamespace(get_data=get_data, Type=SimpleNamespace(NODE="node")))
    monkeypatch.chdir(tmp_path)
    exec(compile(PROGRAM, "owned-node-set-capture", "exec"), {})
    observed = json.loads((tmp_path / "node-set-identities.json").read_text())
    assert "error" in observed and calls == ["num_nodes", "node_ids", "internal_id"]
    assert observed["failed_mapping"] == dict(user_id=11, internal_repr="-1")
    with pytest.raises(ValueError):
        validate(observed)


def test_the_fixture_is_really_created_by_the_existing_mcp_api(tmp_path):
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.domain.model import KeywordDeck
    from ls_prepost_mcp.domain.model.node_sets import NodeSets
    from ls_prepost_mcp.service import Service
    from tools.verify_node_set_user_ids import OPERATIONS, SOURCE

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "main.k"
    source.write_text(SOURCE, encoding="ascii")
    original = source.read_bytes()
    service = Service(Settings(tmp_path / "work", allowed_roots=(source_dir,)))
    created = service.create_entities(str(source), OPERATIONS)
    assert created["status"] == "succeeded", created.get("error")
    resolver = NodeSets(KeywordDeck.load(created["data"]["main"]))
    assert [resolver.resolve(sid) for sid in EXPECTED] == list(EXPECTED.values())
    assert source.read_bytes() == original
    assert sorted(p.name for p in source_dir.iterdir()) == ["main.k"]


def test_directory_identity_includes_new_entries_and_empty_directories(tmp_path):
    from tools.verify_node_set_user_ids import _directory

    (tmp_path / "main.k").write_text("*KEYWORD\n*END\n")
    before = _directory(tmp_path)
    (tmp_path / "new-empty-dir").mkdir()
    assert _directory(tmp_path) != before
    assert _directory(tmp_path)["new-empty-dir"] == dict(kind="directory")
