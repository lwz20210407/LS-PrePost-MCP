"""I01 read-only native snapshots, compiled from the shared Include preflight.

Only filename/path cards change in these disposable copies. Formal keyword saves
still use the raw-preserving model engine and retain their original layout.
"""
from __future__ import annotations

import hashlib
import shutil
import stat
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .domain.model import access
from .domain.model.blocks import SourceFile
from .domain.model.includes import classify, file_names, identity
from .domain.model.text import ending

RESERVE_BYTES = 64 * 1024**2


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _identity(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or (getattr(info, "st_file_attributes", 0) or 0) & 0x400:
        raise ValueError("Native snapshot file is no longer an owned regular file")
    return info.st_dev, info.st_ino


@dataclass(frozen=True)
class _Owned:
    source: Path
    path: Path
    source_sha256: str
    sha256: str
    file_identity: tuple


@dataclass
class KeywordSnapshot:
    main: Path
    root: Path
    files: tuple[_Owned, ...]
    tree_sha256: str
    listings: dict[Path, tuple[str, ...]]
    rewrites: list[dict]
    root_identity: tuple
    tree_sha256_version: int

    def verify(self, settings):
        for item in self.files:
            source = settings.input_path(str(item.source))
            if _sha(source) != item.source_sha256:
                raise ValueError("Input tree changed during native execution")
            if _identity(item.path) != item.file_identity or _sha(item.path) != item.sha256:
                raise ValueError("Native keyword snapshot changed during execution")
        for folder, names in self.listings.items():
            checked = settings.input_directory(str(folder))
            if tuple(sorted(p.name for p in checked.iterdir())) != names:
                raise ValueError("Input tree changed: source directory listing differs")

    def metadata(self):
        return {"mode": "normalized_readonly_snapshot", "tree_sha256": self.tree_sha256,
                "tree_sha256_version": self.tree_sha256_version,
                "main": str(self.main), "path_rewrites": self.rewrites,
                "files": [{"source": str(i.source), "path": str(i.path), "source_sha256": i.source_sha256,
                           "sha256": i.sha256} for i in self.files]}

    def cleanup(self):
        """Unlink only generated files still matching their creation identity and bytes.

        No recursive deletion, source removal or deletion of unknown job files.
        Changed/replaced copies remain available for diagnosis.
        """
        removed, retained = [], []
        try:
            root = self.root.lstat()
        except OSError:
            return {"removed": [], "retained": [str(i.path) for i in self.files]}
        if ((root.st_dev, root.st_ino) != self.root_identity or not self.root_identity[1]
                or (getattr(root, "st_file_attributes", 0) or 0) & 0x400):
            return {"removed": [], "retained": [str(i.path) for i in self.files]}
        for item in self.files:
            try:
                if (item.path.parent != self.root or not item.file_identity[1]
                        or _identity(item.path) != item.file_identity
                        or _sha(item.path) != item.sha256):
                    raise ValueError("Snapshot ownership or bytes changed")
                item.path.unlink()
                removed.append(str(item.path))
            except (OSError, ValueError):
                retained.append(str(item.path))
        return {"removed": removed, "retained": retained}


def _normalize(path, expected_sha, references, aliases):
    source = SourceFile.read(path)
    if source.original_sha256 != expected_sha:
        raise ValueError("Input tree changed before native snapshot compilation")
    lookup = {(r["line"], r["name_line"]): r for r in references}
    used, rewrites = set(), []
    for block in source.keyword_blocks():
        if classify(block.name) is None:
            continue
        for name, indices in file_names(block.name, block.data()):
            key = (block.line_number, block.line_number + indices[0])
            ref = lookup.get(key)
            if ref is None or ref["keyword"] != block.name or source.from_text(name) != ref["name"]:
                raise ValueError("Include map changed while compiling the native snapshot")
            native_name = "." if ref["kind"] == "path" else aliases[identity(Path(ref["path"]))].name
            for number, index in enumerate(indices):
                replacement = native_name if number == 0 else "$ normalized filename continuation"
                block.lines[index] = replacement + ending(block.lines[index])
            used.add(key)
            rewrites.append({"source": str(path), "keyword": block.name, "name_line": key[1],
                             "name_lines": [block.line_number + i for i in indices],
                             "original_name": ref["name"], "native_name": native_name})
    if used != set(lookup):
        raise ValueError("Native snapshot did not account for every Include reference")
    return source.data(), rewrites


def stage_keyword_snapshot(settings, source, directory, report):
    """Compile into fresh flat ASCII aliases so every version resolves the same files.

    Caller holds the model access guard and supplies the admitted preflight report.
    Native success releases copies; failed/changed snapshots are retained.
    """
    directory = Path(directory)
    if sum(f["size"] for f in report["files"]) + RESERVE_BYTES > shutil.disk_usage(directory).free:
        raise ValueError("Insufficient free disk space for the native keyword snapshot plus 64 MiB reserve")
    token = uuid.uuid4().hex
    aliases = {identity(Path(f["path"])): directory / f"native_{token}_{index:05d}.k"
               for index, f in enumerate(report["files"])}
    references = defaultdict(list)
    for ref in report["references"]:
        if ref["path"] is None:
            raise ValueError("Native keyword snapshot requires resolved references")
        references[identity(Path(ref["file"]))].append(ref)
    folders = {Path(f["path"]).parent for f in report["files"]}
    folders |= {Path(r["path"]) for r in report["references"] if r["kind"] == "path"}
    listings = {p: tuple(sorted(item.name for item in settings.input_directory(str(p)).iterdir())) for p in folders}
    files, rewrites = [], []
    for entry in report["files"]:
        path = Path(entry["path"])
        settings.input_path(str(path))
        access.require(path)
        dest = aliases[identity(path)]
        refs = references[identity(path)]
        if refs:
            data, changes = _normalize(path, entry["sha256"], refs, aliases)
            with dest.open("xb") as stream:
                stream.write(data)
            rewrites.extend(changes)
        else:
            with path.open("rb") as original, dest.open("xb") as output:
                shutil.copyfileobj(original, output, 1024 * 1024)
            if _sha(dest) != entry["sha256"]:
                raise ValueError("Input tree changed while copying native input")
        files.append(_Owned(path, dest, entry["sha256"], _sha(dest), _identity(dest)))
    snapshot = KeywordSnapshot(aliases[identity(Path(source))], directory, tuple(files), report["tree_sha256"],
                               listings, rewrites, (directory.stat().st_dev, directory.stat().st_ino),
                               report["tree_sha256_version"])
    admitted = settings.native_keyword_report(snapshot.main)
    expected = {(str(aliases[identity(Path(r["file"]))]), r["line"], r["name_line"], r["keyword"],
                 "." if r["kind"] == "path" else aliases[identity(Path(r["path"]))].name)
                for r in report["references"]}
    observed = {(r["file"], r["line"], r["name_line"], r["keyword"], r["name"])
                for r in admitted["references"]}
    if (expected != observed or {identity(Path(f["path"])) for f in admitted["files"]}
            != {identity(i.path) for i in snapshot.files}):
        raise ValueError("Native snapshot reference graph differs from admitted input")
    snapshot.verify(settings)
    return snapshot
