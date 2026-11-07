"""Synthetic FTS oracles independent of the frozen QA sets and their locators."""
import hashlib
import json
import sqlite3
from dataclasses import asdict, replace

import pytest

from ls_prepost_mcp.knowledge_index import Document, build_index, search_index, terms


def candidate(number=0, **changes):
    payload = dict(id=f"model:synthetic-damping-{number}", reference="model:synthetic@" + "a" * 64,
                   description="Set explicit damping coefficients", tags=["damping", "simulation"],
                   keyword="*CONTROL_DAMPING", parameters=dict(type="object", properties=dict(dt=dict(type="number"))),
                   task_id="P10", channel="keyword", verification_level="L1", versions_verified=[],
                   field_provider_snapshot=dict(capture_viewport_snapshot="metadata-only provenance", source="backend_anchor_zebra"),
                   requirements=dict(package="fixture_capture_viewport_sdk", field_schema_snapshot_version="0.0"))
    payload.update(changes)
    return Document("model-recipe-registry", "recipe", f"Damping candidate {number}",
                    json.dumps(payload, sort_keys=True), f"test://candidate/{number}", "MIT", "public", "fixture-v1", 4, 9)


def test_metadata_only_candidates_cannot_crowd_out_a_semantic_recipe(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    semantic = Document("owned-camera-guide", "recipe", "Image export guide",
                        "Capture viewport as an image. " + " ".join(f"explanation_{i}" for i in range(150)),
                        "test://camera-guide", "MIT", "public")
    build_index(path, [semantic, *(candidate(i) for i in range(3))])
    rows = search_index(path, "capture viewport", category="recipe", limit=3)
    assert [row["source_id"] for row in rows] == ["owned-camera-guide"]


@pytest.mark.parametrize("query", ["capture viewport", "backend_anchor_zebra", "field_provider_snapshot", "field_schema_snapshot_version"])
def test_provenance_keys_and_values_are_not_recipe_features(tmp_path, query):
    path = tmp_path / "metadata.sqlite"
    build_index(path, [candidate()])
    assert search_index(path, query, category="recipe") == []


@pytest.mark.parametrize("changes", [
    dict(description="Capture viewport with a camera"),
    dict(tags=["capture", "viewport"]),
    dict(keyword="*CAPTURE_VIEWPORT"),
    dict(id="model:capture-viewport"),
    dict(parameters=dict(type="object", properties=dict(capture_viewport=dict(type="boolean")))),
    dict(parameters=dict(type="object", properties=dict(action=dict(type="string", enum=["capture viewport"])))),
])
def test_functional_content_keeps_the_same_words_searchable(tmp_path, changes):
    path = tmp_path / "functional.sqlite"
    document = candidate(**changes)
    build_index(path, [document])
    assert search_index(path, "capture viewport", category="recipe")[0]["locator"] == document.locator


def test_projection_keeps_payload_document_id_pin_hash_and_provenance_unchanged(tmp_path):
    path = tmp_path / "retained.sqlite"
    payload = dict(id="model:synthetic-damping", description="Damping control", tags=["damping"],
                   keyword="*CONTROL_DAMPING", parameters={}, reference="model:synthetic@" + "a" * 64,
                   field_provider_snapshot=dict(source="backend_anchor_zebra"), versions_verified=[])
    document = replace(candidate(), text=json.dumps(payload, separators=(",", ":")))
    expected_id = hashlib.sha256(json.dumps(asdict(document), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    build_index(path, [document])
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT id,text,sha256,source_id,locator,version,line_start,line_end FROM documents").fetchone()
    assert row == (expected_id, document.text, hashlib.sha256(document.text.encode()).hexdigest(), document.source_id,
                   document.locator, document.version, document.line_start, document.line_end)
    assert json.loads(row[1])["reference"] == json.loads(document.text)["reference"]
    result = search_index(path, "damping", category="recipe")[0]
    assert result["id"] == expected_id and result["sha256"] == row[2]
    assert result["version"] == document.version and result["locator"] == document.locator
    assert result["line_start"] == 4 and result["line_end"] == 9
    assert json.loads(result["snippet"]) == payload  # Complete compact JSON returned, including metadata and original pin.


def test_functional_title_word_inflections_and_code_parameters_still_use_normal_fts(tmp_path):
    path = tmp_path / "words.sqlite"
    document = candidate(description="Update directories with review records", parameters={
        "type": "object", "properties": {"dt2ms": {"type": "number", "description": "Mass scaling time step"}}})
    build_index(path, [replace(document, title="Readable control guide")])
    for query in ("readable control", "updating directory", "reviewing records", "dt2ms", "mass scaling", "CONTROL_DAMPING"):
        assert search_index(path, query, category="recipe"), query


@pytest.mark.parametrize("source_id,category,text", [
    ("another-public-json-source", "recipe", candidate().text),
    ("model-recipe-registry", "known_issue", candidate().text),
])
def test_projection_scope_preserves_other_sources_and_categories(tmp_path, source_id, category, text):
    path = tmp_path / "legacy.sqlite"
    document = Document(source_id, category, "Legacy reference", text, "test://legacy", "MIT", "public")
    build_index(path, [document])
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT terms FROM search_terms").fetchone()[0] == " ".join(terms(document.title + " " + document.text))
    assert search_index(path, "capture viewport", category=category)


@pytest.mark.parametrize("text", ["capture viewport metadata, not JSON", '["capture viewport"]',
    '{"description":"capture viewport"}',
    json.dumps(dict(id="model:test", description="damping", tags="capture viewport", parameters={})),
    json.dumps(dict(id="model:test", description="damping", tags=[], parameters="capture viewport")),
])
def test_invalid_registry_json_cannot_silently_fall_back_to_metadata_search(tmp_path, text):
    path = tmp_path / "invalid.sqlite"
    document = replace(candidate(), text=text)
    with pytest.raises(ValueError, match="recipe.*search|search.*recipe"):
        build_index(path, [document])
    assert not path.exists()
