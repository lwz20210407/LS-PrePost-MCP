"""I04 input-tree identities and input limitations from the shared keyword preflight."""

import hashlib
import os
from pathlib import Path

from ls_prepost_mcp.domain.model import preflight_includes
from tools.fetch_corpus import io_root, plain_path


def input_tree(source, family, *, keyword):
    """Return publishable metadata plus private paths used only for preservation checks."""
    source = plain_path(source).absolute()
    family = [plain_path(path).absolute() for path in family]
    if keyword:
        report = preflight_includes(source)
        files = report["files"]
        public = {key: report[key] for key in ("ok", "tree_sha256", "tree_sha256_version")}
        public["tree_kind"] = "keyword_include_tree"
        public["problems"] = [
            {key: problem.get(key) for key in ("kind", "hint", "severity", "relative", "name_line", "keyword")}
            for problem in report["problems"]
        ]
        public["unsupported_native_variants"] = sorted({
            ref["keyword"] for ref in report["references"] if ref["keyword"] != "*INCLUDE"
        })
    else:
        files = []
        for path in family:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            files.append(dict(path=str(path), relative=path.relative_to(source.parent).as_posix(),
                              role="result_family", size=path.stat().st_size, sha256=digest))
        public = dict(ok=True, tree_kind="result_family", tree_sha256_version=1,
                      tree_sha256=hashlib.sha256("\n".join(f["sha256"] for f in files).encode("ascii")).hexdigest(),
                      problems=[], unsupported_native_variants=[])
    # Includes may legitimately live above the main deck. Declare a common base,
    # rather than publishing null locators or leaking absolute local paths.
    common = Path(os.path.commonpath([str(plain_path(row["path"]).parent) for row in files])) if files else source.parent
    public["files_relative_to"] = "common_input_directory"
    public["main_relative"] = source.relative_to(common).as_posix()
    public["files"] = [dict(relative=plain_path(row["path"]).relative_to(common).as_posix(),
                            **{key: row[key] for key in ("role", "size", "sha256")}) for row in files]
    return public, {Path(row["path"]): row["sha256"] for row in files}


def input_classification(tree):
    """Concrete preflight evidence; successful preflight is not a native verdict."""
    errors = [p for p in tree["problems"] if p["severity"] == "error"]
    if errors:
        p = errors[0]
        return "input_" + (p.get("hint") or p["kind"])
    if tree["unsupported_native_variants"]:
        return "unsupported_native_include_variant"
    return "preflight_ok_requires_native_diagnosis"


def directory_snapshot(paths):
    """Private recursive name inventory; do not follow directory symlinks/junctions."""
    roots = sorted({plain_path(path).parent for path in paths})
    roots = [p for p in roots if not any(p != other and p.is_relative_to(other) for other in roots)]
    snapshot = {}
    for directory in roots:
        io_directory = io_root(directory)
        names = []
        for current, folders, files in os.walk(io_directory, followlinks=False):
            relative = Path(current).relative_to(io_directory)
            names.extend("d:" + (relative / name).as_posix() for name in folders)
            names.extend("f:" + (relative / name).as_posix() for name in files)
            folders[:] = [name for name in folders if not (Path(current) / name).is_symlink()
                          and not getattr((Path(current) / name).lstat(), "st_file_attributes", 0) & 0x400]
        snapshot[directory] = tuple(sorted(names))
    return snapshot
