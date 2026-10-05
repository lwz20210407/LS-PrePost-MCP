"""Host checks for a native load response; counts alone do not identify a model."""

import ntpath
import posixpath
import re

from .core.native_log import read_delta


def canonical_native_path(value):
    if not isinstance(value, str) or not value or any(c in value for c in "\x00\r\n"):
        raise ValueError("Native model directory is missing or invalid")
    drive, _ = ntpath.splitdrive(value)
    if drive:
        if not ntpath.isabs(value):
            raise ValueError("Native model directory must be absolute")
        return ntpath.normcase(ntpath.normpath(value)), ntpath
    if not posixpath.isabs(value):
        raise ValueError("Native model directory must be absolute")
    return posixpath.normpath(value), posixpath


def verify_loaded_model(request, data):
    """Prove active source scope, not exclusive model count or solver validity.

    Each staged input has its own directory. Native keyword reads can report
    the filename; d3plot reports its directory. Do not collapse an unrelated
    reported filename to its parent: that would accept a different input.
    """
    reset = request.get("action") == "gui_new"
    explicit_empty = request.get("expected_empty", False)
    if type(explicit_empty) is not bool or explicit_empty and request.get("file_type", "keyword") != "keyword":
        raise ValueError("Invalid expected-empty keyword contract")
    expect_empty = reset or explicit_empty
    expected = request.get("model")
    if not expected and not reset:
        return None
    if reset:
        directory, paths = canonical_native_path(request["job_directory"])
        expected = paths.join(directory, "initial.k")
    expected, paths = canonical_native_path(expected)
    if not isinstance(data, dict):
        raise ValueError("Native load has no model inventory")
    observed, _ = canonical_native_path(data.get("model_directory"))
    if observed not in (expected, paths.dirname(expected)):
        raise ValueError("Native active model does not match this request's staged input; old or associated model retained")
    counts = data.get("counts", {})
    if not isinstance(counts, dict):
        raise ValueError("Native model counters are missing")
    nodes = counts.get("nodes")
    if type(nodes) is not int or nodes < 0 or (not expect_empty and nodes == 0):
        raise ValueError("Native load did not verify a nonempty node inventory")
    if expect_empty and (nodes != 0 or type(counts.get("elements")) is not int or counts["elements"] != 0):
        raise ValueError("Native reset did not verify an empty model")
    states = counts.get("states")
    if type(states) is not int or states < 0:
        raise ValueError("Native load did not verify its state inventory")
    if (reset or request.get("file_type", "keyword") == "keyword") and states > 1:
        raise ValueError("Requested keyword model still has a multi-state result context")
    return dict(expected_source=expected, observed_model_directory=observed,
                active_source_verified=True, empty_model_verified=expect_empty,
                scope="Active source path and required counters only; not exclusive model-list or physical validity certification")


LOAD_ERROR = re.compile(
    r"(?:\*+\s*Prog Error\b|^\s*Invalid entity ID!|^\s*(?:\*+\s*)?(?:error reading\b|cannot open\b|failed to read\b|error\s*[-:]\s*invalid\s+keyword\b|error\s+occurs\s+in\s+file\b|dummy\s+read\s+data\s+until\s+next\s+keyword\b))",
    re.IGNORECASE,
)


def load_diagnostics(directory, contract):
    """Read only this request's native log suffix; do not reuse old errors."""
    info = contract.get("model_load_log")
    if info is None:
        return []
    log = directory.parent.parent / "lspost.msg"
    offset = info.get("offset")
    text = read_delta(log, offset, existed=bool(info.get("existed")))
    (directory / "model-load.log").write_text(text, encoding="utf8")
    return [line.strip() for line in text.splitlines() if LOAD_ERROR.search(line)][:30]


def verify_load_reply(request, reply, directory, contract):
    """Share identical load checks between immediate and delayed completion."""
    if not request.get("model") and request.get("action") != "gui_new":
        return None
    diagnostics = load_diagnostics(directory, contract)
    if diagnostics:
        raise ValueError("Native model load diagnostics: " + "; ".join(diagnostics))
    return verify_loaded_model(request, reply.get("data"))
