"""Explicit evidence selection for the contact-geometry dependency refresh only."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/decisions/evidence/contact-geometry-refresh/context.json"
P03_PRODUCT_PATHS = tuple("src/ls_prepost_mcp/" + path for path in (
    "model_recipes.py", "data/model_recipes.json", "automation/recipes.py", "knowledge_index.py",
    "model_target_tools.py", "core/validation.py", "domain/model/materials.py", "domain/model/operations.py",
    "domain/model/deck.py", "domain/model/matching.py", "domain/model/_identity.py", "domain/model/fields.py",
    "domain/model/layouts.py", "domain/model/schema.py", "domain/model/cards.py", "domain/model/persist.py",
    "domain/model/references.py", "domain/model/keyword_docs.py", "server.py", "compact_server.py",
    "operation_registry.py", "data/operations.json", "domain/model/contact_report.py", "domain/model/contact.py",
))
P06_IDENTITY_PRODUCT_PATHS = tuple("src/ls_prepost_mcp/" + path for path in (
    "domain/model/_identity.py", "domain/model/contacts.py", "domain/model/contact.py", "domain/model/cards.py",
    "domain/model/schema.py", "domain/model/keyword_docs.py", "domain/model/fields.py", "domain/model/layouts.py",
    "domain/model/geometry.py", "domain/model/sets.py", "domain/model/node_sets.py", "domain/model/lists.py",
    "domain/model/tables.py", "domain/model/materials.py", "domain/model/deck.py", "domain/model/matching.py",
    "domain/model/blocks.py", "domain/model/text.py", "domain/model/parameters.py", "domain/model/scope.py",
    "domain/model/links.py", "domain/model/references.py", "domain/model/includes.py", "domain/model/tree.py",
    "domain/model/access.py", "domain/model/preflight.py", "domain/model/persist.py", "domain/model/operations.py",
    "model_target_tools.py", "service.py", "config.py", "jobs.py", "core/contracts.py", "core/validation.py",
    "domain/model/contact_report.py",
))
P06_IDENTITY_TEST_PATHS = (
    "tests/test_contact_target_identities.py", "tests/test_keyword_engine_contact.py",
    "tests/test_keyword_engine_properties.py", "tests/data/p06-contact-identity-golden.json",
)


def evidence_path(task, *, historical=False):
    index = json.loads(INDEX.read_text(encoding="utf8"))
    selected = index["historical" if historical else "current"][task]
    path = ROOT / selected["path"]
    assert path.resolve().is_relative_to((ROOT / "docs/decisions/evidence").resolve())
    return path


def read_evidence(task, *, historical=False):
    path = evidence_path(task, historical=historical)
    if not path.is_file():
        raise FileNotFoundError(f"Missing actual current {task} capture: {path}; historical evidence cannot substitute")
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    assert len(raw) < 512 * 1024, "Keep each refresh context below the public evidence size limit"
    if historical:
        expected = json.loads(INDEX.read_text(encoding="utf8"))["historical"][task]["sha256_lf"]
        assert hashlib.sha256(raw).hexdigest() == expected, "Historical evidence bytes changed: " + str(path)
    return json.loads(raw)


def require_host_products(evidence, task):
    assert task in ("P03", "P06_identity")
    expected = P03_PRODUCT_PATHS if task == "P03" else P06_IDENTITY_PRODUCT_PATHS
    actual = [item["path"] for item in evidence["product_source_identity"]]
    assert len(actual) == len(set(actual)) and set(actual) == set(expected), "Missing current consumed host dependency"
