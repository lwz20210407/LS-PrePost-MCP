"""Q06 optional public ASCII references; original bytes and derived curves stay external."""
import csv
import hashlib
import json
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import entries, load_registry, plain_path, resolve

CASES = [
    ("result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit", "rcforc", 1001, 2),
    ("result.lsdyna-ansys-com__lspp-mini-tutorials.rcforc", "rcforc", 121, 2),
    ("result.node997__dyna_pladebuk.Plade_300_150_4.BB", "rcforc", 1, 8),
    ("result.praveenvenky110395__LS-DYNA-Crimping-Simulation.results", "rcforc", 651, 10),
    ("result.pranavduraisamy__helmet-fit-bayes-opt.bo-runs.run0.pendulum", "secforc", 250, 1),
]
COMPONENTS = {
    "rcforc": {"x_force": "x", "y_force": "y", "z_force": "z", "mass": "mass",
               "x_moment": "mx", "y_moment": "my", "z_moment": "mz"},
    "secforc": ["x_force", "y_force", "z_force", "force_magnitude", "x_moment", "y_moment",
                "z_moment", "moment_magnitude", "x_centroid", "y_centroid", "z_centroid", "area"],
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@lru_cache(maxsize=1)
def capture_identity():
    root = Path(__file__).resolve().parents[1]
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=root)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    products = ["src/ls_prepost_mcp/domain/results/ascii_forces.py", "src/ls_prepost_mcp/results_target_tools.py"]
    return dict(actual_git_revision=revision, working_tree_dirty=False,
        product_source_identity=[dict(path=p, git_blob_id=subprocess.check_output(
            ["git", "rev-parse", revision+":"+p], cwd=root, text=True).strip()) for p in products],
        test_source_identity=dict(path="tests/test_ascii_force_corpus.py", git_blob_id=subprocess.check_output(
            ["git", "rev-parse", revision+":tests/test_ascii_force_corpus.py"], cwd=root, text=True).strip()))


def record_capture(corpus_id, kind, component, source_sha256, result, available, samples):
    location = os.environ.get("LSPP_FORCE_EVIDENCE_DIR")
    if not location:
        return
    out = Path(location).resolve()
    assert not out.is_relative_to(Path(__file__).resolve().parents[1])
    out.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((corpus_id+kind+component).encode()).hexdigest()[:16]
    proof = dict(**capture_identity(), corpus_id=corpus_id, database=kind, component=component,
        source_sha256=source_sha256, component_stored=available, status=result.status,
        samples_checked=samples, input_bytes_and_listing_unchanged=True,
        independent_raw_columns_equal=available, artifact_sha256=[a.sha256 for a in result.artifacts])
    with (out / (key+".json")).open("x", encoding="utf8", newline="\n") as stream:
        json.dump(proof, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")


def reference(source, kind, component):
    """Independent raw-column check; no production field list, parser or math."""
    values = {}
    missing, legend, lines = False, False, []
    with source.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if "{BEGIN LEGEND}" in line:
                legend = True
            elif "{END LEGEND}" in line:
                legend = False
            elif not legend and line.strip():
                lines.append(line.strip())
        for i, line in enumerate(lines):
            fields = line.split()
            if kind == "rcforc":
                if not fields or fields[0].lower() not in ("slave", "master", "surfa", "surfb"):
                    continue
                assert fields[2] == "time"
                side = int(fields[0].lower() in ("master", "surfb"))
                key = (float(fields[3]), int(fields[1]), side)
                pairs = dict(zip(fields[4::2], fields[5::2]))
                token = pairs.get(COMPONENTS[kind][component])
                if token is None:
                    missing = True
                    continue
                value = float(token.replace("D", "E").replace("d", "e"))
            else:
                if len(fields) != 6 or not re.fullmatch(r"\d+", fields[0]):
                    continue
                force = fields[2:]
                moment = lines[i+1].split("=", 1)[-1].split()
                if "=" in lines[i+1]:
                    moment = moment[1:]  # written ac-reference ID, not a moment column
                centroid = lines[i+2].split()
                assert len(force) == len(moment) == len(centroid) == 4
                token = (force + moment + centroid)[COMPONENTS[kind].index(component)]
                key, value = (float(fields[1]), int(fields[0])), float(token.replace("D", "E").replace("d", "e"))
            assert key not in values
            values[key] = value
    return None if missing else values


@pytest.mark.parametrize("corpus_id,kind,states,columns,component",
    [(*case, component) for case in CASES for component in COMPONENTS[case[1]]])
def test_public_force_rows_match_original_tokens_and_preserve_inputs(tmp_path, corpus_id, kind, states, columns, component):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR for registered public force files")
    root = Path(location)
    source = plain_path(resolve(entries(load_registry())[corpus_id], root) / kind)
    assert source.is_file(), f"Registered corpus lacks {kind}"
    before, listing = digest(source), sorted(p.name for p in source.parent.iterdir())
    expected = reference(source, kind, component)
    result = JobResult.model_validate_json(json.dumps(Service(Settings(tmp_path, allowed_roots=(root,)))
        .extract_database(str(source), kind, component, "declared_component_units"), allow_nan=False))
    assert digest(source) == before and sorted(p.name for p in source.parent.iterdir()) == listing
    if expected is None:
        assert result.status == "failed" and not result.artifacts
        record_capture(corpus_id, kind, component, before, result, False, 0)
        return
    assert result.status == "succeeded", result.error
    assert result.backend == "ls-dyna-ascii"
    assert result.data["state_count"] == states and result.data["entity_count"] == columns
    assert result.data["row_count"] == len(expected) == states * columns
    with open(result.artifacts[0].path, newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    actual = {}
    for row in rows:
        key = (float(row["time"]), int(row["entity_id"]))
        if kind == "rcforc":
            key += (int(row["side"]),)
        assert key not in actual
        actual[key] = float(row[component])
    assert actual == expected
    assert digest(source) == before
    assert sorted(p.name for p in source.parent.iterdir()) == listing
    record_capture(corpus_id, kind, component, before, result, True, len(expected))


def test_public_empty_secforc_is_failed_instead_of_a_zero_curve(tmp_path):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR for the public header-only secforc")
    root = Path(location)
    source = plain_path(resolve(entries(load_registry())[CASES[0][0]], root) / "secforc")
    before = digest(source)
    result = Service(Settings(tmp_path, allowed_roots=(root,))).extract_database(
        str(source), "secforc", "x_force", "model_force")
    assert result["status"] == "failed" and result["backend"] == "ls-dyna-ascii"
    assert not result["artifacts"] and digest(source) == before
