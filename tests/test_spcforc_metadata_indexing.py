"""The public stored-column index preserves source metadata associations after selection."""
import pytest

from tests.test_ascii_spcforc_database import extract


@pytest.mark.parametrize("selected", [[10], [10, 90]])
def test_selected_ids_use_stored_columns_to_identify_source_setid(tmp_path, selected):
    _, result = extract(tmp_path, entity_ids=selected)
    assert result["status"] == "succeeded"
    data = result["data"]
    metadata = data["entity_metadata"]
    assert data["ids"] == selected
    assert metadata["column_order"] == "first force table"
    assert metadata["raw_node_id_tokens"] == [["90"], ["10"]]
    expected_setid = {10: 0, 90: 7}
    for node, index in zip(data["ids"], data["stored_columns"]):
        assert int(metadata["raw_node_id_tokens"][index][0]) == node
        assert metadata["setid"][index] == expected_setid[node]
