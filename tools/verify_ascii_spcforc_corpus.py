"""Independent SPCFORC Decimal/token oracle for two registered local-only sources.

No downloads, native execution, result mathematics, or redistribution. Parser
mode is a reader check; Service mode additionally checks the public CSV product.
Reports record the actual Git head and dirty state and are private local output.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from decimal import Decimal
from pathlib import Path

from tools.fetch_corpus import entries, load_registry, plain_path, resolve
from tools.public_corpus_preflight import directory_snapshot

CASES = [("result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit", 1000, 45, True),
         ("result.node997__dyna_pladebuk.Plade_300_150_4.BB", 2, 32, False)]
# This oracle deliberately does not import production patterns, mappings or helpers.
FIELDS = {"x_force": ("forces", 0), "y_force": ("forces", 1), "z_force": ("forces", 2),
          "x_moment": ("moments", 0), "y_moment": ("moments", 1), "z_moment": ("moments", 2)}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def literal_reference(path):
    """Scan original tokens independently; vectors keyed by frame/node/kind, never setid-as-CSID."""
    frames, current, ids, references = [], None, [], {}

    def scalar(token):
        exact = Decimal(token.replace("D", "E").replace("d", "e"))
        value = float(exact)
        assert exact.is_finite() and math.isfinite(value)
        assert value != 0 or exact == 0, "reference scalar underflows float64"
        return value

    def finish():
        if current is None:
            return
        assert current["summary"] and current["forces"]
        nodes = list(current["forces"])
        if not ids:
            ids.extend(nodes)
        assert set(nodes) == set(ids)
        assert not current["moments"] or set(current["moments"]) == set(ids)
        if frames:
            assert current["time"] > frames[-1]["time"]
            assert bool(current["moments"]) == bool(frames[-1]["moments"])
        frames.append(current)

    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            words = line.replace("=", " = ").replace(",", " , ").split()
            if not words:
                continue
            if words[:3] == ["output", "at", "time"]:
                assert len(words) == 5 and words[3] == "="
                finish()
                current = dict(time=scalar(words[4]), forces={}, moments={}, summary=False)
            elif words[0] == "node":
                assert current is not None and not current["summary"]
                assert len(words) == 17 and words[1] == "="
                assert words[3:9] == ["local", "x", ",", "y", ",", "z"]
                assert words[9] in ("forces", "moments") and words[10] == "="
                assert words[14:16] == ["setid", "="]
                assert words[2].isascii() and words[2].isdigit() and int(words[2]) > 0
                assert words[16].isascii() and words[16].isdigit()
                node, setid, kind = int(words[2]), int(words[16]), words[9]
                assert node not in references or references[node] == setid
                references[node] = setid
                assert node not in current[kind]
                current[kind][node] = [scalar(word) for word in words[11:14]]
            elif words[:2] == ["force", "resultants"]:
                assert current is not None and current["forces"] and not current["summary"]
                assert len(words) == 6 and words[2] == "="
                [scalar(word) for word in words[3:]]
                current["summary"] = True
            else:
                assert current is None, "unrecognized reference record inside a frame"
    finish()
    assert frames
    return dict(times=[frame["time"] for frame in frames], ids=ids, frames=frames,
                setid=[references[node] for node in ids], moments=bool(frames[0]["moments"]))


def git_identity():
    root = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1", "--untracked-files=all"],
                                     cwd=root, text=True).splitlines()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
    sources = ["src/ls_prepost_mcp/domain/results/ascii_spcforc.py",
               "src/ls_prepost_mcp/domain/results/ascii_records.py",
               "src/ls_prepost_mcp/results_target_tools.py", "tools/verify_ascii_spcforc_corpus.py"]
    return dict(head=head, tree=tree, dirty=bool(status), status=status,
                source_sha256={relative: sha(root / relative) for relative in sources})


def source_stat(path):
    info = path.stat()
    return dict(size=info.st_size, mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns,
                device=info.st_dev, inode=info.st_ino)


def verify_case(corpus, output, case, *, reader_mode):
    corpus_id, frames, nodes, has_moments = case
    registry = load_registry()
    source = plain_path(resolve(entries(registry)[corpus_id], corpus) / "spcforc")
    before, listing, stat_before = sha(source), directory_snapshot([source]), source_stat(source)
    catalog = json.loads((corpus / "public-results/manifest.json").read_text(encoding="utf8"))
    relative_set = source.parent.relative_to(corpus / "public-results").as_posix()
    source_set = next(item for item in catalog["result_sets"] if item["path"] == relative_set)
    member = next(item for item in source_set["files"] if item["name"] == "spcforc")
    assert before == member["sha256"] and stat_before["size"] == member["size"]
    reference = literal_reference(source)
    assert len(reference["times"]) == frames and len(reference["ids"]) == nodes
    assert reference["moments"] is has_moments
    curves, unavailable = [], []
    if reader_mode == "service":
        from ls_prepost_mcp.config import Settings
        from ls_prepost_mcp.service import Service

        service = Service(Settings(output / "work", allowed_roots=(corpus, output)))
    for component, (kind, column) in FIELDS.items():
        missing = kind == "moments" and not has_moments
        if reader_mode == "parser":
            from ls_prepost_mcp.domain.results import ascii_spcforc
            from ls_prepost_mcp.domain.results.lasso_backend import ResultsError

            try:
                data = ascii_spcforc.read(source, component)
            except ResultsError as error:
                assert missing and "not stored; missing values are unknown" in str(error)
                unavailable.append(component)
                continue
            assert not missing
            actual = [(time, node, data["values"][i][j])
                      for i, time in enumerate(data["time"]) for j, node in enumerate(data["ids"])]
        else:
            result = service.extract_database(str(source), "spcforc", component, "declared_source_quantity",
                                              time_units="declared_source_time")
            if missing:
                assert result["status"] == "failed" and not result["artifacts"]
                assert "not stored; missing values are unknown" in result["error"]["message"]
                unavailable.append(component)
                continue
            assert result["status"] == "succeeded", result["error"]
            data = result["data"]
            assert result["backend"] == "ls-dyna-ascii" and data["source_sha256"] == before
            assert data["stored_columns"] == list(range(nodes))
            assert data["state_count"] == frames and data["row_count"] == frames*nodes
            artifact = result["artifacts"][0]
            csv_path = Path(artifact["path"])
            assert artifact["sha256"] == sha(csv_path)
            with csv_path.open(newline="", encoding="utf8") as stream:
                csv_reader = csv.DictReader(stream)
                assert csv_reader.fieldnames == ["time", "entity_id", component]
                actual = [(float(row["time"]), int(row["entity_id"]), float(row[component])) for row in csv_reader]
        assert data["ids"] == reference["ids"] and data["source_kind"] == "ascii"
        assert data["source_format"] == "spcforc"
        meta = data["entity_metadata"]
        assert meta["setid"] == reference["setid"] and "coordinate_system_ids" not in meta
        assert meta["frame"] == "local as printed; basis unidentified; no transform"
        assert meta["record_kind"] == kind and meta["component_index"] == column
        assert not meta["alive_mask_available"] and meta["deletion_validity"] == "unknown"
        assert meta["summary_records_validated"] == frames and not meta["summary_exported"]
        expected = [(frame["time"], node, frame[kind][node][column])
                    for frame in reference["frames"] for node in reference["ids"]]
        assert actual == expected
        curves.append(dict(component=component, frames=frames, nodes=nodes, compared_values=len(actual), exact=True,
                           zero_values=sum(value == 0 for _, _, value in expected),
                           nonzero_values=sum(value != 0 for _, _, value in expected)))
    assert unavailable == ([] if has_moments else ["x_moment", "y_moment", "z_moment"])
    after, stat_after = sha(source), source_stat(source)
    assert after == before and stat_after == stat_before and directory_snapshot([source]) == listing
    namespace = json.dumps(list(listing.values()), ensure_ascii=True, separators=(",", ":"))
    return dict(corpus_id=corpus_id, member="spcforc", sha256=before, size_bytes=source.stat().st_size,
                source_sha256_after=after, source_stat_before=stat_before, source_stat_after=stat_after,
                source_namespace_sha256=hashlib.sha256(namespace.encode()).hexdigest(),
                source_namespace_entries=sum(len(names) for names in listing.values()),
                source_unchanged=True, source_directory_unchanged=True, curves=curves,
                unavailable_components_rejected=unavailable, reader_mode=reader_mode, native_executed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reader", choices=("parser", "service"), required=True)
    parser.add_argument("--expect-head", required=True)
    parser.add_argument("--lease", required=True, help="Explicit run scope/authorization label, recorded verbatim")
    args = parser.parse_args()
    corpus, output = plain_path(args.corpus).resolve(), args.output.resolve()
    if output.exists() or output.is_relative_to(corpus):
        parser.error("--output must be fresh and outside the read-only corpus")
    before = git_identity()
    if before["dirty"] or before["head"] != args.expect_head:
        parser.error("verification requires the exact expected clean Git head")
    catalog_path = corpus / "public-results/manifest.json"
    catalog_before = dict(sha256=sha(catalog_path), stat=source_stat(catalog_path))
    output.mkdir(parents=True)
    cases = []
    for index, case in enumerate(CASES):
        cases.append(verify_case(corpus, output / str(index), case, reader_mode=args.reader))
        print(case[0], "verified", flush=True)
    after = git_identity()
    assert before == after, "repository identity changed during verification"
    catalog_after = dict(sha256=sha(catalog_path), stat=source_stat(catalog_path))
    assert catalog_before == catalog_after, "source manifest changed during verification"
    report = dict(cases=cases, repository_before=before, repository_after=after, lease=args.lease,
                  catalog_before=catalog_before, catalog_after=catalog_after, native_executed=False,
                  scope="Literal source-token comparison; no native L2; parser mode is not public Service evidence")
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf8")
    print(json.dumps(dict(cases=len(cases), reader=args.reader,
                         compared_values=sum(curve["compared_values"] for item in cases for curve in item["curves"]))))


if __name__ == "__main__":
    main()
