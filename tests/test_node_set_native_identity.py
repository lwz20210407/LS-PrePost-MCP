"""A source-bound storage rule needs the complete independent native ID/rank table."""
import copy
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

from tools.verify_node_set_user_ids import EXPECTED, NODE_IDS, PROGRAM, validate


def capture(base=0):
    # The native registry iteration order may differ; verify ranks explicitly.
    mapping = {uid: base + i for i, uid in enumerate(NODE_IDS)}
    return dict(protocol="named_node_id_roundtrip_v1", node_ids=[89, 121, 11, 37],
        mapping=[dict(user_id=uid, internal_id=i, roundtrip_user_id=uid) for uid, i in mapping.items()],
        sets=[dict(sid=sid, raw_ids_inset=[mapping[uid] + 1 for uid in members]) for sid, members in EXPECTED.items()])


def test_mapping_admits_one_based_set_slots_only_after_the_full_native_rank_proof():
    result = validate(capture())
    assert result["status"] == "passed"
    assert [row["native_user_ids"] for row in result["sets"]] == list(EXPECTED.values())
    assert all(row["membership_equal"] and row["definition_order_equal"] for row in result["sets"])


def test_a_reversible_but_differently_based_native_table_is_not_silently_shifted():
    with pytest.raises(ValueError):
        validate(capture(1))


def test_a_full_bijection_with_different_sorted_ranks_is_not_admitted():
    raw = capture()
    raw["mapping"][0]["internal_id"], raw["mapping"][1]["internal_id"] = 1, 0
    with pytest.raises(ValueError):
        validate(raw)


def test_membership_and_native_order_are_reported_separately():
    raw = capture()
    raw["sets"][2]["raw_ids_inset"].reverse()
    result = validate(raw)
    assert result["sets"][2]["membership_equal"] is True
    assert result["sets"][2]["definition_order_equal"] is False


def test_observed_three_set_shapes_resolve_to_the_independent_user_id_oracle():
    raw = capture()
    raw["sets"] = [dict(sid=101, raw_ids_inset=[4, 2]), dict(sid=202, raw_ids_inset=[1, 2, 3]),
                   dict(sid=303, raw_ids_inset=[1, 2, 3, 4])]
    result = validate(raw)
    assert [row["native_user_ids"] for row in result["sets"]] == [[121, 37], [11, 37, 89], [11, 37, 89, 121]]
    assert [row["membership_equal"] for row in result["sets"]] == [True, True, True]
    assert [row["definition_order_equal"] for row in result["sets"]] == [True, True, False]


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


@pytest.mark.parametrize("missing", ["src/ls_prepost_mcp/model_target_tools.py",
    "src/ls_prepost_mcp/domain/model/contact_report.py", "src/ls_prepost_mcp/domain/model/contact.py",
    "src/ls_prepost_mcp/domain/model/operations.py"])
def test_missing_product_source_rejects_before_native_or_configuration_io(tmp_path, monkeypatch, missing):
    from tools import verify_node_set_user_ids as verifier

    identity = verifier.execution_identity(verifier.ROOT)
    identity["working_tree_dirty"] = False  # isolate source admission from the dirty-tree guard
    del identity["source_files"][missing]
    monkeypatch.setattr(verifier, "execution_identity", lambda root: identity)

    def forbidden(*args, **kwargs):
        pytest.fail("Missing source must reject before process/configuration/native IO")

    for name in ("native_processes", "require_installation", "locate_config", "Service"):
        monkeypatch.setattr(verifier, name, forbidden)
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match="required P04 capture source"):
        verifier.run(tmp_path / "not-used.exe", output)
    assert not output.exists()


def test_p04_product_scope_includes_the_executed_check_helpers_without_touching_other_capture_scopes():
    from tools import verify_node_set_user_ids as verifier
    from tools import verify_p05_boundary_roundtrip as p05
    from tools import verify_p12_joint_roundtrip as p12

    assert len(verifier.PRODUCT_PATHS) == len(set(verifier.PRODUCT_PATHS)) == 13
    assert {"src/ls_prepost_mcp/model_target_tools.py", "src/ls_prepost_mcp/domain/model/contact_report.py",
            "src/ls_prepost_mcp/domain/model/contact.py"} <= set(verifier.PRODUCT_PATHS)
    p04_instrumentation = {"tools/verify_node_set_user_ids.py", "tests/test_node_set_native_identity.py",
                           "tests/test_node_set_native_membership_evidence.py"}
    assert p04_instrumentation.isdisjoint(p05.CAPTURE_SOURCE_PATHS)
    assert p04_instrumentation.isdisjoint(p12.CAPTURE_SOURCE_PATHS)


def test_each_product_proof_keeps_the_actual_full_snapshot_hash(tmp_path, monkeypatch):
    from tools import verify_node_set_user_ids as verifier

    paths = ("selected/source.py",)
    target = tmp_path / paths[0]
    target.parent.mkdir()
    target.write_bytes(b"# owned source\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    identity = dict(actual_git_head="a" * 40, source_files={paths[0]: digest})
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    monkeypatch.setattr(verifier, "PRODUCT_PATHS", paths)
    monkeypatch.setattr(verifier.subprocess, "check_output", lambda *args, **kwargs: "b" * 40 + "\n")
    assert verifier.source_identity(identity) == [dict(path=paths[0], git_blob_id="b" * 40, captured_file_sha256=digest)]
    target.write_bytes(b"# changed after snapshot\n")
    with pytest.raises(ValueError, match="required P04 capture source"):
        verifier.source_identity(identity)
