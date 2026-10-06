"""I06: reject invalid planning data rather than publishing misleading docs."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from task_catalog import read_catalog, registered_tools  # noqa: E402
from validate_tasks import validate  # noqa: E402


@pytest.mark.parametrize(
    "mutation,fragment",
    [
        (lambda c: c["tasks"][0].update(status="done"), "evidence"),
        (lambda c: c["tasks"][0].update(existing=["not_a_tool"]), "unregistered"),
        (lambda c: c["tasks"][0].update(depends_on=["MISSING"]), "dependency"),
        (lambda c: c["tasks"][0].update(id=c["tasks"][1]["id"]), "unique"),
        (lambda c: c["milestones"][0]["tasks"].append("P01"), "membership"),
        (lambda c: c["tasks"][0].pop("acceptance"), "missing acceptance"),
    ],
)
def test_invalid_catalog_is_rejected(mutation, fragment):
    catalog = copy.deepcopy(read_catalog())
    mutation(catalog)
    assert any(fragment in error for error in validate(catalog, registered_tools()))
