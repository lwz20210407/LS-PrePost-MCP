# Correlated completion and saved-model recovery

Recovery never resubmits the timed-out command. Native completion, host-side
transaction verification and workflow quality gates are different events.

## Zero-entity keyword baselines

Keyword recordings now save a native checkpoint even when nodes/elements are zero. An empty mesh can still contain materials or controls; reopening its saved file preserves those cards. The recorded `initial_expected_empty` boolean survives parameterization and requires an actual keyword initial_model during static preflight.

`open_in_gui_session` and explicit `restore_gui_checkpoint` accept `expected_empty=True` for this declared zero-node/zero-element case. Source identity, native log errors, integral counts and the no-multistate-keyword guard still apply. Default opens continue to reject unexpected zero-node loads. The same contract is checked for late replies. Start a new GUI session for the updated embedded bridge.

Visible4.13.4 acceptance: a material-only baseline, create nodes101/103, add an unrecorded node999, then replay with nodes201/205. The active model contains only the replay nodes, while the material card and original file remain unchanged. Existing engineering curve recording/replay was rerun successfully (20→10MPa after area change, previous plot data preserved). This is active-model restoration, not proof that every resident model was unloaded. Old recordings without a saved baseline are not automatically repaired; record a new baseline for reproducible modeling.

### Saved-file expectations during process restart

New successful keyword opens/exports retain an owned `.lspp-context.json` sidecar with the file SHA256/size and native node/element counts. `restart_gui_session` still chooses only the session's trusted checkpoint/staged source; it validates the input boundary and the sidecar owner/hash before starting a replacement. For verified zero-entity files it passes the explicit empty expectation to the new session. A changed file or foreign context is rejected. A legacy file without this evidence retains the nonempty rule; no empty-model guess is made by scanning text. The sidecar records inventory, not solver validity or completion of a parent workflow gate.

Visible4.13.4 controlled-exit acceptance: save a material-only zero-entity checkpoint, create an unsaved8-node/1-solid mesh, terminate only the owned idle test process, and recover the zero-entity file/material. Repeated restart returns the same child. Save node201 in that child, terminate it, then restart the child: node201 and its coordinates return. Restarting the old parent after its child exited is rejected, preventing restoration of an older checkpoint. Original input remains unchanged. Driver: `tools/run_checkpoint_context_acceptance.py`. This verifies two controlled idle-process exits; crashes during execution and full selection/view/model-list restoration remain separate.

## Reset: undo file versus current restart source

`reset_gui_session(save_checkpoint=True)` now saves keyword cards even when there is no mesh. The prior `last_checkpoint` remains the default explicit undo target; a separate `reset_recovery_source` points to the verified new empty keyword. Restart uses this new baseline while the staged model and rollback pointer still match the reset. A newer checkpoint or another model load supersedes it. Unsaved raw edits do not make restart silently load the pre-reset model. Late reset completion establishes the same source separation, and the pre-reset checkpoint is persisted before submitting reset so a timeout cannot discard it.

`restore_gui_checkpoint(expected_empty=None)` auto-detects the empty expectation only for the same trusted checkpoint, with matching owner/hash. Explicit True/False remain available; an explicit other file does not borrow the trusted file's expectation. Restoring the old checkpoint clears the reset markers. Recording also retains the requested save_checkpoint option.

Visible4.13.4 acceptance: reset a96-node model, close/restart and obtain0nodes; import another material into a material-only model, reset and explicitly restore both material blocks; reset again, save node301, close/restart and recover301. Source files remain unchanged. Driver: `tools/run_reset_recovery_acceptance.py`. This verifies active-model recovery, not unloading every resident model or in-flight GUI crash handling.

## Late replies

`recover_gui_session` reads the saved request/contract and matching `complete.json`.
Both request and response IDs must match the pending request. Artifacts must
remain inside its owned directory and pass their declared validation. Invalid
or missing evidence retains the pending request and the trusted checkpoint.

- A pure read, or a native kernel that validates its own result before publishing
  completion, can restore readiness when the session was previously ready.
- Native-command plus readback transactions still require their host-side
  comparisons. A late readback alone leaves the session `uncertain`; recovery
  records `completed_unverified` in `recovery.json` and does not promote the
  output to the trusted checkpoint.
- An explicit completed model reopen/reset can replace uncertainty. It updates
  model identity and clears old selection buffers/fringe caches. Switching to a
  result model clears the old keyword checkpoint; source provenance is restored
  from the staging manifest.
- An exited native process remains exited even if a completion file exists.
  Reconciliation does not manufacture a live ready session.

Potentially changed keyword models retain `dirty=true`. Checkpoint export and
reset-with-checkpoint reject uncertain sessions, including the generic
`gui_session_action("export_keyword")` route. Use an explicit trusted checkpoint
restore, or an explicit discard/reset, before continuing; an unverified output
must not silently replace the recovery baseline. Parent workflow gates and
postconditions are not automatically declared passed by this operation.

## Exited-process restart

`restart_gui_session` refuses a still-live original process. It serializes restart
of the old session, persists the replacement session ID, opens its saved keyword
checkpoint or staged result source, and shows the new owned GUI maximized.
Repeating the call returns the same live replacement without launching another
window or reopening its model. Interrupted restoration returns an uncertain
existing replacement. If that replacement has itself exited, restart the child
session to retain its latest checkpoint rather than returning to an ancestor's
older model.

This restores the saved model/source, **not** all arbitrary GUI selections,
camera state, manual edits or opaque macro internals. Full workflow continuation
from every possible interruption boundary remains separate unfinished work.

## Native evidence

`tools/run_session_recovery_acceptance.py` uses only generated geometry and
processes created by the test. It deliberately uses a tiny host observation
timeout after actual native submission, then reconstructs a fresh `Service`
object from the same workspace. The recorded native result is reconciled;
nothing is resubmitted.

Visible maximized LS-PrePost4.13.4 passed:

1. A late native box creation recovers its validated checkpoint and eight nodes.
2. A native node translation executes exactly once, but its absent host
   verification leaves the session uncertain and blocks checkpoint replacement.
3. Explicit checkpoint reopening restores the exact original coordinates.
4. A subsequent validated edit is saved. Terminating only the exact owned
   PID/executable/creation-time identity simulates an abrupt native exit.
5. A new service object restarts the saved model with identical node data;
   repeating restart returns the same replacement GUI.

Evidence: `gui-recovery-36d892f4e9374302833ca138b561133c` in the dated local task
directory. Negative unit cases cover invalid artifacts, wrong/missing pending
identity, unverified command readback, exited-process status, stale model cache
cleanup and replacement reuse. A fresh service object is evidence of disk-based
reconciliation, not an operating-system MCP-server crash or long-uptime test.
