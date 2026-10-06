"""Tiny coordinate round-off: detection and the move-far-and-back cleanup."""
import math
from pathlib import Path

import numpy as np
import pytest

from ls_prepost_mcp.domain.model import FieldError, KeywordDeck
from ls_prepost_mcp.domain.model.coordinates import clean_coordinates, coordinate_noise
from ls_prepost_mcp.domain.model.geometry import nodes
from ls_prepost_mcp.domain.model.mesh import translate_nodes
from ls_prepost_mcp.domain.model.operations import check_deck, edit_deck

pytest.importorskip("ansys.dyna.core")

NOISY = [("-10.0", "0.0", "0.0"), ("10.0000000000001", "1e-13", "0.0"), ("-5.0", "3.0", "2.0"),
         ("5.0", "3.0000000000004", "2.0"), ("0.0", "3.0", "5.0"), ("1.25", "7.5", "5.0")]


def _deck(tmp_path: Path, rows: list[tuple[str, str, str]]) -> KeywordDeck:
    text = "*KEYWORD\n*NODE\n" + "".join(f"{i + 1:>8}{x:>16}{y:>16}{z:>16}\n" for i, (x, y, z) in enumerate(rows))
    (tmp_path / "main.k").write_bytes((text + "*END\n").encode())
    return KeywordDeck.load(tmp_path / "main.k")


def test_detects_mirror_zero_and_plane_noise(tmp_path: Path) -> None:
    report = coordinate_noise(_deck(tmp_path, NOISY))
    x, y, z = (report["axes"][a] for a in "xyz")
    assert x["broken_mirror_pairs"] == 1 and x["nodes"] == 2
    assert y["near_zero"] == 1 and y["split_values"] == 4 and z["nodes"] == 0
    assert report["noisy_axes"] == ["x", "y"] and report["nodes_affected"] == 5  # nodes 1-5 sit in noisy groups


def test_cleanup_restores_exact_values_and_leaves_clean_rows(tmp_path: Path) -> None:
    deck = _deck(tmp_path, NOISY)
    result = clean_coordinates(deck)
    assert result["axes"] == "xy" and result["changed_nodes"] == 2 and result["max_change"] < result["bound"]
    assert result["noise_after"]["nodes_affected"] == 0
    lines = deck.main.text().splitlines()
    assert lines[3] == "       2            10.0             0.0             0.0"
    assert lines[2] == "       1           -10.0             0.0             0.0"  # untouched rows keep their bytes
    assert clean_coordinates(deck)["changed_nodes"] == 0


def test_cleanup_removes_translate_there_and_back_noise(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    rows = [tuple(f"{v:.6f}" for v in rng.uniform(-50, 50, 3)) for _ in range(40)]
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    original, moved = _deck(tmp_path / "a", rows), _deck(tmp_path / "b", rows)
    ids = nodes(moved)[0].tolist()
    translate_nodes(moved, ids, (1.0e3 + 0.1, 0.0, 0.0))
    translate_nodes(moved, ids, (-1.0e3 - 0.1, 0.0, 0.0))
    assert not np.array_equal(nodes(original)[1], nodes(moved)[1])  # round-off was introduced
    for deck in (original, moved):
        clean_coordinates(deck, axes="xyz", magnitude=1.5 * 2.0 ** 20)
    assert np.array_equal(nodes(original)[1], nodes(moved)[1])


def test_check_and_edit_deck_ops(tmp_path: Path) -> None:
    _deck(tmp_path, NOISY)
    checked = check_deck(str(tmp_path / "main.k"))
    assert checked["coordinate_noise"]["nodes_affected"] == 5 and any("round-off" in w for w in checked["warnings"])
    result = edit_deck(str(tmp_path / "main.k"), [{"op": "clean_coordinates"}], output_dir=str(tmp_path / "out"))
    assert result["status"] == "succeeded", result
    assert coordinate_noise(KeywordDeck.load(tmp_path / "out" / "main.k"))["nodes_affected"] == 0


def test_cleanup_keeps_mirror_pairs_exact(tmp_path: Path) -> None:
    """Cube corners p +/- h/2 of a lattice symmetric about 0 (the case that broke with D = 2**k)."""
    h = 1.0e-4
    centres = -4.5e-4 + h * np.arange(10)
    values = sorted({float(c + s * h / 2) for c in centres for s in (-1, 1)})
    rows = [(f"{v:.9e}", f"{-v:.9e}", "0.0") for v in values]  # as the Peridigm converter writes them
    deck = _deck(tmp_path, rows)
    assert coordinate_noise(deck)["nodes_affected"] > 0
    result = clean_coordinates(deck)
    assert result["noise_after"]["nodes_affected"] == 0
    assert result["magnitude"] / 2.0 ** math.floor(math.log2(result["magnitude"])) == 1.5
    xs = nodes(deck)[1][:, 0]
    assert set(xs.tolist()) == set((-xs).tolist()) and 0.0 in xs.tolist()


def test_power_of_two_magnitude_straddling_a_binade_is_refused(tmp_path: Path) -> None:
    deck = _deck(tmp_path, NOISY)
    with pytest.raises(FieldError, match="straddles a power of two"):
        clean_coordinates(deck, axes="xy", magnitude=2.0 ** 20)


def test_values_straddling_a_grid_point_are_snapped_together(tmp_path: Path) -> None:
    """Cubit-style split planes: 4.702 and 4.702 + 3e-9 can land on two grid points; snap joins them."""
    rows = [("4.702", "0.0", "0.0"), ("4.702000003", "1.0", "0.0"), ("-4.7020000000001", "2.0", "0.0"),
            ("10.0", "3.0", "0.0"), ("1e-12", "4.0", "0.0")]
    deck = _deck(tmp_path, rows)
    result = clean_coordinates(deck)
    assert result["noise_after"]["nodes_affected"] == 0
    xs = nodes(deck)[1][:, 0].tolist()
    assert xs == [4.702, 4.702, -4.702, 10.0, 0.0]


def test_float32_noise_chain_snaps_to_the_cleanest_decimal(tmp_path: Path) -> None:
    """Cubit tensile_test: values around -0.254 spaced 7.45e-9 (float32 level) over 3e-8 > 2 tol."""
    noisy = [-0.2540000006557, -0.2539999932051, -0.2539999857545, -0.2539999783039, -0.2539999708533]
    rows = [(f"{v:.13f}", "0.0", "0.0") for v in noisy] + [("10.0", "1.0", "0.0"), ("0.254", "2.0", "0.0")]
    deck = _deck(tmp_path, rows)
    result = clean_coordinates(deck)
    assert result["noise_after"]["nodes_affected"] == 0
    assert nodes(deck)[1][:, 0].tolist() == [-0.254] * 5 + [10.0, 0.254]


def test_a_chain_wider_than_the_snap_span_is_left_alone(tmp_path: Path) -> None:
    from ls_prepost_mcp.domain.model.coordinates import SNAP_SPAN

    size = 1000.0
    tol = 1e-9 * size
    steps = int(1.2 * SNAP_SPAN)
    rows = [(f"{1.0 + k * 0.9 * tol:.9f}", "0.0", "0.0") for k in range(steps)] + [(f"{size + 1.0}", "0.0", "0.0")]
    deck = _deck(tmp_path, rows)
    result = clean_coordinates(deck, axes="x")
    assert result["snapped_values"]["x"] == 0
