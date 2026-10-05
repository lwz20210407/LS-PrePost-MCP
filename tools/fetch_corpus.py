"""I11: read-only lookup/verification of the user's external corpus.

The historical CLI name is retained; this tool never downloads, copies,
generates, repairs or executes corpus contents.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests/corpus/manifest.yaml"
PUBLIC_GROUPS = ("catalogs", "keyword_sources", "result_sets", "regression_inputs")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def io_root(root):
    """Use extended Windows paths before resolving long descendants/symlinks."""
    absolute = str(root.resolve())
    if os.name == "nt" and not absolute.startswith("\\\\?\\"):
        absolute = "\\\\?\\UNC\\" + absolute[2:] if absolute.startswith("\\\\") else "\\\\?\\" + absolute
    return Path(absolute)


def destination(root, relative):
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or any(c in relative for c in ":\x00\r\n")
    ):
        raise ValueError("Corpus path must be a portable relative path")
    if (
        PureWindowsPath(relative).drive
        or PurePosixPath(relative).is_absolute()
        or any(p in (".", "..") for p in relative.split("/"))
    ):
        raise ValueError("Corpus member escapes destination")
    base = io_root(root)
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or path == base:
        raise ValueError("Corpus member escapes destination")
    return path


def load_registry(path=MANIFEST):
    registry = yaml.safe_load(path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 2 or registry.get("root_env") != "LSPP_CORPUS_DIR":
        raise ValueError("Expected reference-only corpus registry schema 2")
    seen = set()
    for group in (*PUBLIC_GROUPS, "private_corpora"):
        for entry in registry[group]:
            allowed = {"id"} if group == "private_corpora" else {"id", "path"}
            if set(entry) != allowed:
                raise ValueError(f"{group}: entries must contain only {sorted(allowed)}")
            name = entry["id"]
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in seen:
                raise ValueError("Invalid or duplicate corpus ID")
            seen.add(name)
            if "path" in entry:
                destination(ROOT, entry["path"])
    return registry


def entries(registry):
    return {e["id"]: e for group in (*PUBLIC_GROUPS, "private_corpora") for e in registry[group]}


def resolve(entry, root):
    if "path" not in entry:
        raise ValueError(f"{entry['id']}: private ID only; no private path is stored or inferred")
    path = destination(root, entry["path"])
    if not path.exists():
        raise FileNotFoundError(entry["path"])
    return path


def read_catalogs(registry, root):
    records, snapshots = {}, {}

    def add(relative, metadata, size_key):
        destination(root, relative)
        sha = metadata.get("sha256")
        size = metadata.get(size_key)
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("Missing/invalid external SHA256 for " + relative)
        if type(size) is not int or size < 0:
            raise ValueError("Missing/invalid external size for " + relative)
        record = dict(sha256=sha, size=size)
        if relative in records and records[relative] != record:
            raise ValueError("Conflicting external metadata for " + relative)
        records[relative] = record

    for entry in registry["catalogs"]:
        path = resolve(entry, root)
        raw = path.read_bytes()
        snapshots[entry["path"]] = hashlib.sha256(raw).hexdigest()
        catalog = json.loads(raw.decode("utf-8"))
        prefix = PurePosixPath(entry["path"]).parent.as_posix()
        if "entries" in catalog:
            for item in catalog["entries"]:
                destination(root, item["path"])
                if not item.get("source_url") or not item.get("license"):
                    raise ValueError("External source/license metadata is missing")
                add(prefix + "/" + item["path"], item, "size_bytes")
        elif "result_sets" in catalog:
            for case in catalog["result_sets"]:
                destination(root, case["path"])
                if not case.get("source_url") or not case.get("license"):
                    raise ValueError("External source/license metadata is missing")
                for item in case["files"]:
                    destination(root, item["name"])
                    add(prefix + "/" + case["path"] + "/" + item["name"], item, "size")
        else:
            raise ValueError("Unknown external manifest shape")
    return records, snapshots


def verify_records(root, records):
    total = 0
    for relative, record in records.items():
        path = destination(root, relative)
        if not path.is_file():
            raise FileNotFoundError(relative)
        if path.stat().st_size != record["size"] or digest(path) != record["sha256"]:
            raise ValueError("Corpus SHA256/size mismatch; nothing was modified: " + relative)
        total += record["size"]
    return dict(verified_files=len(records), verified_bytes=total)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--check-registry", action="store_true", help="CI-safe schema check; no external corpus required"
    )
    parser.add_argument(
        "--verify-all", action="store_true", help="Read and hash all files listed by the external catalogs"
    )
    args = parser.parse_args()
    registry = load_registry()
    index = entries(registry)
    if args.check_registry:
        print("reference-only corpus registry: IDs, relative paths and private-ID isolation OK")
        return
    if args.list:
        for entry in index.values():
            print(entry["id"], entry.get("path", "<private ID only>"))
        return
    value = os.environ.get("LSPP_CORPUS_DIR")
    if not value:
        raise SystemExit(
            "Set LSPP_CORPUS_DIR to the existing unified corpus root (not its public-keyword child)"
        )
    root = Path(value).resolve(strict=True)
    if root.is_relative_to(ROOT) or ROOT.is_relative_to(root):
        raise SystemExit("Corpus must be outside the repository and not its ancestor")
    records, snapshots = read_catalogs(registry, root)
    selected = {} if args.ids else records
    for name in args.ids:
        if name not in index:
            raise SystemExit("Unknown corpus ID: " + name)
        path = resolve(index[name], root)
        relative = index[name]["path"]
        matches = {
            key: row
            for key, row in records.items()
            if key == relative or (path.is_dir() and key.startswith(relative + "/"))
        }
        if not matches and name not in {e["id"] for e in registry["catalogs"]}:
            raise ValueError("Registered path has no external file metadata: " + name)
        selected.update(matches)
    # Check every registered public path even when no binaries are hashed.
    if not args.ids:
        for group in PUBLIC_GROUPS:
            for entry in registry[group]:
                resolve(entry, root)
    report = (
        verify_records(root, records if args.verify_all else selected)
        if args.verify_all or args.ids
        else dict(indexed_files=len(records))
    )
    for relative, expected in snapshots.items():
        if digest(destination(root, relative)) != expected:
            raise ValueError("External catalog changed during verification; repeat with a stable catalog")
    print(json.dumps(dict(**report, catalogs_sha256=snapshots, read_only=True), ensure_ascii=False))


if __name__ == "__main__":
    main()
