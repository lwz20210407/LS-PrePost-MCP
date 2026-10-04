"""Opt-in real GUI late-completion and owned-process crash/checkpoint recovery tests."""

import argparse
import time
import uuid
from dataclasses import replace
from pathlib import Path

import psutil

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json, fingerprint
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.sessions import alive, process_identity


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("gui-recovery-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    service = Service(Settings(root, Path(executable), timeout=120))
    fast = Service(replace(service.settings, timeout=1e-9))
    session = service.start_gui_session()
    sid = session["session_id"]
    owned = [sid]
    atomic_json(root / "started.json", session)
    checks = []

    def checked(name, result):
        atomic_json(root / (name + ".json"), result)
        assert result["status"] == "succeeded", result.get("error")
        checks.append(name)
        print(name, flush=True)
        return result

    def wait_reconcile(name):
        # Use a new host service object: no in-memory request handles are reused.
        replacement = Service(service.settings)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            result = replacement.recover_gui_session(sid)
            if not result.get("active_request"):
                atomic_json(root / (name + ".json"), result)
                checks.append(name)
                print(name, result["state"], flush=True)
                return result
            time.sleep(.1)
        raise TimeoutError("The same native request did not publish completion; no replay attempted")

    def native_nodes():
        manager = service._session_manager()
        with manager.lock(sid):
            result = manager.dispatch(sid, "list_nodes", dict(offset=0, limit=100))
        assert result["status"] == "succeeded"
        return result["data"]

    try:
        service.show_gui_session(sid, maximize=True)
        try:
            fast.gui_session_action(sid, "create_solid_box", dict(divisions=[1,1,1], size=[2.,2.,2.], units="mm"))
        except TimeoutError:
            pass
        else:
            raise AssertionError("Expected the deliberately tiny host observation timeout")
        pending = service.inspect_gui_session(sid)
        atomic_json(root / "pending-kernel.json", pending)
        assert pending["active_request"]
        reconciled = wait_reconcile("kernel-late-completion")
        assert reconciled["state"] == "ready" and reconciled["recovery_mode"] == "validated_native_kernel"
        checkpoint = Path(reconciled["last_checkpoint"])
        identity = fingerprint(checkpoint)
        baseline = native_nodes()
        assert baseline["total"] == 8
        atomic_json(root / "baseline-nodes.json", baseline)
        # An actual native transform finishes, but its host-side comparison is
        # deliberately absent. Recovery must not certify that transaction.
        commands = ["pall", "genselect clear", "genselect target node", "genselect transfer 0",
                    "genselect node add node 1", "translate_model 3 0 0", "translate_model accept", "genselect clear"]
        manager = fast._session_manager()
        try:
            with manager.lock(sid):
                manager.dispatch(sid, "gui_mesh_digest", dict(entity_type="node", entity_ids=[1]), native_commands=commands)
        except TimeoutError:
            pass
        else:
            raise AssertionError("Expected the host-validation observation timeout")
        recovered = wait_reconcile("transaction-late-completion")
        assert recovered["state"] == "uncertain" and recovered["requires_host_validation"] and recovered["dirty"]
        assert fingerprint(checkpoint) == identity
        moved = native_nodes()
        atomic_json(root / "uncertain-nodes.json", moved)
        expected = [list(row) for row in baseline["rows"]]
        next(row for row in expected if row[0] == 1)[1] += 3
        assert moved["rows"] == expected, "The timed-out transform must execute exactly once"
        try:
            service.checkpoint_gui_session(sid)
        except ValueError as exc:
            assert "trusted checkpoint" in str(exc)
        else:
            raise AssertionError("Unverified transaction overwrote the trusted checkpoint")
        checked("restore-checkpoint", service.restore_gui_checkpoint(sid))
        assert native_nodes() == baseline
        checked("validated-edit", service.translate_gui_nodes(sid, [1], [.25,0.,0.], "mm"))
        saved = native_nodes()
        try:
            service.restart_gui_session(sid)
        except ValueError as exc:
            assert "still alive" in str(exc)
        else:
            raise AssertionError("Live owned GUI was duplicated")
        before_crash = service.inspect_gui_session(sid)
        atomic_json(root / "before-crash.json", before_crash)
        # Fault injection is restricted to the exact process created by this test.
        assert alive(before_crash["process"]) and process_identity(before_crash["process"]["pid"]) == before_crash["process"]
        process = psutil.Process(before_crash["process"]["pid"])
        process.terminate()
        process.wait(timeout=15)
        old_sid = sid
        restarted = checked("restart-after-exit", Service(service.settings).restart_gui_session(old_sid))
        sid = restarted["session_id"]
        owned.append(sid)
        assert native_nodes() == saved
        reused = checked("repeat-restart", Service(service.settings).restart_gui_session(old_sid))
        assert reused["session_id"] == sid and reused["reused"]
        atomic_json(root / "acceptance.json", dict(status="succeeded", checks=checks,
                    checkpoint_unchanged=True, live_duplicate_refused=True,
                    scope="Visible4.13.4 typed-kernel late completion; uncertain native-command transaction blocked from checkpointing and explicitly restored; exact owned-process termination then saved-model restart through a new Service object. No claim of arbitrary GUI view/selection/macro restoration."))
    finally:
        for ident in owned:
            atomic_json(root / ("closed-"+ident+".json"), service.close_gui_session(ident, save_checkpoint=False))
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    print(accept(args.workspace, args.executable))
