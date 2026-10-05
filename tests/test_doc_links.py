from tools.check_doc_links import json_doc_paths


def test_json_links_include_nested_runtime_metadata_but_not_external_urls():
    data = dict(items=["See docs/TOOLS.md and docs/archive/2026-10/RESULTS.md#fields",
                       dict(evidence="docs/MISSING.md")], external="https://example.org/docs/remote.md")
    assert list(json_doc_paths(data)) == ["docs/TOOLS.md", "docs/archive/2026-10/RESULTS.md", "docs/MISSING.md"]
