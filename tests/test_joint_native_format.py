"""Native-only classification of an inapplicable motor slot; strict cards stay visible."""

import copy

import pytest

import tools.verify_p12_joint_roundtrip as verifier
from tests.test_joint_roundtrip_contract import _copy_model

pytest.importorskip("ansys.dyna.core")


@pytest.fixture(scope="module")
def created(tmp_path_factory):
    return verifier.prepare_case("nine_types", tmp_path_factory.mktemp("motor-native-format") / "case")


@pytest.mark.parametrize("jids", [(908,), (909,), (908, 909)])
def test_only_native_export_classifies_motor_blank_r1_zero_fill(created, tmp_path, jids):
    def mutate(deck):
        for jid in jids:
            kind = "ROTATIONAL" if jid == 908 else "TRANSLATIONAL"
            block, _ = deck.find(f"*CONSTRAINED_JOINT_{kind}_MOTOR_ID", jid=jid)[0]
            deck.set(block, "r1", 0.)

    path = _copy_model(created, tmp_path, mutate)
    expected = created["spec"]["expected"]
    strict = verifier.compare(path, expected)
    assert {item["field"] for item in strict} == {f"Joint {jid}.r1" for jid in jids}
    report = verifier.native_export_comparison(path, expected)
    assert report["strict_card_differences"] == strict and report["differences"] == []
    assert {item["field"] for item in report["format_normalizations"]} == {item["field"] for item in strict}
    for item in report["format_normalizations"]:
        assert item["expected"] is None and type(item["actual"]) is float and item["actual"] == 0
        assert item["rule"] == "native_motor_type0_inapplicable_r1_zero_fill"
        assert item["source"]["manual"]["printed_page"] == "10-57"
        assert item["source"]["sdk"]["version"] == "0.12.1"
        assert item["source"]["observed_capture"]["actual_git_revision"] == "1b7fc6047c61b9df9f9f14f1cfc2d1a4001445f3"
    assert all(joint["r1"] is None for joint in expected["joints"] if joint["jid"] in (908, 909))
    assert verifier.compare(path, expected) == strict  # default/offline comparison was not relaxed


def _projection(created, monkeypatch):
    actual = verifier.snapshot(created["edited"])
    expected = copy.deepcopy(created["spec"]["expected"])
    monkeypatch.setattr(verifier, "snapshot", lambda path: actual)
    joint = next(joint for joint in expected["joints"] if joint["jid"] == 908)
    return actual["joints"][908], joint, expected


@pytest.mark.parametrize("value", [1e-300, 2., float("nan"), float("inf"), False, "0"])
def test_native_r1_rule_does_not_accept_nonzero_nonfinite_or_nonnumeric_values(created, monkeypatch, value):
    record, _, expected = _projection(created, monkeypatch)
    record["r1"] = value
    report = verifier.native_export_comparison(created["edited"], expected)
    assert report["differences"] and not report["format_normalizations"]


@pytest.mark.parametrize("side,value", [("expected", False), ("actual", False), ("expected", 1), ("actual", 1),
                                       ("expected", 0.), ("actual", 0.)])
def test_native_r1_rule_requires_explicit_integer_type_zero_on_both_sides(created, monkeypatch, side, value):
    record, joint, expected = _projection(created, monkeypatch)
    record["r1"] = 0.
    (record if side == "actual" else joint)["type"] = value
    report = verifier.native_export_comparison(created["edited"], expected)
    assert report["differences"] and not report["format_normalizations"]


@pytest.mark.parametrize("value", [0, 0., -0.])
def test_native_r1_rule_accepts_only_exact_numeric_zero_as_writer_representation(created, monkeypatch, value):
    record, _, expected = _projection(created, monkeypatch)
    record["r1"] = value
    report = verifier.native_export_comparison(created["edited"], expected)
    assert report["strict_card_differences"] and report["differences"] == []
    assert [item["field"] for item in report["format_normalizations"]] == ["Joint 908.r1"]


@pytest.mark.parametrize("keyword", ["*CONSTRAINED_JOINT_ROTATIONAL_MOTOR_ID_LOCAL",
                                     "*CONSTRAINED_JOINT_ROTATIONAL_MOTOR_ID_FAILURE",
                                     "*CONSTRAINED_JOINT_GEAR_ID", "*CONSTRAINED_JOINT_REVOLUTE_ID"])
def test_native_r1_rule_cannot_generalize_to_other_keywords_or_options(created, monkeypatch, keyword):
    record, joint, expected = _projection(created, monkeypatch)
    record.update(r1=0., keyword=keyword)
    joint["keyword"] = keyword
    report = verifier.native_export_comparison(created["edited"], expected)
    assert report["differences"] and not report["format_normalizations"]


@pytest.mark.parametrize("side", ["actual", "expected"])
def test_native_r1_rule_never_hides_a_missing_slot(created, monkeypatch, side):
    record, joint, expected = _projection(created, monkeypatch)
    record["r1"] = 0.
    del (record if side == "actual" else joint)["r1"]
    report = verifier.native_export_comparison(created["edited"], expected)
    assert any(item["field"] == "Joint 908.field_names" for item in report["differences"])
    assert not report["format_normalizations"]


@pytest.mark.parametrize("field,value", [("parm", 3.), ("lcid", 999), ("type", 1), ("rps", .25)])
def test_native_r1_rule_leaves_other_parameter_differences_failed(created, monkeypatch, field, value):
    record, _, expected = _projection(created, monkeypatch)
    record.update(r1=0., **{field: value})
    report = verifier.native_export_comparison(created["edited"], expected)
    assert any(item["field"] == "Joint 908." + field for item in report["differences"])
