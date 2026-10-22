"""Q06 optional public ASCII references; original bytes and derived curves stay external."""
import csv
import hashlib
import json
import os
import re
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


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def reference(source, kind):
    """Independent raw-token check of every written x-force, without production parsing."""
    values = {}
    with source.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            fields = line.split()
            if kind == "rcforc":
                if not fields or fields[0].lower() not in ("slave", "master", "surfa", "surfb"):
                    continue
                assert fields[2] == "time" and fields[4] == "x"
                side = int(fields[0].lower() in ("master", "surfb"))
                key = (float(fields[3]), int(fields[1]), side)
                value = float(fields[5])
            else:
                if len(fields) != 6 or not re.fullmatch(r"\d+", fields[0]):
                    continue
                key, value = (float(fields[1]), int(fields[0])), float(fields[2])
            assert key not in values
            values[key] = value
    return values


@pytest.mark.parametrize("corpus_id,kind,states,columns", CASES)
def test_public_force_rows_match_original_tokens_and_preserve_inputs(tmp_path, corpus_id, kind, states, columns):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR for registered public force files")
    root = Path(location)
    source = plain_path(resolve(entries(load_registry())[corpus_id], root) / kind)
    assert source.is_file(), f"Registered corpus lacks {kind}"
    before, listing = digest(source), sorted(p.name for p in source.parent.iterdir())
    expected = reference(source, kind)
    result = JobResult.model_validate_json(json.dumps(Service(Settings(tmp_path, allowed_roots=(root,)))
        .extract_database(str(source), kind, "x_force", "model_force"), allow_nan=False))
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
        actual[key] = float(row["x_force"])
    assert actual == expected
    assert digest(source) == before
    assert sorted(p.name for p in source.parent.iterdir()) == listing


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
