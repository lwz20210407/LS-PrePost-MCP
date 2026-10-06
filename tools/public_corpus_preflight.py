"""I04 input-tree identities and input limitations from the shared keyword preflight."""

import hashlib
from pathlib import Path

from ls_prepost_mcp.domain.model import preflight_includes


def input_tree(source, family, *, keyword):
    """Return publishable metadata plus private paths used only for preservation checks."""
    source = Path(source)
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
    public["files"] = [{key: row[key] for key in ("relative", "role", "size", "sha256")} for row in files]
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
