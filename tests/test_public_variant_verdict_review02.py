"""Legal unsupported INCLUDE variants are product gaps, not unavailable inputs."""
from types import SimpleNamespace

import pytest

import tests.test_public_corpus_native as runner
from tools.public_corpus_preflight import input_classification


def tree():
    return dict(ok=True, problems=[], unsupported_native_variants=["*INCLUDE_TRANSFORM"])


def test_legal_variant_is_classified_as_a_product_gap():
    assert input_classification(tree()) == "product_unsupported_include_variant"


def test_legal_variant_runs_native_reference_then_remains_a_failed_product_case(monkeypatch):
    calls = []

    def native(service, source, record):
        calls.append(source)
        record["checks"].append(dict(name="native_variant_reference", status="succeeded"))

    monkeypatch.setattr(runner, "keyword_variant_reference", native, raising=False)
    record = dict(input_tree=tree(), checks=[])
    request = SimpleNamespace(node=SimpleNamespace(user_properties=[]))
    with pytest.raises(pytest.fail.Exception, match="product_unsupported_include_variant"):
        runner.test_public_corpus({"kind": "keyword"}, (object(), "owned-source", record), request)
    assert calls == ["owned-source"]
    assert record["input_classification"] == "product_unsupported_include_variant"
    assert not request.node.user_properties  # no evidence_only/xfail exemption


def test_failed_native_reference_is_not_replaced_by_an_input_exemption(monkeypatch):
    def native(*args):
        raise AssertionError("native read failed")

    monkeypatch.setattr(runner, "keyword_variant_reference", native, raising=False)
    request = SimpleNamespace(node=SimpleNamespace(user_properties=[]))
    record = dict(input_tree=tree(), checks=[])
    try:
        with pytest.raises(AssertionError, match="native read failed"):
            runner.test_public_corpus({"kind": "keyword"}, (object(), "owned-source", record), request)
    except pytest.xfail.Exception:
        pytest.fail("Product failure was exempted before running the native reference")
    assert not request.node.user_properties
