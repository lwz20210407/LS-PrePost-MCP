"""Host candidates are public reference facts, not executable indexed text."""
import json

from ls_prepost_mcp.knowledge_index import build_index, repository_documents, search_index
from ls_prepost_mcp.model_recipes import knowledge_documents


def test_every_host_candidate_is_a_real_public_index_source(tmp_path, monkeypatch):
    monkeypatch.setenv("LSPP_MANUAL_INDEX", str(tmp_path / "never-read-private-manual"))
    documents = [doc for doc in repository_documents() if doc.source_id == "model-recipe-registry"]
    assert len(documents) == 9
    for doc in documents:
        assert doc.category == "recipe" and doc.visibility == "public" and doc.license == "MIT"
        assert doc.locator.startswith("repo://src/ls_prepost_mcp/data/model_recipes.json#model:")
        record = json.loads(doc.text)
        assert record["backend"] == "keyword" and record["verification_level"] == "L1" and not record["versions_verified"]
        assert record["tier"] == "candidate" and "units" in record["parameters"]["required"]
    index = tmp_path / "small-public-index.sqlite"
    build_index(index, documents)
    results = search_index(index, "Johnson Cook material", category="recipe", limit=10)
    assert any(row["locator"].endswith("#model:mat-015-johnson-cook") for row in results)
    assert all(row["visibility"] == "public" for row in results)


def test_repository_provider_and_direct_candidate_documents_agree():
    from ls_prepost_mcp.knowledge_index import REPOSITORY

    actual = list(knowledge_documents(REPOSITORY))
    indexed = [doc for doc in repository_documents() if doc.source_id == "model-recipe-registry"]
    assert actual == indexed
