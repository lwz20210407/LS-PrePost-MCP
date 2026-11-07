"""Independent literal SLEOUT comparison; existing public files only, no native jobs.

Usage: python tools/verify_ascii_sleout_corpus.py --corpus ROOT --output EXTERNAL_DIR
Raw sources and exported CSVs stay outside Git; report.json contains counts and hashes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import entries, load_registry, plain_path, resolve
from tools.public_corpus_preflight import directory_snapshot

CASES = [("result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit", 1001, 3),
         ("result.praveenvenky110395__LS-DYNA-Crimping-Simulation.results", 261, 7)]
COMPONENTS = ("side_a_energy", "side_b_energy", "frictional_energy")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def literal_reference(source):
    """Scan these registered layouts independently; never import the product parser."""
    frames, labels, legend, current = [], [], False, None
    with source.open(encoding="utf-8-sig") as stream:
        for line in stream:
            text, fields = line.strip(), line.split()
            if text == "{BEGIN LEGEND}":
                legend = True
            elif text == "{END LEGEND}":
                legend = False
            elif not legend and fields:
                if text.startswith("contact interface energy file, time="):
                    time = float(text.split("=", 1)[1].replace("D", "E"))
                    assert math.isfinite(time)
                    current = dict(time=time, rows={}, summaries=0)
                    frames.append(current)
                elif fields[0] == "#":
                    assert current is not None and fields[3] == "cycle=" and len(fields) == 6
                    written = (fields[1], fields[2], fields[5])
                    assert written in (("slave", "master", "frictional"), ("surfa", "surfb", "frictional"))
                    if written not in labels:
                        labels.append(written)
                elif current is not None and fields[0].isdigit():
                    assert len(fields) == 4
                    identity = int(fields[0])
                    assert identity > 0 and identity not in current["rows"]
                    numbers = [float(token.replace("D", "E")) for token in fields[1:]]
                    assert all(math.isfinite(value) for value in numbers)
                    current["rows"][identity] = numbers
                elif current is not None and "=" in text:
                    assert text.startswith(("summary", "total ", "friction energy"))
                    assert math.isfinite(float(text.split("=", 1)[1].replace("D", "E")))
                    current["summaries"] += 1
    assert not legend and frames
    identifiers = list(frames[0]["rows"])
    times = [frame["time"] for frame in frames]
    assert all(b > a for a, b in zip(times, times[1:]))
    assert all(set(frame["rows"]) == set(identifiers) and frame["summaries"] == 4 for frame in frames)
    return times, identifiers, frames, labels


def verify_case(corpus, output, case):
    corpus_id, frame_count, interface_count = case
    source = plain_path(resolve(entries(load_registry())[corpus_id], corpus) / "sleout")
    catalog_path = corpus / "public-results" / "manifest.json"
    catalog_sha = sha(catalog_path)
    catalog = json.loads(catalog_path.read_text(encoding="utf8"))
    relative = source.parent.relative_to(corpus / "public-results").as_posix()
    registered = [record for record in catalog["result_sets"] if record["path"] == relative]
    assert len(registered) == 1
    members = [member for member in registered[0]["files"] if member["name"] == "sleout"]
    assert len(members) == 1
    digest, stat = sha(source), source.stat()
    assert digest == members[0]["sha256"] and stat.st_size == members[0]["size"]
    listing = directory_snapshot([source])
    times, identifiers, frames, labels = literal_reference(source)
    assert len(times) == frame_count and len(identifiers) == interface_count
    service = Service(Settings(output / "work", allowed_roots=(corpus, output)))
    curves = []
    for column, component in enumerate(COMPONENTS):
        result = service.extract_database(str(source), "sleout", component, "source_energy",
                                          time_units="source_time")
        assert result["status"] == "succeeded", result["error"]
        data = result["data"]
        assert data["ids"] == identifiers and data["stored_columns"] == list(range(interface_count))
        assert data["source_kind"] == "ascii" and data["source_format"] == "sleout"
        assert data["source_column_names"]["value"] == [layout[column] for layout in labels]
        assert data["source_sha256"] == digest
        assert data["entity_metadata"]["validity"] == "raw_unmasked"
        assert data["entity_metadata"]["deletion_validity"] == "unknown"
        assert data["entity_metadata"]["summary_exported"] is False
        artifact = result["artifacts"][0]
        csv_path = Path(artifact["path"])
        assert sha(csv_path) == artifact["sha256"]
        with csv_path.open(newline="", encoding="utf8") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == ["time", "entity_id", component]
            written = [(float(r["time"]), int(r["entity_id"]), float(r[component])) for r in reader]
        expected = [(frame["time"], identity, frame["rows"][identity][column])
                    for frame in frames for identity in identifiers]
        assert written == expected
        curves.append(dict(component=component, frames=frame_count, interfaces=interface_count,
                           compared_values=len(expected), nonzero_values=sum(row[2] != 0 for row in expected),
                           exact=True))
    after = source.stat()
    assert (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev) == (
        after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino, after.st_dev)
    assert sha(source) == digest and directory_snapshot([source]) == listing
    assert sha(catalog_path) == catalog_sha
    return dict(corpus_id=corpus_id, member="sleout", sha256=digest, size_bytes=stat.st_size,
                catalog_sha256=catalog_sha, source_unchanged=True, source_stat_unchanged=True,
                source_directory_unchanged=True, source_labels=labels, curves=curves)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus, output = plain_path(args.corpus.resolve()), args.output.resolve()
    if output.exists():
        parser.error("--output must name a fresh directory")
    if output.is_relative_to(corpus):
        parser.error("--output must stay outside the read-only corpus")
    output.mkdir(parents=True)
    report = dict(cases=[verify_case(corpus, output / str(index), case) for index, case in enumerate(CASES)],
                  native_executed=False, scope="Literal stored SLEOUT energies only; L1, not native evidence")
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps(dict(cases=len(report["cases"]),
                         compared_values=sum(c["compared_values"] for p in report["cases"] for c in p["curves"]),
                         exact=True, source_unchanged=True, native_executed=False)))


if __name__ == "__main__":
    main()
