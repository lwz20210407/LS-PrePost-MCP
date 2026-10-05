"""I11: materialize hash-pinned, licensed fixtures outside the repository."""

import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def destination(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError("Corpus member escapes destination")
    return path


def verify(path, expected):
    if digest(path) != expected:
        raise ValueError("Corpus SHA256 mismatch; existing files are never replaced")


def fetch(entry, cache):
    if entry["status"] != "available":
        raise ValueError(f"{entry['id']}: {entry.get('gap', 'not available')}")
    directory = destination(cache, entry["id"])
    if entry.get("generator") == "synthetic_shell_result":
        if not directory.exists():
            from synthetic_shell_result import create_fixture

            create_fixture(directory)
        for item in entry["files"]:
            verify(destination(directory, item["path"]), item["sha256"])
        return
    directory.mkdir(parents=True, exist_ok=True)
    for item in entry["files"]:
        target = destination(directory, item["path"])
        if target.exists():
            verify(target, item["sha256"])
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if "content" in item:
            data = item["content"].encode("ascii")
        else:
            if not item["url"].startswith("https://"):
                raise ValueError("Corpus downloads require HTTPS")
            with urllib.request.urlopen(item["url"], timeout=60) as response:
                data = response.read(512 * 1024 * 1024 + 1)
            if len(data) > 512 * 1024 * 1024:
                raise ValueError("Corpus file exceeds 512 MiB download budget")
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Downloaded/generated content hash mismatch")
        with target.open("xb") as stream:
            stream.write(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    manifest = yaml.safe_load((ROOT / "tests/corpus/manifest.yaml").read_text(encoding="utf-8"))
    entries = {x["id"]: x for x in manifest["corpora"]}
    if args.list:
        for entry in entries.values():
            print(entry["id"], entry["status"])
        return
    value = os.environ.get("LSPP_CORPUS_DIR")
    if not value:
        raise SystemExit("Set LSPP_CORPUS_DIR to an external cache directory")
    cache = Path(value).resolve()
    if cache.is_relative_to(ROOT):
        raise SystemExit("Corpus cache must be outside repository")
    for name in args.ids or [n for n, e in entries.items() if e["status"] == "available"]:
        if name not in entries:
            raise SystemExit("Unknown corpus ID: " + name)
        fetch(entries[name], cache)
        print(name + ": hash-verified")


if __name__ == "__main__":
    main()
