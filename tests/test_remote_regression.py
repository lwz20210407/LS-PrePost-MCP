import hashlib
import json

import pytest

from tools.remote_regression import seal_capture, targets, verify_cell, verify_window


def fake_capture(root):
    root.mkdir()
    report = dict(environment="UU remote", protocol=0, started_at=10, finished_at=20)
    (root / "uu-result.json").write_text(json.dumps(report))
    for version, mode, language in targets():
        directory = root / "matrix" / f"{version}-{mode}-{language}-unlocked"
        directory.mkdir(parents=True)
        result = dict(cell=dict(version=version, mode=mode, language=language, request_id="a" * 32),
                      lanes={name: dict(status="failed", error="Recorded native rejection",
                                        desktop_before="unlocked", desktop_after="unlocked")
                             for name in ("execution", "png", "mp4")})
        (directory / "matrix-result.json").write_text(json.dumps(result))
    seal_capture(root)
    return dict(environment="UU", phase="confirmed", operator_confirmed=True,
                disconnected_from=9, disconnected_until=21)


def test_native_failures_are_preserved_when_remote_evidence_verifies(tmp_path):
    root = tmp_path / "capture"
    confirmation = fake_capture(root)
    result = verify_cell(root, targets()[0], confirmation)
    assert result["native_lane_statuses"] == dict(execution="failed", png="failed", mp4="failed")
    assert result["scope"] == "probe_evidence_and_remote_window"


@pytest.mark.parametrize("changes", [dict(operator_confirmed=False), dict(disconnected_from=11),
                                     dict(disconnected_until=19), dict(phase="armed"),
                                     dict(disconnected_from=float("nan")), dict(environment="RDP")])
def test_console_or_arming_is_not_proof_of_a_disconnected_uu_window(changes):
    confirmation = dict(environment="UU", phase="confirmed", operator_confirmed=True,
                        disconnected_from=9, disconnected_until=21)
    confirmation.update(changes)
    with pytest.raises(ValueError):
        verify_window(dict(environment="UU remote", protocol=0, started_at=10, finished_at=20), confirmation)


def test_capture_requires_all_thirteen_cells_and_rejects_changed_records(tmp_path):
    root = tmp_path / "capture"
    confirmation = fake_capture(root)
    path = next((root / "matrix").glob("*/matrix-result.json"))
    path.write_text("{}")
    target = tuple(path.parent.name.removesuffix("-unlocked").split("-"))
    with pytest.raises(ValueError, match="changed"):
        verify_cell(root, target, confirmation)
    path.unlink()
    with pytest.raises(ValueError, match="13"):
        seal_capture(root)


def test_changed_native_artifact_is_rejected_after_operator_confirmation(tmp_path):
    root = tmp_path / "capture"
    confirmation = fake_capture(root)
    target = targets()[0]
    directory = root / "matrix" / ("-".join(target) + "-unlocked")
    saved = directory / "execution" / "artifacts"
    saved.mkdir(parents=True)
    rows = []
    for name in ("receipt.txt", "model.k"):
        path = saved / name
        path.write_bytes(b"synthetic evidence")
        rows.append(dict(path=path.relative_to(directory).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    path = directory / "matrix-result.json"
    result = json.loads(path.read_text())
    result["lanes"]["execution"].update(status="succeeded", artifacts={}, captured_files=rows)
    path.write_text(json.dumps(result))
    seal_capture(root)
    assert verify_cell(root, target, confirmation)["native_lane_statuses"]["execution"] == "succeeded"
    (saved / "model.k").write_bytes(b"changed after capture")
    with pytest.raises(ValueError, match="artifact changed"):
        verify_cell(root, target, confirmation)
