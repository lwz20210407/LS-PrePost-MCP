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

## Remaining integration

This change does not add physical masking to `render_gui_field` or animation,
and does not certify numerical equivalence between native layer averaging and
reader stored integration points. The release gate for complete validity and
visual/numeric agreement remains partial. See [public fixtures](PUBLIC_TEST_CORPUS.md)
for the expanded regression inputs.
