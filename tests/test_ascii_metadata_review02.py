"""Review02 Q06: labels are retained without inventing coordinate-system semantics."""
import pytest

from ls_prepost_mcp.domain.results.ascii_forces import read
from tests.test_ascii_force_database import SECTION, contact


def test_ac_prefix_is_a_local_frame_reference_with_its_original_text(tmp_path):
    source = tmp_path / "secforc"
    source.write_text(SECTION.replace("ac ID = 123", "AC   ID=123"), encoding="utf8")
    result = read(source, "secforc", "x_force")
    metadata = result["entity_metadata"]
    assert "coordinate_system_ids" not in metadata
    assert metadata.get("local_frame_reference") == [{"id": 123, "prefixes": ["AC   ID=123"]}]


@pytest.mark.parametrize("kind,ident,text", [("rcforc", 7, contact()), ("secforc", 9, SECTION)], ids=["rcforc", "secforc"])
def test_legend_title_map_survives_ascii_extraction(tmp_path, kind, ident, text):
    source = tmp_path / kind
    source.write_text(f"{{BEGIN LEGEND}}\n{ident} owned label for interface or section\n{{END LEGEND}}\n" + text, encoding="utf8")
    result = read(source, kind, "x_force")
    assert result["entity_metadata"].get("legend_titles") == {str(ident): "owned label for interface or section"}
    assert result["repeated_times_dropped"] == 0


def test_conflicting_titles_for_one_legend_id_are_null_with_a_warning(tmp_path):
    source = tmp_path / "rcforc"
    source.write_text("{BEGIN LEGEND}\n7 first\n7 different\n{END LEGEND}\n" + contact(), encoding="utf8")
    result = read(source, "rcforc", "x_force")
    assert result["entity_metadata"].get("legend_titles") == {"7": None}
    assert result["entity_metadata"]["ambiguous_legend_ids"] == ["7"]
    assert any("legend" in warning for warning in result["warnings"])
