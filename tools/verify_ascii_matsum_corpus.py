"""Independent literal-field Q06 public MATSUM check; no native process or source copies.

Usage: python tools/verify_ascii_matsum_corpus.py --corpus ROOT --output EXTERNAL_REPORT_DIR
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import entries, load_registry, plain_path, read_catalogs, resolve
from tools.public_corpus_preflight import directory_snapshot

CASES = [
    ("result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit", 1001, 7),
    ("result.praveenvenky110395__LS-DYNA-Crimping-Simulation.results", 131, 22),
    ("result.node997__dyna_pladebuk.Plade_300_150_4.BB", 1, 3),
]
# An independent literal-field reference, not imported from the product mapping.
FIELDS = {"inten": "internal_energy", "kinen": "kinetic_energy", "hgeng": "hourglass_energy",
          "eroded_ie": "eroded_internal_energy", "eroded_ke": "eroded_kinetic_energy"}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def literal_reference(source):
    """Tokenize the registered assignment layout independently, preserving ID/time order."""
    times, identifiers, data = [], [], {}
    time = pid = None
    legend = False
    with source.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if "{BEGIN LEGEND}" in line:
                legend = True
            if "{END LEGEND}" in line:
                legend = False
                continue
            if legend:
                continue
            tokens = line.replace("=", " = ").split()
            for index, token in enumerate(tokens):
                if token != "=" or index == 0 or index + 1 == len(tokens):
                    continue
                name, written = tokens[index - 1], tokens[index + 1]
                if name == "time":
                    time = float(written.replace("D", "E"))
                    times.append(time)
                    pid = None
                elif name == "mat.#":
                    pid = int(written)
                    if pid not in identifiers:
                        identifiers.append(pid)
                elif name in FIELDS:
                    key = (time, pid, FIELDS[name])
                    if key in data:
                        raise ValueError("Duplicate literal reference key")
                    data[key] = float(written.replace("D", "E"))
    return times, identifiers, data


def verify_case(corpus, output, case):
    corpus_id, sample_count, part_count = case
    registry = load_registry()
    source = plain_path(resolve(entries(registry)[corpus_id], corpus) / "matsum")
    digest = sha(source)
    catalog, _ = read_catalogs(registry, corpus)
    assert digest == catalog[source.relative_to(corpus).as_posix()]["sha256"]
    listing = directory_snapshot([source])
    times, identifiers, reference = literal_reference(source)
    assert len(times) == sample_count and len(identifiers) == part_count
    service = Service(Settings(output / "work", allowed_roots=(corpus, output)))
    curves = []
    for component in FIELDS.values():
        result = service.extract_database(str(source), "matsum", component, "source_energy",
                                          time_units="source_time")
        assert result["status"] == "succeeded", result["error"]
        assert result["data"]["ids"] == identifiers
        assert result["data"]["stored_columns"] == list(range(part_count))
        assert result["data"]["source_sha256"] == digest
        artifact = result["artifacts"][0]
        csv_path = Path(artifact["path"])
        assert sha(csv_path) == artifact["sha256"]
        with csv_path.open(newline="", encoding="utf8") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == ["time", "entity_id", component]
            written = [(float(r["time"]), int(r["entity_id"]), float(r[component])) for r in reader]
        expected = [(time, pid, reference[time, pid, component]) for time in times for pid in identifiers]
        assert written == expected
        curves.append(dict(component=component, samples=sample_count, parts=part_count,
                           compared_values=len(expected), exact=True))
    assert sha(source) == digest and directory_snapshot([source]) == listing
    return dict(corpus_id=corpus_id, member="matsum", sha256=digest, size_bytes=source.stat().st_size,
                source_unchanged=True, source_directory_unchanged=True, curves=curves)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus, output = plain_path(args.corpus), args.output.resolve()
    if output.exists():
        parser.error("--output must name a fresh directory")
    output.mkdir(parents=True)
    report = dict(cases=[verify_case(corpus, output / str(i), case) for i, case in enumerate(CASES)],
                  native_executed=False, scope="Literal assignments only; not native evidence")
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps(dict(cases=len(report["cases"]),
                         compared_values=sum(c["compared_values"] for p in report["cases"] for c in p["curves"]),
                         exact=True, source_unchanged=True)))


if __name__ == "__main__":
    main()
