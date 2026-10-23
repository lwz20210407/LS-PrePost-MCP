"""G04 shared-reader identity independently checked against headless DataCenter/SCL."""

import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results import lasso_backend as lb
from ls_prepost_mcp.service import Service
from tests.test_entity_query import keyword_model as keyword_model
from tests.test_entity_query import selection
from tests.test_save_model_native import installation as installation
from tools.fetch_corpus import entries, load_registry, plain_path, read_catalogs, resolve
from tools.public_corpus_preflight import directory_snapshot, input_tree

pytestmark = pytest.mark.native


@pytest.mark.parametrize("case", ["keyword-include", "public-solid", "public-shell"])
def test_entity_identity_matches_native_geometry_and_values(installation, pytestconfig, keyword_model, case):
    executable, binary, config_sha = installation
    root = pytestconfig._native_root / case
    root.mkdir()
    allowed = [root, keyword_model.parent]
    source = keyword_model
    source_kind, family, eid, pid = "keyword", "shell", 10, 7
    if case != "keyword-include":
        location = os.environ.get("LSPP_CORPUS_DIR")
        if not location:
            pytest.skip("Set LSPP_CORPUS_DIR to registered external public results")
        corpus = plain_path(Path(location))
        family = case.partition("-")[2]
        source = plain_path(resolve(entries(load_registry())[family + "_d3plot"], corpus))
        allowed.append(corpus / "public-results")
        arrays = lb._arrays(source, state_arrays=["timesteps"])
        eid = int(arrays[f"element_{family}_ids"][0])
        pid = int(lb._part_ids(arrays)[arrays[f"element_{family}_part_indexes"][0]])
        source_kind = "d3plot"
    service = Service(Settings(root / "work", executable, tuple(allowed), timeout=180))
    files = service._result_family(str(source)) if source_kind == "d3plot" else [source]
    tree, before = input_tree(source, files, keyword=source_kind == "keyword")
    listing = directory_snapshot(list(before))
    if source_kind == "d3plot":
        catalog, _ = read_catalogs(load_registry(), corpus)
        assert all(h == catalog[p.relative_to(corpus).as_posix()]["sha256"] for p, h in before.items())
    native_nodes = service.list_nodes(str(source), source_kind, limit=10)
    assert native_nodes["status"] == "succeeded", native_nodes.get("error")
    native_rows = native_nodes["data"]["rows"]
    ids = [int(r[0]) for r in native_rows]
    result = service.query_entities(str(source), selection("node", ids), source_kind=source_kind)
    expected_status = "succeeded" if source_kind == "keyword" else "partial"
    assert result["status"] == expected_status, result.get("error")
    rows = {r["entity_id"]: r for r in result["data"]["entities"]}
    for r in native_rows:
        np.testing.assert_allclose(rows[int(r[0])]["coordinates"], r[1:], rtol=1e-6, atol=1e-8)
    native_conn = service.get_element_connectivity(str(source), eid, family, source_kind)
    assert native_conn["status"] == "succeeded", native_conn.get("error")
    element = service.query_entities(str(source), selection(family, [eid]), source_kind=source_kind)
    assert element["status"] == expected_status, element.get("error")
    row = element["data"]["entities"][0]
    assert row["node_ids"] == native_conn["data"]["node_ids"] and row["part_id"] == pid
    if source_kind == "keyword":
        assert row["material_id"] == 3 and row["section_id"] == 2
    else:
        assert row["material_id"] is None and row["section_id"] is None
    result_error = None
    if source_kind == "d3plot":
        # Public shell has several stored points: compare nodal displacement without
        # assuming a stored-point-to-native-layer mapping for shell stress.
        domain = "solid" if family == "solid" else "node"
        uid = eid if domain == "solid" else ids[0]
        quantity = "sxx" if domain == "solid" else "displacement_z"
        state = len(lb.state_times(source))
        selected = service.query_entities(
            str(source),
            selection(domain, [uid]),
            source_kind="d3plot",
            state=state,
            quantity=quantity,
            units="source_native_units",
        )
        assert selected["status"] == "partial", selected.get("error")
        value = selected["data"]["entities"][0]["result"]["value"]
        if domain == "solid":
            canonical = service.extract_field(
                str(source),
                domain,
                quantity,
                state=state,
                mask="all",
                units="source_native_units",
                output_format="none",
            )
            assert canonical["status"] == "succeeded", canonical.get("error")
            assert value == canonical["data"]["values"][canonical["data"]["ids"].index(uid)]
        native = service.extract_native_fields(
            str(source), domain, [uid], [state], [quantity], "mid", "source_native_units"
        )
        assert native["status"] == "succeeded", native.get("error")
        with Path(native["artifacts"][0]["path"]).open(newline="", encoding="utf8") as f:
            native_values = list(csv.DictReader(f))
        assert len(native_values) == 1 and int(native_values[0]["entity_id"]) == uid
        native_value = float(native_values[0][quantity])
        np.testing.assert_allclose(value, native_value, rtol=2e-5, atol=1e-6)
        result_error = abs(value - native_value)
    identity = pytestconfig._native_identity
    proof = {k: identity[k] for k in ("working_tree_dirty", "git_diff_sha256", "git_diff_scope")}
    proof.update(
        case=case,
        actual_git_revision=identity["actual_git_head"],
        executable=binary,
        source_config_sha256=config_sha,
        query_status=result["status"],
        node_count=len(rows),
        source_tree_sha256=tree["tree_sha256"],
        result_error=result_error,
        connectivity_equal=True,
        material_known=source_kind == "keyword",
        source_unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in before.items()),
        directory_unchanged=directory_snapshot(list(before)) == listing,
    )
    jobs = []
    for job in service.jobs.root.glob("*/job.json"):
        data = json.loads(job.read_text(encoding="utf8"))
        p = data.get("process")
        if p:
            jobs.append(
                dict(
                    status=data["status"],
                    returncode=p.get("returncode"),
                    graphics=p.get("graphics"),
                    nographics="-nographics" in p.get("argv", []),
                    timed_out=p.get("timed_out"),
                )
            )
    proof["native_jobs"] = jobs
    (root / "verified.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf8")
    assert proof["source_unchanged"] and proof["directory_unchanged"]
    assert len(jobs) == (2 if source_kind == "keyword" else 3)
    assert all(
        j["status"] == "succeeded"
        and j["returncode"] == 0
        and j["graphics"] is False
        and j["nographics"]
        and j["timed_out"] is False
        for j in jobs
    )
