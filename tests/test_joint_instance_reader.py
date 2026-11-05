"""Repeated Joint cards reuse the model engine's instance boundaries and named fields."""

import pytest

from ls_prepost_mcp.domain.model import KeywordDeck, joint_checks
from ls_prepost_mcp.domain.model.blocks import SourceFile, parse_blocks
from ls_prepost_mcp.domain.model.text import encode
from tests.test_keyword_engine_joints import _joint_deck, _nodes, _row


def repeated(tmp_path, kind="ROTATIONAL_MOTOR", count=2):
    coordinates = _nodes((301, (0, 0, 0)), (302, (0, 0, 0)), (303, (0, 0, 40)),
                         (304, (0, 0, 40)), (305, (40, 0, 0)), (306, (40, 0, 0)))
    text = f"*CONSTRAINED_JOINT_{kind}_ID\n"
    for jid in range(7, 7+count):
        text += f"{jid:>10}manual instance {jid}\n" + _row(301, 302, 303, 304, 305, 306) + "      0.75     0.125\n"
        if kind.endswith("MOTOR"):
            text += "                  70         0\n"
    extra = ("*CONTROL_RIGID\n         1\n*DEFINE_CURVE\n        70\n"
             "                 0.0                 2.0\n                 1.0                 2.0\n")
    return _joint_deck(tmp_path, coordinates, text, extra)


def test_product_joint_check_reads_both_motor_id_parm_cards_in_a_shared_block(tmp_path):
    deck = repeated(tmp_path)
    report = joint_checks.check_joints(deck)
    assert not report["errors"] and not report["unverified"], report
    assert [joint["jid"] for joint in report["joints"]] == [7, 8]


@pytest.mark.parametrize("kind,count", [("REVOLUTE", 2), ("ROTATIONAL_MOTOR", 1)])
def test_existing_revolute_and_single_motor_shapes_remain_clean(tmp_path, kind, count):
    report = joint_checks.check_joints(repeated(tmp_path, kind, count))
    assert not report["errors"] and not report["unverified"], report
    assert [joint["jid"] for joint in report["joints"]] == list(range(7, 7+count))


def test_repeated_motor_with_missing_parm_is_unverified_not_a_partial_joint_list(tmp_path):
    deck = repeated(tmp_path)
    block = next(b for b in deck.iter_blocks() if "ROTATIONAL_MOTOR" in b.name)
    block.lines.pop()
    report = joint_checks.check_joints(deck)
    assert report["unverified"] and not report["joints"]


@pytest.mark.parametrize("kind,count", [("REVOLUTE", 1), ("REVOLUTE", 2),
                                        ("ROTATIONAL_MOTOR", 1), ("ROTATIONAL_MOTOR", 2)])
def test_explicit_instance_reader_covers_every_data_line(tmp_path, kind, count):
    deck = repeated(tmp_path, kind, count)
    block = next(b for b in deck.iter_blocks() if b.name.startswith("*CONSTRAINED_JOINT_"))
    instances = joint_checks.joint_instances(deck, block)
    assert [site["jid"] for site, _ in instances] == list(range(7, 7+count))
    assert [nodes[1] for _, nodes in instances] == [301]*count
    starts = [site["line"] - block.line_number for site, _ in instances]
    assert starts[0] == block.data()[0][0] and starts == sorted(set(starts))
    # Project already located records back through the existing named-field engine.
    for start, end in zip(starts, [*starts[1:], len(block.lines)]):
        text = "*KEYWORD\n" + block.lines[0] + "".join(block.lines[start:end]) + "*END\n"
        source = SourceFile(path=tmp_path / "projection.k", original=encode(text), blocks=parse_blocks(text))
        for item in source.blocks:
            item.file = source
        fragment = KeywordDeck(source, [])
        actual = next(b for b in fragment.iter_blocks() if b.name.startswith("*CONSTRAINED_JOINT_"))
        assert fragment.get(actual, "rps").value == .75 and fragment.get(actual, "damp").value == .125
