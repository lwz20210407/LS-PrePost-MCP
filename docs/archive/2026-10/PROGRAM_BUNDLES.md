# Declared native script bundles and GUI execution

The existing program and macro tools accept optional
`dependencies=[{"path":"<allowed source>","name":"lib/helper.py"}, ...]`.
Preparation copies each explicitly supplied file, including empty package
initializers, into its declared relative location. It does not discover imports,
download packages, copy an entire workspace or execute retrieved source.

## Identity and layout

- Up to100 declared dependency files and64MiB combined content; the entry remains
  bounded to1MiB. Model/result inputs use their existing separate staging route.
- Names must be portable relative paths; traversal, Windows reserved aliases,
  case-insensitive duplicates, file/directory collisions, and collisions with
  controller or output files are rejected.
- Entry numeric substitution remains unchanged. Dependency bytes are frozen
  verbatim; pass parameters from the entry to a helper instead of assuming all
  dependency source is templated.
- With dependencies, `data.sha256` identifies the entry, dependency names/sizes/
  hashes and declared output/count contract. `source_sha256` is the entry alone.
  Existing single-file execution hashes retain their former meaning. Pass the
  returned execution hash to `execute_native_program`.
- Files are checked before execution and declared dependency bytes are checked
  again afterwards. Changing original files after preparation does not change
  the frozen bundle; changing prepared assets causes rejection.

Literal `open/openc command`, `runpython` and `runscript` references in reachable
cfile content must use declared job-root-relative names. Nested command files
are followed regardless of their extension; cycles and depth above16 reject.
This is important because4.13.4 can silently continue after a missing child
cfile and successfully save the parent output. Native logs alone did not detect
that failure. Dynamic Python imports, arbitrary SCL include dialects, runtime
path changes and every possible command grammar are **not** statically resolved.

## Current GUI and macro route

`execute_native_program(..., session_id=...)` and
`run_native_macro(..., session_id=...)` now use the current owned, ready GUI.
Omit `model`: open/reset the session with the existing dedicated tools first.
A GUI workflow routes these actions to its session automatically. Omitting a
session retains the isolated-process route; the two execution modes are explicit.

The GUI route preserves a keyword checkpoint before executing on a nonempty
model, stages code/assets in a fresh job and correlates completion through the
existing bridge. It checks native diagnostics, Python exception reports,
declared files/counts, dependency identity and coarse model-directory coherence.
Native keyword save can change `model_directory` from a filename to a directory,
so the comparison baseline is refreshed after the controller's checkpoint.
Directory coherence is not proof of arbitrary script semantics or model identity.

Scripts run with normal LS-PrePost permissions; this is not a security sandbox.
Do not replace/close the owned model or change global runtime configuration from
these GUI programs. Failure leaves uncertainty and retains the prior checkpoint.
Successful raw programs mark keyword state dirty and invalidate cached selections
and managed fringe certainty. Checkpoint after recording before replaying a
baseline that would replace the current model; do not silently discard it.

The Python wrapper temporarily adds the job root to its module path, isolates
declared top-level module names and removes modules loaded from the job after
execution, restoring previous declared modules/path/cwd. This prevents stale
helpers between bundles. It is not complete interpreter or C++-SDK isolation.

`create_native_macro` captures dependency assets beside `macro.json`; later
changes to originals do not alter the macro. GUI recording stores a single
parameterized `run_native_macro` operation, not its internal preparation or
child-script steps. Global LS-PrePost macro-menu/shortcut installation and
arbitrary mouse recording remain separate unfinished capabilities.

## Verified evidence

`tools/run_program_bundle_acceptance.py` verifies visible maximized4.13.4:

1. Nested cfiles build8nodes/1solid and save a new keyword output; the prepared single-command GUI route separately saves a verified keyword.
2. SCL reads a declared data file with `fgets`/`atoi` and writes the checked sum.
   `fscanf` was unavailable in this build and is not presented as supported.
3. Two bundles using the same Python module name return7 then19 without stale
   import reuse.
4. A package/data macro preserves its captured base5 after the original changes
   to99; recording and changing its factor2→4 produces10→20.

Native evidence: `bundle-test-1ad8b678ba39435a97bec0d1e865872a` in the dated task
directory. Failure probes and corrected runs are retained. Batch behavior has
unit-level staging/identity checks; old-build and headless **bundle** acceptance
are not inherited from earlier single-file program tests. Generated native
inputs, outputs and logs remain outside Git.

The final local unit/integration suite passed515 tests. This does not extend the native matrix to other builds or modes.
