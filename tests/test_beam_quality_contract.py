"""P09 endpoint-only BEAM contracts on tiny explicit models; no native physics claims."""
import hashlib

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck
from ls_prepost_mcp.domain.model.operations import check_deck
from ls_prepost_mcp.domain.model.quality import check_quality


def beam_deck(tmp_path, endpoints=(101, 307), coordinates=((101, 0., 0., 0.), (307, 3., 4., 0.)),
              keyword="*ELEMENT_BEAM", elform="1"):
    pytest.importorskip("ansys.dyna.core")
    dimensions = ".1,.1,.1,.1" if elform == "1" else "0,0,0,0"
    rows = ["*KEYWORD", "*PART", "owned beam", "11,21,31", "*SECTION_BEAM", f"21,{elform}", dimensions,
            "*MAT_ELASTIC", "31,1,1000,.25", "*NODE"]
    rows += [",".join(str(value) for value in row) for row in coordinates]
    rows += [keyword, f"71,11,{endpoints[0]},{endpoints[1]},0", "*END"]
    path = tmp_path / "beam.k"
    path.write_bytes(("\n".join(rows) + "\n").encode("ascii"))
    return path, KeywordDeck.load(path)


def test_plain_beam_reports_endpoint_length_user_id_and_limited_scope_readonly(tmp_path):
    path, deck = beam_deck(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    references = deck.references().summary()
    result = check_quality(deck)
    assert result["beams"]["scope"] == "endpoint_length_only"
    assert result["beams"]["count"] == 1
    assert result["beams"]["length"]["min"] == result["beams"]["length"]["max"] == 5.
    assert result["beams"]["length"]["worst"] == [dict(id=71, value=5.)]
    assert result["errors"] == []
    assert result["nodes_not_in_solid_or_shell_elements"]["count"] == 2
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert deck.references().summary() == references


def test_zero_length_beam_is_an_objective_defect_with_original_eid(tmp_path):
    _, deck = beam_deck(tmp_path, endpoints=(101, 101))
    report = check_quality(deck)
    assert any(row["kind"] == "zero_length_beams" and row["ids"] == [71] for row in report["errors"])
    assert report["ok"] is False


def test_missing_endpoint_uses_quality_undefined_node_error_not_a_zero_measurement(tmp_path):
    _, deck = beam_deck(tmp_path, endpoints=(101, 99999))
    report = check_quality(deck)
    assert any(row["kind"] == "beams_with_undefined_nodes" and row["ids"] == [71] for row in report["errors"])
    assert report["beams"]["count"] == 0
    assert report["ok"] is False


def test_public_check_keeps_endpoint_length_in_quality_without_changing_reference_check(tmp_path):
    path, _ = beam_deck(tmp_path, endpoints=(101, 101))
    result = check_deck(str(path))
    assert any(row["kind"] == "zero_length_beams" for row in result["errors"])
    assert result["quality"]["beams"]["scope"] == "endpoint_length_only"
    assert result["read_only"] is True


@pytest.mark.parametrize("form", ["6", "7", "8", "9", "", "99"])
def test_special_or_implicit_section_forms_report_geometric_zero_without_solver_invalid_error(tmp_path, form):
    path, deck = beam_deck(tmp_path, endpoints=(101, 101), elform=form)
    report = check_quality(deck)
    assert report["beams"]["length"]["min"] == 0.
    assert report["beams"]["zero_length_ids"] == [71]
    assert not any(row["kind"] == "zero_length_beams" for row in report["errors"])
    assert report["quality_coverage"]["complete"] is False and report["unsupported_quality"]
    assert report["unchecked_mesh_blocks"] == []  # Valid AST read; this is a distinct quality limitation.
    references_only = check_deck(str(path), include_mesh=False)
    result = check_deck(str(path))
    assert result["complete"] is False
    assert result["unchecked"] == references_only["unchecked"]  # Never turn quality limitations into a fake parse gap.


@pytest.mark.parametrize("coordinates", [((101, 0., 0., 0.), (307, float("nan"), 0., 0.)),
    ((101, 0., 0., 0.), (307, float("inf"), 0., 0.)), ((101, -1e308, 0., 0.), (307, 1e308, 0., 0.))])
def test_nonfinite_or_unrepresentable_length_is_not_reported_as_clean_zero(tmp_path, coordinates):
    _, deck = beam_deck(tmp_path, coordinates=coordinates)
    report = check_quality(deck)
    assert report["quality_coverage"]["complete"] is False
    assert report["beams"]["count"] == 0 and "length" not in report["beams"]
    assert report["not_graded"] and not any(row["kind"] == "zero_length_beams" for row in report["errors"])


@pytest.mark.parametrize("distance", [1e-300, 1e308])
def test_representable_lengths_use_stable_norm_without_underflow_or_square_overflow(tmp_path, distance):
    _, deck = beam_deck(tmp_path, coordinates=((101, 0., 0., 0.), (307, distance, 0., 0.)))
    report = check_quality(deck)
    assert report["beams"]["length"]["min"] == distance
    assert report["beams"]["length"]["mean"] == distance
    assert report["errors"] == []


@pytest.mark.parametrize("duplicate", ["node", "beam"])
def test_duplicate_endpoint_or_element_id_does_not_choose_an_arbitrary_definition(tmp_path, duplicate):
    path, _ = beam_deck(tmp_path)
    text = path.read_text()
    if duplicate == "node":
        text = text.replace("*ELEMENT_BEAM", "*NODE\n101,7,8,9\n*ELEMENT_BEAM")
    else:
        text = text.replace("71,11,101,307,0", "71,11,101,307,0\n71,11,307,101,0")
    path.write_text(text, encoding="ascii")
    if duplicate == "node":
        with pytest.raises(ValueError, match="Node IDs must be unique"):
            check_quality(KeywordDeck.load(path))
        return
    report = check_quality(KeywordDeck.load(path))
    assert report["quality_coverage"]["complete"] is False
    assert any(row["kind"] == "beams_with_ambiguous_ids" for row in report["errors"])
    assert report["beams"]["count"] == 0


def test_unread_node_block_suppresses_an_unproven_missing_endpoint_defect(tmp_path):
    path, _ = beam_deck(tmp_path, endpoints=(101, 99999))
    path.write_text(path.read_text().replace("*END", "*NODE\nbad-node\n*END"), encoding="ascii")
    report = check_quality(KeywordDeck.load(path))
    assert not any(row["kind"] == "beams_with_undefined_nodes" for row in report["errors"])
    assert any(row["kind"] == "beams_with_undefined_nodes" for row in report["not_graded"])
    assert report["unchecked_mesh_blocks"] and report["quality_coverage"]["complete"] is False


def test_explicit_length_threshold_only_grades_when_given_and_does_not_make_an_objective_error(tmp_path):
    _, deck = beam_deck(tmp_path)
    plain = check_quality(deck)
    assert "threshold" not in plain["beams"]["length"]
    graded = check_quality(deck, {"length": 6.})
    assert graded["beams"]["length"]["failing_ids"] == [71] and graded["errors"] == []


@pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
def test_invalid_length_threshold_rejects_instead_of_coercing_a_flag(tmp_path, value):
    _, deck = beam_deck(tmp_path)
    with pytest.raises(ValueError, match="length threshold"):
        check_quality(deck, {"length": value})


def test_tshell_is_not_accidentally_marked_covered_when_basic_beams_are_added(tmp_path):
    path, _ = beam_deck(tmp_path)
    path.write_text(path.read_text().replace("*END", "*ELEMENT_TSHELL\n91,11,101,307,101,307,101,307,101,307\n*END"), encoding="ascii")
    report = check_quality(KeywordDeck.load(path))
    assert report["beams"]["length"]["min"] == 5.
    assert report["quality_coverage"]["complete"] is False
    assert any(row["keyword"] == "*ELEMENT_TSHELL" for row in report["unsupported_quality"])


def test_missing_optional_sdk_is_honestly_unread_not_a_zero_beam_result(tmp_path, monkeypatch):
    from ls_prepost_mcp.domain.model import quality
    from ls_prepost_mcp.domain.model.layouts import Unsupported

    path = tmp_path / "without-sdk.k"
    path.write_bytes(b"*KEYWORD\n*NODE\n101,0,0,0\n307,1,0,0\n*ELEMENT_BEAM\n71,11,101,307,0\n*END\n")
    deck = KeywordDeck.load(path)
    real_layout = deck.layout

    def no_sdk(block):
        if block.name == "*ELEMENT_BEAM":
            raise Unsupported("PyDYNA is unavailable")
        return real_layout(block)

    monkeypatch.setattr(deck, "layout", no_sdk)
    report = quality.check_quality(deck)
    assert report["quality_coverage"]["complete"] is False and report["unchecked_mesh_blocks"]
    assert "beams" not in report and report["errors"] == []
