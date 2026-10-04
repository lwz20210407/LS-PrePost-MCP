"""Apply saved physical deletion to an explicitly requested native fringe scene."""

from pathlib import Path

from .gui_mesh import verify_mesh_digest
from .gui_selection import part_visibility
from .gui_visibility import flags, transitions
from .jobs import atomic_json
from .result_validity import load_physical_validity, reject_adaptive_family


def masked_flags(old, physical, state, domain):
    if {uid for kind, uid in old if kind == domain} != set(physical.lookup):
        raise ValueError("Native and physical-mask user-ID registries disagree")
    return {key: active and physical.alive(state, key[1]) if key[0] == domain else active
            for key, active in old.items()}


def physical_fringe_scope(service, manager, session_id, meta, domain, state, time_value, directory):
    """Hide deleted elements; preserve existing Blank of present elements and part flags.

    Called under the render transaction lock, after state and part isolation.
    Values still come from SCL; LASSO supplies only the explicit deletion mask.
    """
    if domain not in ("solid", "shell"):
        raise ValueError("Physical fringe masking currently supports standard solid/shell elements")
    source = meta.get("staged_model")
    if meta.get("source"):
        reject_adaptive_family(meta["source"])
    baseline = manager.dispatch(session_id, "gui_mesh_digest", {})
    if baseline["status"] != "succeeded":
        raise ValueError("Cannot establish physical-fringe native baseline")
    before = baseline["data"]
    native_directory = before.get("model_directory")
    if not source or not native_directory or Path(native_directory).resolve() != Path(source).resolve().parent:
        raise ValueError("Native model directory does not match the staged physical-mask source")
    physical = load_physical_validity(source, [state], domain)
    physical.check_time(state, time_value)
    original_parts = part_visibility(before)
    reveal = ["+m " + pid for pid, active in original_parts.items() if not active]
    restore = ["-m " + pid for pid, active in original_parts.items() if not active] + ["genselect clear"]
    report = physical.describe(physical.user_ids.tolist(), [state])
    atomic_json(directory / "physical-validity.json", report)
    try:
        visible = manager.dispatch(session_id, "gui_mesh_digest", dict(visibility_readback=True), native_commands=reveal)
        if visible["status"] != "succeeded":
            raise ValueError("Cannot read native entity flags for physical mask")
        verify_mesh_digest(before, visible["data"])
        old = flags(visible["data"], visible["job_directory"])
        desired = masked_flags(old, physical, state, domain)
        applied = manager.dispatch(session_id, "gui_mesh_digest", dict(visibility_readback=True),
                                   native_commands=transitions(domain, old, desired))
        if applied["status"] != "succeeded" or flags(applied["data"], applied["job_directory"]) != desired:
            raise ValueError("Native Blank did not enforce the requested physical deletion mask")
        verify_mesh_digest(before, applied["data"])
        report["native_visibility_verified"] = True
    finally:
        restored = manager.dispatch(session_id, "gui_mesh_digest", dict(visibility_readback=True), native_commands=restore)
        if restored["status"] != "succeeded":
            raise ValueError("Cannot restore fringe part visibility after physical masking")
        verify_mesh_digest(before, restored["data"])
        if part_visibility(restored["data"]) != original_parts or restored["data"]["current_state"] != state:
            raise ValueError("Physical fringe mask changed the requested state or part scope")
    final = flags(restored["data"], restored["job_directory"])
    expected = {uid for (kind, uid), active in final.items() if kind == domain and active}
    if any(not physical.alive(state, uid) for uid in expected):
        raise ValueError("A deleted element remains visible after physical masking")
    if not expected:
        raise ValueError("No physically present visible elements remain; no meaningful fringe can be rendered")
    report["render_scope_count"] = len(expected)
    atomic_json(directory / "physical-validity.json", report)
    return report, expected
