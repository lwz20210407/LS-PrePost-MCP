"""The portable registry must expose compatibility periods without Python defaults."""
import json
from pathlib import Path

from ls_prepost_mcp import operation_registry as registry


def test_raw_registry_explicitly_records_periods_for_legacy_and_target_tools():
    rows = json.loads(Path(registry.__file__).with_name("data").joinpath("operations.json").read_text(encoding="utf8"))["operations"]
    runtime = {r.name: r for r in registry.OPERATIONS}
    assert {row["name"] for row in rows} == set(runtime)
    for row in rows:
        assert "legacy_until" in row, row["name"] + " relies on a Python-only default"
        expected = None if row["name"] == row["target"] else "v0.6"
        assert row["legacy_until"] == runtime[row["name"]].legacy_until == expected
