"""Bounded I04 diagnostics; raw reports stay outside Git and never certify acceptance.

Uses the registered corpus and existing preflight/Service/readers. Native execution
requires --run-native plus an explicitly scheduled headless window.
"""

import argparse
import importlib.metadata
import json
import os
import re
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain.results.lasso_backend import overview
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service
from tools.fetch_corpus import digest, entries, io_root, load_registry, plain_path, read_catalogs, resolve
from tools.native_regression import execution_identity
from tools.public_corpus_preflight import directory_snapshot, input_classification, input_tree

ROOT = Path(__file__).resolve().parents[1]
CASE_IDS = ("extra-keyword-064", "extra-result-03")


def state_comparison(native, reader):
    """Retain every state and its 1-based position, including suspicious times."""
    left, right = native["state_times"], reader["state_times"]
    result = dict(native_count=native["counts"]["states"], reader_count=reader["state_count"],
                  native_times=left, reader_times=right)
    if len(left) != result["native_count"] or len(right) != result["reader_count"]:
        result["verdict"] = "incomplete_time_arrays"
    elif result["native_count"] != result["reader_count"]:
        result["verdict"] = "backend_state_count_mismatch"
    elif left != right:
        result["verdict"] = "backend_time_array_mismatch"
    else:
        result["verdict"] = "identical_state_metadata_only"
    result["reader_time_reversals"] = [i + 1 for i in range(1, len(right)) if right[i] < right[i - 1]]
    return result


def resolve_case(case_id, root):
    cases = json.loads((ROOT / "tests/corpus/public_cases.json").read_text(encoding="utf8"))["cases"]
    case = next(c for c in cases if c["id"] == case_id)
    registry = load_registry()
    catalog, manifests = read_catalogs(registry, root)
    base = resolve(entries(registry)[case["corpus"]], root)
    source = plain_path((base / case["member"] if case["member"] else base).resolve(strict=True))
    if not source.is_relative_to(plain_path(root)):
        raise ValueError("Corpus member escapes root")
    family = [source]
    if case["kind"] == "d3plot":
        family += sorted(p for p in source.parent.iterdir() if p.is_file()
                         and re.fullmatch(re.escape(source.name) + r"\d+", p.name))
    tree, identities = input_tree(source, family, keyword=case["kind"] == "keyword")
    for path, sha in identities.items():
        relative = plain_path(path).relative_to(plain_path(root)).as_posix()
        if sha != catalog[relative]["sha256"]:
            raise ValueError("Corpus differs from external manifest: " + relative)
    return case, source, tree, identities, manifests


def diagnose(service, source, kind, *, run_native):
    record = dict(status="offline_only", native_requested=run_native)
    if kind == "d3plot":
        record["metadata_reader"] = service.inspect_d3plot_database(str(source))
        full = overview(source)
        record["full_reader"] = {key: full[key] for key in ("backend", "states", "times")}
    if not run_native:
        return record
    native = service.inspect_model(str(source), kind)
    record["native_inventory"] = native
    if native["status"] != "succeeded":
        record["status"] = "native_inventory_failed"
        return record
    if kind == "d3plot":
        record["comparison"] = state_comparison(native["data"], record["metadata_reader"])
        record["status"] = record["comparison"]["verdict"]
    else:
        saved = service.export_keyword(str(source))
        record["save_keyword"] = saved
        record["status"] = "keyword_save_failed"
        if saved["status"] == "succeeded":
            output = next(a["path"] for a in saved["artifacts"] if a["kind"] == "keyword")
            reopened = service.inspect_model(output)
            record["reopen_inventory"] = reopened
            record["status"] = "keyword_reopen_failed"
            if reopened["status"] == "succeeded":
                same = native["data"]["counts"] == reopened["data"]["counts"]
                record["status"] = "identical_counts_only" if same else "reopen_count_mismatch"
    return record


def preservation(identities, listing):
    result = dict(originals_unchanged=None, directory_listing_unchanged=None)
    if identities:
        try:
            result["originals_unchanged"] = all(digest(p) == sha for p, sha in identities.items())
            result["directory_listing_unchanged"] = directory_snapshot(identities) == listing
        except OSError as exc:
            result.update(originals_unchanged=False, preservation_error=str(exc))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=CASE_IDS)
    parser.add_argument("--corpus-root", type=Path, default=os.environ.get("LSPP_CORPUS_DIR"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-native", action="store_true")
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args(argv)
    if args.corpus_root is None:
        parser.error("Set --corpus-root or LSPP_CORPUS_DIR")
    if args.run_native and args.executable is None:
        parser.error("--run-native requires --executable and a scheduled headless window")
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or output.is_relative_to(args.corpus_root.resolve()):
        parser.error("Output must stay outside the repository and corpus")
    output.mkdir(parents=True, exist_ok=False)
    record = dict(case=args.case, scope="Diagnostic evidence, not acceptance", status="diagnostic_error",
                  execution_context=execution_identity(report_directory=output),
                  dependencies={p: importlib.metadata.version(p) for p in ("lasso-python", "numpy", "pydantic")})
    identities, listing = {}, None
    try:
        case, source, tree, identities, manifests = resolve_case(args.case, io_root(args.corpus_root))
        listing = directory_snapshot(identities)
        record.update(corpus=case["corpus"], input_tree=tree, external_manifests=manifests,
                      preflight=input_classification(tree))
        if record["preflight"] != "preflight_ok_requires_native_diagnosis":
            record["status"] = "input_limited"
        else:
            service = Service(Settings(output / "jobs", args.executable,
                                       (plain_path(args.corpus_root.resolve()), output), timeout=120))
            record.update(diagnose(service, source, case["kind"], run_native=args.run_native))
    except Exception as exc:
        record["error"] = dict(type=type(exc).__name__, message=str(exc))
        raise
    finally:
        record.update(preservation(identities, listing))
        if record["originals_unchanged"] is False or record["directory_listing_unchanged"] is False:
            record["status"] = "input_preservation_failed"
        atomic_json(output / "diagnostic.json", record)
    return 0 if record["status"] in ("offline_only", "identical_state_metadata_only", "identical_counts_only") else 1


if __name__ == "__main__":
    raise SystemExit(main())
