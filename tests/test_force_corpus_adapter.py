"""I04 calls the Q06 native tool with an explicitly declared contact side."""

import csv
from types import SimpleNamespace

from tests.test_ascii_force_database import contact
from tests.test_public_corpus_native import ascii_cross_check


def test_public_contact_adapter_requires_and_preserves_the_registered_side(tmp_path):
    source = tmp_path / "rcforc"
    source.write_text(contact())
    curve = tmp_path / "native.csv"
    with curve.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerows([["time", "value"], [0, 2], [2, 6]])
    calls = []

    def native(path, database, component, units, entity_id=None, side=None):
        calls.append(side)
        return {"status": "succeeded", "artifacts": [{"path": str(curve)}]}

    case = {"database": "rcforc", "component": 1, "entity_id": 7, "side": 1}
    record = {"checks": []}
    ascii_cross_check(SimpleNamespace(extract_native_ascii_curve=native), source, record, case, None)
    assert calls == [1] and "RCFORC" in record["scope"]
