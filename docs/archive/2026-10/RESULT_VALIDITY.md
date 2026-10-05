# Per-state physical deletion and retained extrema

The four field/stress exporters (`extract_native_fields`, `extract_native_stress`,
`extract_d3plot_field`, `extract_d3plot_stress`) accept `validity_policy`:

- `raw` retains the existing stored population, for backward compatibility.
  Its extrema must not be described as alive-only.
- `alive` requires a recorded physical element-deletion table. Missing masks,
  ambiguous/adaptive mappings and unsupported domains fail explicitly. It
  excludes deleted rows before finite-value checks, tensor invariants and extrema.

`inspect_result_validity(path, element_type, states, element_ids=None)` returns
per-state requested/domain counts and a validated NPZ containing user IDs,
1-based states, times and a Boolean state-by-entity mask. The optional results
extra (LASSO 2.0.4) is required. This is explicitly a reader operation.

## Meaning and alignment

The [official binary database description](https://lsdyna.ansys.com/wp-content/uploads/2026/08/ls-dyna_database_Jan2018.pdf),
MDLOPT=2 table (printed page 44), records an element material number or zero
when deleted. Positive values including 2 and 3 mean present; checking only
`== 1` is incorrect. Map by element domain, saved state and **user ID**, rather
than stress-array position: rigid-shell omission can change stress populations.
MDLOPT=1 nodal visibility is a different contract. SPH, adaptive mesh epochs,
material damage criteria and arbitrary history-slot interpretations are outside
this implementation.

Public mixed-solid/shell regression subsequently found a separate native SDK
sampling defect: on 4.13.4, requesting solid point 8 through the scalar-array
SCL getter returned the point-1 tensor unchanged. Scalar getter, application-internal
Python `get_data`, `sintpt 8` and legacy reader-mode probes did not resolve it. Consequently native solid selectors 2..8
now reject before dispatch, including native image requests using the shared
sampling contract. Point 1 and default remain distinct labelled selections;
reader stored-point extraction remains available only when explicitly selected.
Do not silently relabel point 1 or switch backend. A validated native adapter
for the remaining solid points is still required.

On the same public mixed fixture, native shell selectors 1, 3 and 5 exactly
matched their six stored stress components at the last state for the sampled
element; this is bounded evidence, not all-shell/material/frame certification.
Local probe: `native-point-probe-4d852c99f6ae4ffe8a42f2aa85b4b62c`.

## Known-truth shell deletion acceptance

`tools/synthetic_shell_result.py` constructs an original three-shell binary
fixture with sparse node/element/part IDs, three stored layers and three states.
It is **not solver output** and makes no material-failure or physical-validation
claim. The LASSO writer is used only to prepare test input in a fresh directory;
all subsequent native checks run in real visible maximized LS-PrePost 4.13.4.
The generated binary is read back and compared array-for-array before use.

`tools/run_shell_validity_acceptance.py` passed the combined workflow:

- Raw native tensors retain nine state/entity rows; physical filtering retains
  six, with exact state/user-ID membership and the known layer-2 stresses.
- Present shell counts are3/2/1. Deleting the high-stress shell reduces the
  retained maximum from2000Pa to60Pa, within native floating-point tolerance.
- A requested all-deleted subset returns an empty CSV/null extrema. Rendering
  a part containing only deleted shells fails instead of producing a zero plot.
- Static PNG/CSV and the per-state native PNG/FFmpeg movie agree on counts3/2/1.
  The generated input fingerprint is unchanged and the owned GUI is closed.

Evidence: `shell-validity-5b10f11303034e8fb0336e07582fcf64` in the dated task
directory. This complements the public solid solver-result case and the public
mixed shell/solid integration-point comparison; those evidence types are not
interchangeable. Standard shell/solid MDLOPT2 deletion now meets the bounded
first-release gate; SPH, adaptive mesh epochs, arbitrary damage variables,
beam/tshell runtime coverage, old builds and headless execution remain outside
that native acceptance.

Physical deletion, display Blank, rigid material and variable availability are
separate properties. A present entity with no stress record is not assigned
zero stress. Unsupported/missing variables still fail. A request containing only
deleted entities succeeds with a header-only CSV, `row_count=0`, explicit
`empty_reason=all_requested_entities_deleted`, and null extrema.

## Native route and evidence

Native values still come from LS-PrePost SCL. `alive` adds an explicitly labelled
LASSO physical mask; it does not replace native values with reader values. In a
GUI workflow, omit `path`, use the current owned result session and request
`validity_policy="alive"`. The native model directory must match the staged
mask source, saved times must agree, and state/selection/geometry/part visibility
and element display flags must be preserved. The field context now uses a
streaming mesh digest with selected IDs instead of the old whole-model 20,000
snapshot. Export/selection request limits still apply.

Visible maximized LS-PrePost 4.13.4 passed the opt-in
`tools/run_result_validity_acceptance.py` on the public Ansys projectile family,
states 1 and 16: solid MDLOPT2 counts, deleted-row removal, all-deleted output,
retaining a physically present but blanked element, recording/replay and a
native SCL check at the reader's retained maximum. Original file fingerprints
were unchanged. Evidence is local under
`native-validity-acceptance-7d24d895523e47a6bdb86597703227cf` in the dated task
directory. Unit labels in that check are unresolved source units, not MPa.

A separate native probe demonstrated that unblanking can leave all 5,664
solid display flags active while the saved last-state table marks 614 deleted.
Display flags therefore cannot supply the physical deletion mask.

Synthetic tests also cover sparse IDs, positive material codes, reactivation,
rigid-shell compressed records, deleted NaNs, empty extrema, time mismatch and
adaptive-family rejection. Shell/tshell/beam real deletion cases, old builds
and headless modes still need their own acceptance.

## Static native PNG/CSV integration

`render_gui_field(..., validity_policy="alive")` now applies the explicit
physical mask for standard solid/shell fields after setting the requested parts
and state. It checks native/reader user-ID registries, hides deleted elements
with the existing native Blank route, verifies geometry and display flags, and
requires the CSV IDs to match the verified visible population exactly. Values
remain SCL-derived; provenance identifies the LASSO mask separately. The title
policy and default MinMax presentation averaging remain unchanged. Legacy `raw`
rendering retains its prior behavior.

Deleted/unselected buffer slots are neutralized before custom-fringe transfer;
only retained values must be finite. Color bounds are calculated from the
retained CSV. The public solid last-state check retained 5,050 of 5,664 elements
and agreed with the separately extracted effective-stress range. A native pixel
probe changed excluded buffer values from zero to 1e10, then reapplied identical
camera, color bounds and MinMax settings: the PNG pixels were unchanged. This
is evidence for this build/fixture, not an independent implementation of the
native averaging algorithm. Initial probe evidence and corrected presentation
comparison are retained separately; omitted range reapplication is not a valid
pixel comparison.

The rendering workflow intentionally retains the requested scene and physical
Blank state. An all-deleted visible scope rejects with no meaningful PNG rather
than manufacturing a zero-stress plot. Existing visibility-transition limits
still apply (20,000 changed/complement explicit IDs), independently of the
one-million-entity readback limit. Shell physical-fringe runtime verification
uses the explicitly constructed fixture above; other builds and headless modes
remain outstanding.

Combined acceptance passed 17 recorded checks under visible maximized 4.13.4:
`native-validity-acceptance-ea4083ae005947babc82efee5e11edde` in the dated task
directory. The first render preserves one manually blanked present element
(5,049 visible); explicitly showing that element restores the 5,050-element
physical scope. The replay output is the reference for the zero-pixel-difference
test. Source-family fingerprints were unchanged and the owned GUI was closed.
The final fitted image was visually reviewed. Local unit/integration suite:
480 passed; this count does not imply native certification for every tool.

## Remaining integration

The original native Movie-command interface still rejects physical-fringe
animations. The explicit [per-state field animation](FIELD_MOVIES.md) route now
renders each verified physical scope in LS-PrePost and encodes its PNGs using
FFmpeg; it has solid4.13.4 frame-count, deletion and parameter-replay evidence.
Ordinary previously validated raw-field native movies retain their scope.
Native layer averaging and reader stored integration points are not implicitly
equated. The release validity gate is passed for its standard shell/solid scope. See
[public fixtures](PUBLIC_TEST_CORPUS.md) for the expanded regression inputs.
