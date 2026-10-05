"""I11: external data remains read-only, even on malformed metadata or hashes."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from tools.fetch_corpus import destination, load_registry, read_catalogs, resolve, verify_records


def test_hash_failure_does_not_repair_or_replace_external_input(tmp_path):
    path = tmp_path / "model.k"
    path.write_bytes(b"*KEYWORD\n*END\n")
    records = {"model.k": dict(size=14, sha256=hashlib.sha256(path.read_bytes()).hexdigest())}
    before = path.stat().st_mtime_ns
    assert verify_records(tmp_path, records)["verified_files"] == 1
    assert path.stat().st_mtime_ns == before
    path.write_bytes(b"user edit")
    with pytest.raises(ValueError, match="mismatch"):
        verify_records(tmp_path, records)
    assert path.read_bytes() == b"user edit"
    assert [p.name for p in tmp_path.iterdir()] == ["model.k"]


@pytest.mark.parametrize(
    "path",
    [
        "../outside.k",
        "a/../outside.k",
        "/outside.k",
        "C:/outside.k",
        "C:outside.k",
        "a\\outside.k",
        "https://example.invalid/model.k",
    ],
)
def test_fixture_path_cannot_escape_root(tmp_path, path):
    with pytest.raises(ValueError):
        destination(tmp_path, path)


def test_private_id_cannot_be_bound_by_guessing_a_directory(tmp_path):
    (tmp_path / "fangzhen").mkdir()
    with pytest.raises(ValueError, match="private ID only"):
        resolve({"id": "fangzhen"}, tmp_path)


def test_registry_rejects_embedded_content_or_private_paths(tmp_path):
    import yaml

    registry = dict(
        schema_version=2,
        root_env="LSPP_CORPUS_DIR",
        catalogs=[],
        keyword_sources=[],
        result_sets=[],
        regression_inputs=[],
        private_corpora=[],
    )
    registry["private_corpora"] = [dict(id="private", path="private-data")]
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(registry), encoding="utf8")
    with pytest.raises(ValueError, match="only"):
        load_registry(path)
    registry["private_corpora"] = []
    registry["regression_inputs"] = [dict(id="sample", path="sample.k", content="*KEYWORD")]
    path.write_text(yaml.safe_dump(registry), encoding="utf8")
    with pytest.raises(ValueError, match="only"):
        load_registry(path)


def test_untrusted_external_manifest_cannot_escape_root(tmp_path):
    folder = tmp_path / "public-results"
    folder.mkdir()
    raw = dict(
        result_sets=[
            dict(
                path="case",
                source_url="https://example.invalid",
                license="local-only",
                files=[dict(name="../../outside.k", size=0, sha256="0" * 64)],
            )
        ]
    )
    (folder / "manifest.json").write_text(json.dumps(raw), encoding="utf8")
    with pytest.raises(ValueError, match="escapes"):
        read_catalogs(dict(catalogs=[dict(id="results", path="public-results/manifest.json")]), tmp_path)


def test_symlink_outside_corpus_is_rejected(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    outside = tmp_path / "outside.k"
    outside.write_bytes(b"external")
    try:
        (root / "model.k").symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation unavailable on this test host")
    with pytest.raises(ValueError, match="escapes"):
        resolve(dict(id="model", path="model.k"), root)


def test_existing_long_windows_path_is_not_misreported_missing(tmp_path):
    relative = "a" * 110 + "/" + "b" * 110 + "/model.k"
    normal = tmp_path / relative
    actual = Path("\\\\?\\" + str(normal)) if os.name == "nt" else normal
    actual.parent.mkdir(parents=True)
    content = b"*KEYWORD\n*END\n"
    actual.write_bytes(content)
    assert resolve(dict(id="long", path=relative), tmp_path).read_bytes() == content
    result = verify_records(
        tmp_path, {relative: dict(size=len(content), sha256=hashlib.sha256(content).hexdigest())}
    )
    assert result["verified_files"] == 1
