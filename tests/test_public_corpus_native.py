"""I04 public samples: immutable inputs, reopen and explicit numerical oracles.

Features describe the input, not certification of every quantity it contains.
All data, exports and detailed reports remain under external --native-output.
"""
import csv
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.native.versions import profile
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import entries, load_registry, plain_path, read_catalogs, resolve
from tools.public_corpus_preflight import directory_snapshot, input_classification, input_tree

CASE_FILE = Path(__file__).parent / "corpus/public_cases.json"
CASES = json.loads(CASE_FILE.read_text(encoding="utf8"))["cases"]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked(record, name, result):
    record["checks"].append(dict(name=name, status=result.get("status"), error=result.get("error")))
    assert result.get("status") == "succeeded", (name, result.get("error"))
    return result


def curve_rows(result):
    with Path(result["artifacts"][0]["path"]).open(encoding="utf8", newline="") as stream:
        return list(csv.DictReader(stream))


def compare_node_rows(before, after):
    import numpy as np

    left, right = ({int(row[0]): row[1:] for row in rows} for rows in (before, after))
    assert len(left) == len(before) and len(right) == len(after), "Duplicate user node IDs"
    assert left.keys() == right.keys(), "User node IDs changed during save/reopen"
    for uid in left:
        assert np.allclose(left[uid], right[uid], rtol=1e-7, atol=1e-9), (uid, left[uid], right[uid])


def unsupported(record, request, reason):
    record.update(status="unsupported", reason=reason)
    request.node.user_properties.append(("native_scope", "evidence_only"))
    pytest.xfail(reason)


@pytest.fixture(scope="module")
def public_registry(pytestconfig):
    if not pytestconfig.getoption("--run-native"):
        pytest.skip("Public corpus execution requires --run-native")
    raw = os.environ.get("LSPP_CORPUS_DIR")
    if not raw:
        pytest.fail("Set LSPP_CORPUS_DIR to the external corpus root")
    root = plain_path(Path(raw)).resolve(strict=True)
    registry = load_registry()
    records, manifests = read_catalogs(registry, root)
    return root, entries(registry), records, manifests


@pytest.fixture
def public_case(case, public_registry, pytestconfig, request):
    root, registry, catalog, manifests = public_registry
    base = resolve(registry[case["corpus"]], root)
    source = plain_path(base / case["member"] if case["member"] else base).resolve(strict=True)
    assert source.is_relative_to(root) and "local-book" not in source.relative_to(root).parts
    family = [source]
    if case["kind"] == "d3plot":
        family += sorted(p for p in source.parent.iterdir() if p.is_file()
                         and re.fullmatch(re.escape(source.name) + r"\d+", p.name))
    if "mpp" in case["features"]:
        family = sorted(p for p in source.parent.iterdir() if re.fullmatch(r"binout\d+", p.name))
        assert len(family) > 1
    tree, tree_identities = input_tree(source, family, keyword=case["kind"] == "keyword")
    directory_before = directory_snapshot([source, *tree_identities])
    identities = {}
    for path in family:
        relative = path.relative_to(root).as_posix()
        identities[relative] = sha(path)
        assert identities[relative] == catalog[relative]["sha256"], relative
    executable = pytestconfig.getoption("--native-executable")
    assert executable, "Set --native-executable"
    directory = pytestconfig._native_root / hashlib.sha256(case["id"].encode()).hexdigest()[:8]
    directory.mkdir()
    service = Service(Settings(directory, Path(executable),
                               (root / "public-keyword", root / "public-results", directory), timeout=120))
    record = dict(case=case["id"], corpus=case["corpus"], member=case["member"],
                  input_features=case["features"], status="running", checks=[],
                  source_identities=identities, external_manifest_identities=manifests,
                  input_tree=tree, tree_sha256=tree["tree_sha256"], tree_sha256_version=tree["tree_sha256_version"],
                  native_installation=dict(executable=str(Path(executable).resolve()), **profile(Path(executable))))
    evidence = directory / "public-case.json"
    request.node.user_properties.append(("native_evidence", str(evidence)))
    try:
        yield service, source, record
        # Pytest does not throw test-body exceptions back into yield fixtures.
        # Use the already-recorded call outcome, never a successful teardown.
        outcome = pytestconfig._native_rows.get(request.node.nodeid, {})
        if record["status"] not in ("unsupported", "input_limited"):
            record["status"] = "succeeded" if outcome.get("status") == "passed" else "failed"
            if record["status"] == "failed":
                record["failure"] = outcome.get("reason", "No completed test verdict")
    except BaseException as exc:
        if record["status"] not in ("unsupported", "input_limited"):
            record.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
        raise
    finally:
        unchanged = all(sha(root / name) == digest for name, digest in identities.items())
        tree_unchanged = all(path.is_file() and sha(path) == digest for path, digest in tree_identities.items())
        directory_after = directory_snapshot([source, *tree_identities])
        record["source_directory_listing_unchanged"] = directory_before == directory_after
        record["source_directory_count"] = len(directory_before)
        record["source_directory_listing_sha256"] = hashlib.sha256(
            json.dumps(list(directory_before.values()), ensure_ascii=True).encode("ascii")).hexdigest()
        record["input_tree_unchanged"] = tree_unchanged
        record["originals_unchanged"] = unchanged and tree_unchanged
        atomic_json(evidence, record)
        assert unchanged and tree_unchanged, "Original corpus or INCLUDE tree bytes changed"
        assert directory_before == directory_after, "Source directory entries changed"


