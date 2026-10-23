"""Q05: fixed public erosion example, no copied result family or native run."""
import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import entries, load_registry, plain_path, resolve


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def test_real_projectile_deleted_samples_are_explicit_in_each_export(tmp_path):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR for the registered public projectile result")
    pytest.importorskip("lasso.dyna")
    from ls_prepost_mcp.domain.model.includes import is_network

    root = plain_path(Path(location))
    if is_network(str(root)):
        pytest.fail("The public erosion regression does not access network roots")
    corpus_id = "result.ansys__example-data.result_files.d3plot_projectile"
    entry = entries(load_registry())[corpus_id]
    assert entry["path"].startswith("public-results/")
    directory = plain_path(resolve(entry, root))
    service = Service(Settings(tmp_path / "work", allowed_roots=(root / "public-results",)))
    source = service.settings.input_path(str(directory / "d3plot"))
    family = service._result_family(str(source))
    before = {p.name: sha(p) for p in family}
    summaries = []
    for quantity in ["effective_plastic_strain", "von_mises", "sxx"]:
        result = service.extract_history(str(source), "solid", quantity, [1], units="as_stored", time_units="as_stored")
        assert result["status"] == "succeeded", result.get("error")
        artifact = result["artifacts"][0]
        with Path(artifact["path"]).open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        # The frozen example erodes solid user ID 1 at state 3. These expected
        # states are independent of the production reader's alive-array loop.
        assert [r.get("alive") for r in rows] == ["1", "1"] + ["0"] * (len(rows) - 2)
        assert artifact["metadata"]["deleted_from_state"] == 3
        assert artifact["metadata"]["deletion_status"] == "stored" and result["warnings"]
        assert all(float(r["value"]) == 0. for r in rows[2:])
        if quantity == "effective_plastic_strain":
            assert .52 < float(rows[1]["value"]) < .54
        summaries.append({"quantity": quantity, "samples": len(rows), "deleted_from_state": 3,
                          "alive_samples": 2, "deleted_samples": len(rows) - 2, "csv_sha256": artifact["sha256"]})
    assert before == {p.name: sha(p) for p in family}
    capture = os.environ.get("LSPP_HISTORY_EVIDENCE_DIR")
    if capture:
        repo = Path(__file__).resolve().parents[1]
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo)
        output = Path(capture).resolve()
        assert not output.is_relative_to(repo)
        output.mkdir(parents=True, exist_ok=True)
        products = ["src/ls_prepost_mcp/domain/results/lasso_backend.py", "src/ls_prepost_mcp/history_tools.py",
                    "src/ls_prepost_mcp/post_backend.py", "src/ls_prepost_mcp/core/contracts.py"]
        proof = {"corpus_id": corpus_id, "actual_git_revision": revision, "working_tree_dirty": False,
            "native_run": False, "source_sha256": before, "source_family_unchanged": True,
            "element_id": 1, "curves": summaries, "product_source_identity": [
                {"path": p, "git_blob_id": subprocess.check_output(["git", "rev-parse", revision + ":" + p],
                    cwd=repo, text=True).strip()} for p in products]}
        with (output / "projectile.json").open("x", encoding="utf-8") as stream:
            json.dump(proof, stream, separators=(",", ":"))
            stream.write("\n")
