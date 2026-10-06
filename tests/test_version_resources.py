"""I03: executable metadata outranks names without claiming runtime validation."""

import ast
import os
from functools import lru_cache
from pathlib import Path

import pytest

from ls_prepost_mcp.native import _version_resource, versions


def resource(version="4.13.0.1", **changes):
    return dict(dict(file_version=version, product_version=version, fixed_file_version=version,
                     product_name="LS-PrePost"), **changes)


@pytest.mark.parametrize("version", ["4.8.0.1", "4.10.0.1", "4.13.0.1"])
def test_resource_family_wins_over_renamed_executable(monkeypatch, version):
    monkeypatch.setattr(versions, "read_version_resource", lambda _: resource(version))
    family = ".".join(version.split(".")[:2])
    assert versions.installation_version("unknown.exe") == family
    result = versions.profile("lsprepost4.13.exe")
    assert result["version"] == family and result["version_source"] == "file_version_resource"
    assert result["runtime_verified"] is False
    assert result["path_hint_conflict"] == (family != "4.13")


@pytest.mark.parametrize("field", ["file_version", "product_version", "fixed_file_version"])
def test_any_reported_411_resource_blocks_before_launch(monkeypatch, field):
    monkeypatch.setattr(versions, "read_version_resource", lambda _: resource(**{field: "4.11.9.0"}))
    with pytest.raises(ValueError, match="4.11.*excluded"):
        versions.require_installation("lsprepost4.13.exe", version="4.13")


def test_stale_fixed_version_is_reported_but_consistent_strings_determine_family(monkeypatch):
    monkeypatch.setattr(versions, "read_version_resource",
                        lambda _: resource("4.10.0.1", fixed_file_version="4.9.0.1"))
    result = versions.require_capability("lsprepost4.13.exe", "batch")
    assert result["version"] == "4.10" and result["policy"] == "regression_subset"
    assert result["resource_conflict"] is True and result["path_hint_conflict"] is True
    with pytest.raises(ValueError, match="unavailable"):
        versions.require_capability("lsprepost4.13.exe", "queue_model_identity")


def test_disagreeing_strings_or_configured_label_are_rejected(monkeypatch):
    monkeypatch.setattr(versions, "read_version_resource", lambda _: resource(product_version="4.10.0.1"))
    with pytest.raises(ValueError, match="strings disagree"):
        versions.require_installation("anything.exe")
    monkeypatch.setattr(versions, "read_version_resource", lambda _: resource("4.10.0.1"))
    with pytest.raises(ValueError, match="label conflicts"):
        versions.require_installation("anything.exe", version="4.13")


def test_foreign_product_cannot_masquerade_as_lspp_by_filename(monkeypatch):
    monkeypatch.setattr(versions, "read_version_resource", lambda _: resource(product_name="Python"))
    with pytest.raises(ValueError, match="different product"):
        versions.require_installation("lsprepost4.13.exe")


def test_missing_resource_retains_explicitly_unverified_path_fallback(monkeypatch):
    monkeypatch.setattr(versions, "read_version_resource", lambda _: None)
    result = versions.profile("lsprepost4.10.exe")
    assert result["version_source"] == "path_hint" and result["runtime_verified"] is False
    with pytest.raises(ValueError, match="excluded"):
        versions.require_installation("lsprepost4.11.exe", version="4.13")


def test_missing_binary_and_embedded_syntax_compatibility(tmp_path):
    assert _version_resource.read_version_resource(tmp_path / "absent.exe") is None
    for module in (versions, _version_resource):
        ast.parse(Path(module.__file__).read_text(encoding="utf8"), feature_version=(3, 6))


@pytest.mark.skipif(os.name != "nt", reason="Windows executable resource cache")
def test_replaced_file_invalidates_cache_even_with_same_size_and_timestamp(tmp_path, monkeypatch):
    path = tmp_path / "native.exe"
    path.write_text("4.13")
    calls = []

    @lru_cache(maxsize=8)
    def reader(filename, *identity):
        calls.append(identity)
        return resource(Path(filename).read_text())

    monkeypatch.setattr(_version_resource, "_read", reader)
    assert _version_resource.read_version_resource(path)["file_version"] == "4.13"
    assert _version_resource.read_version_resource(path)["file_version"] == "4.13"
    assert len(calls) == 1
    before = path.stat()
    replacement = tmp_path / "replacement.exe"
    replacement.write_text("4.11")
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(replacement, path)
    assert _version_resource.read_version_resource(path)["file_version"] == "4.11"
    assert len(calls) == 2 and calls[0] != calls[1]