def keyword_round_trip(service, source, record):
    before = checked(record, "native_inventory", service.inspect_model(str(source)))
    assert before["data"]["counts"]["nodes"] > 0

    def nodes(path, label):
        rows = []
        for offset in range(0, before["data"]["counts"]["nodes"], 10000):
            page = checked(record, label + "_" + str(offset), service.list_nodes(path, offset=offset, limit=10000))
            rows.extend(page["data"]["rows"])
        assert len(rows) == before["data"]["counts"]["nodes"]
        return rows

    original_nodes = nodes(str(source), "reference_nodes")
    saved = checked(record, "save_keyword", service.export_keyword(str(source)))
    output = next(a["path"] for a in saved["artifacts"] if a["kind"] == "keyword")
    after = checked(record, "reopen_inventory", service.inspect_model(output))
    assert before["data"]["counts"] == after["data"]["counts"]
    compare_node_rows(original_nodes, nodes(output, "reopened_nodes"))
    record["scope"] = "Native counts and all reference-node IDs/coordinates through bounded pages; not all keyword card semantics"


def d3plot_cross_reader(service, source, record, request):
    import numpy as np

    from ls_prepost_mcp.post_backend import selected_database
    from ls_prepost_mcp.results import lasso_vectors

    native = checked(record, "native_inventory", service.inspect_model(str(source), "d3plot"))["data"]
    reader = service.inspect_d3plot_database(str(source))
    assert native["counts"]["nodes"] == reader["node_count"]
    assert native["counts"]["states"] == reader["state_count"]
    record["checks"].append(dict(name="independent_reader_counts", status="succeeded"))
    if not reader["state_count"]:
        unsupported(record, request, "No saved result states: inventory only, no numerical result certification")
    states = sorted({1, reader["state_count"]})
    db, rows = selected_database(source, states, ["node_displacement"])
    ids = db.arrays["node_ids"]
    indices = sorted({0, len(ids) // 2, len(ids) - 1})
    selected = [int(ids[i]) for i in indices]
    vectors = lasso_vectors(db.arrays, "displacement")
    result = checked(record, "native_displacement", service.extract_node_history(
        str(source), selected, "displacement", states, "source_native_units"))
    actual = curve_rows(result)
    assert len(actual) == len(states) * len(selected)
    errors = []
    for row in actual:
        state, uid = int(row["state"]), int(row["node_id"])
        index = indices[selected.index(uid)]
        expected = vectors[rows[state], index]
        observed = np.array([float(row[key]) for key in ("x", "y", "z")])
        assert np.allclose(observed, expected, rtol=2e-5, atol=1e-6), (state, uid, observed, expected)
        assert np.isclose(float(row["time"]), db.arrays["timesteps"][rows[state]], rtol=1e-6, atol=1e-9)
        errors.append(float(np.max(np.abs(observed - expected))))
    record.update(scope="Native/LASSO counts, sampled user IDs, first/last times and nodal displacement; thermal/stress quantities not certified",
                  numerical_backend="lsprepost", reference_backend="lasso", states=states,
                  sampled_ids=selected, max_absolute_error=max(errors))


def binout_round_trip(service, source, record, case, request):
    import numpy as np

    from ls_prepost_mcp.results import open_binout

    try:
        inventory = service.inspect_binout(str(source))
    except ValueError as exc:
        if "Multiple MPP binout shards detected" in str(exc):
            unsupported(record, request, "Legacy tools reject multi-shard input; Claude Q06 integration pending")
        raise
    for branch in case["branches"]:
        assert branch in inventory["children"]
        with open_binout(str(source)) as db:
            variables = db.read(branch)
            priority = ["x_force", "force_x", "axial", "kinetic_energy", "internal_energy"]
            variable = next((name for name in priority if name in variables), None)
            assert variable, (branch, variables)
            times = np.asarray(db.read(branch, "time"))
            values = np.asarray(db.read(branch, variable))
            entity = None
            if values.ndim == 2:
                ids = np.asarray(db.read(branch, "ids")).reshape(-1)
                assert values.shape[1] == len(ids)
                entity = int(ids[len(ids) // 2])
                values = values[:, len(ids) // 2]
        result = checked(record, branch, service.extract_binout_curve(str(source), branch, variable,
                         "source_native_units", entity_id=entity))
        actual = np.array([[float(row["time"]), float(row["value"])] for row in curve_rows(result)])
        expected = np.column_stack((times, values))
        assert actual.shape == expected.shape and np.allclose(actual, expected, rtol=1e-12, atol=1e-12)
        record["checks"][-1].update(variable=variable, entity_id=entity, samples=len(times))
    record["scope"] = "LASSO extraction/CSV identity and entity-axis checks; not independent native force validation"


def ascii_cross_check(service, source, record, case, request):
    import numpy as np

    try:
        result = service.extract_native_ascii_curve(str(source), case["database"], case["component"],
                                                    "source_native_units", entity_id=case["entity_id"])
    except ValueError as exc:
        if str(exc) == "Unsupported native ASCII database":
            unsupported(record, request, "Legacy native ASCII tool does not support " + case["database"])
        raise
    checked(record, "native_ascii_curve", result)
    expected = []
    for line in source.read_text(errors="strict").splitlines():
        fields = line.split()
        if len(fields) == 6 and fields[0] == str(case["entity_id"]):
            expected.append([float(fields[1]), float(fields[2])])
    assert len(expected) > 1
    actual = [[float(row["time"]), float(row["value"])] for row in curve_rows(result)]
    assert np.shape(actual) == np.shape(expected) and np.allclose(actual, expected, rtol=2e-5, atol=1e-8)
    record["scope"] = "Native SECFORC component 1 compared to the fixture's labeled x-force records"


@pytest.mark.native
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_public_corpus(case, public_case, request):
    service, source, record = public_case
    if case["kind"] == "keyword":
        if not record["input_tree"]["ok"]:
            reason = "输入限制：" + input_classification(record["input_tree"])
            record.update(status="input_limited", reason=reason)
            request.node.user_properties.append(("native_scope", "evidence_only"))
            pytest.xfail(reason)
        keyword_round_trip(service, source, record)
    elif case["kind"] == "d3plot":
        d3plot_cross_reader(service, source, record, request)
    elif case["kind"] == "binout":
        binout_round_trip(service, source, record, case, request)
    else:
        ascii_cross_check(service, source, record, case, request)
