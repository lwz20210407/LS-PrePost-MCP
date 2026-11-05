"""Independent literal-token reference for registered ASCII NODOUT translations."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import entries, load_registry, plain_path, read_catalogs, resolve
from tools.public_corpus_preflight import directory_snapshot

CASES = [
    ("result.ansyshelp-ansys-com__doc-assets.4_2_Post_Plot_curve", 121, 1),
    ("result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit", 1001, 2),
    ("result.pranavduraisamy__helmet-fit-bayes-opt.bo-runs.run0.drop", 251, 1),
    ("result.pranavduraisamy__helmet-fit-bayes-opt.bo-runs.run0.pendulum", 251, 1),
    ("result.zenodo__18598355.FEMU_Taylor.03_mat_CS_artificial", 669, 21),
    ("result.zenodo__18598355.FEMU_Taylor.21_mat_JC_real", 429, 21),
]
# Independent token scanning, not the production fixed-width slicer or its mapping.
COMPONENTS = [f"{axis}_{quantity}" for quantity in ["displacement", "velocity", "acceleration"] for axis in "xyz"]
NUMERIC = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def literal_reference(path):
    times, ids, values = [], [], {}
    current_time, active, legend = None, False, False
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if "{BEGIN LEGEND}" in line:
                legend = True
            if "{END LEGEND}" in line:
                legend = False
                continue
            if legend:
                continue
            match = re.search(r"\(\s*at time\s+(\S+)\s*\)", line)
            if match:
                current_time, active = float(match[1].replace("D", "E")), False
                continue
            if line.lstrip().startswith("nodal point"):
                active = "x-disp" in line
                if active:
                    times.append(current_time)
                continue
            if not active or not line.strip():
                continue
            matches = list(NUMERIC.finditer(line))
            if not matches:
                continue
            assert len(matches) == 13
            position = 0
            for token in matches:
                assert not line[position:token.start()].strip()
                position = token.end()
            assert not line[position:].strip()
            assert matches[0][0].isdigit()
            node = int(matches[0][0])
            if node not in ids:
                ids.append(node)
            key = current_time, node
            assert key not in values
            values[key] = [float(token[0].replace("D", "E")) for token in matches[1:10]]
    return times, ids, values


def verify_case(corpus, output, case):
    corpus_id, frames, nodes = case
    registry = load_registry()
    source = plain_path(resolve(entries(registry)[corpus_id], corpus) / "nodout")
    before, listing = sha(source), directory_snapshot([source])
    catalog, _ = read_catalogs(registry, corpus)
    assert before == catalog[source.relative_to(corpus).as_posix()]["sha256"]
    times, ids, expected = literal_reference(source)
    assert len(times) == frames and len(ids) == nodes
    service = Service(Settings(output / "work", allowed_roots=(corpus, output)))
    curves = []
    for index, component in enumerate(COMPONENTS):
        result = service.extract_database(str(source), "nodout", component, "declared_source_quantity",
                                          time_units="declared_source_time")
        assert result["status"] == "succeeded", result["error"]
        data = result["data"]
        assert result["backend"] == "ls-dyna-ascii" and data["source_kind"] == "ascii"
        assert data["ids"] == ids and data["stored_columns"] == list(range(nodes))
        assert data["entity_metadata"]["deletion_validity"] == "unknown"
        assert not data["entity_metadata"]["alive_mask_available"] and data["source_sha256"] == before
        artifact = result["artifacts"][0]
        csv_path = Path(artifact["path"])
        assert sha(csv_path) == artifact["sha256"]
        with csv_path.open(newline="", encoding="utf8") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == ["time", "entity_id", component]
            actual = [(float(r["time"]), int(r["entity_id"]), float(r[component])) for r in reader]
        wanted = [(time, node, expected[time, node][index]) for time in times for node in ids]
        assert actual == wanted
        curves.append(dict(component=component, frames=frames, nodes=nodes, compared_values=len(actual), exact=True))
    assert sha(source) == before and directory_snapshot([source]) == listing
    return dict(corpus_id=corpus_id, member="nodout", sha256=before, size_bytes=source.stat().st_size,
                source_unchanged=True, source_directory_unchanged=True, stored_ids=ids, curves=curves,
                deletion_validity="unknown", native_executed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus, output = plain_path(args.corpus), args.output.resolve()
    if output.exists():
        parser.error("--output must be fresh")
    output.mkdir(parents=True)
    cases = []
    for index, case in enumerate(CASES):
        cases.append(verify_case(corpus, output / str(index), case))
        print(case[0], "verified", flush=True)
    report = dict(cases=cases, native_executed=False, scope="Literal source-token comparison; no native L2")
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf8")
    print(json.dumps(dict(cases=len(cases), compared_values=sum(c["compared_values"] for p in cases for c in p["curves"]))))


if __name__ == "__main__":
    main()
