# Node replacement and reference repair

`replace_gui_node(session_id, source_node_id, target_node_id, units)` replaces one existing node with another in the current owned keyword GUI. Public IDs are user IDs. The target ID and coordinates survive; the source is removed. This extends WF-MESH / T05; it is not a general renumbering or duplicate-node algorithm.

## Execution and evidence

The native sequence is `elemedit replace clear`, `elemedit replace two SOURCE TARGET 2`, `elemedit replace accept`. On Windows LS-PrePost 4.13.4 the native operation updates mesh connectivity but does not reliably repair every node reference: Segment/SPC rows can still reference the deleted source and Node LIST sets can contain duplicate members.

The tool therefore reports its actual mixed execution route:

1. Export a fresh baseline and read the complete bounded mesh; inspect supported reference cards before editing.
2. Apply native Replace in the visible session; verify every surviving coordinate, every element connection and part membership.
3. Patch supported Node LIST, Segment and SPC_NODE references in a **new native-export copy**. Deduplicate Node LIST membership. Preserve SPC constraint IDs, titles and untouched native-export blocks.
4. Reopen that copy natively, restore part visibility, export again and verify reference membership, SPC DOFs/IDs, remaining NODE TC/RC attributes and unrelated keyword blocks.

This is not byte-preserving editing of the original deck: native export may normalize its representation. The input file is not overwritten. Selection is cleared; complete viewport/element Blank recovery is not certified. A failure after mutation leaves the session uncertain and retains the original baseline checkpoint; use explicit recovery rather than replaying an uncertain edit.

`tools/run_node_replacement_acceptance.py` passed 26 recorded checks on visible, maximized 4.13.4 with an original synthetic Tri3/Quad4 fixture and Hex8 box. Evidence includes changed topology propagation, Node/Segment/SPC repair, constraint-ID preservation, changed-target parameter replay, native reopen and unchanged source. Element collapse, Segment collapse, overlapping SPC constraints and unsupported direct-node load cases were rejected before mutation with the model unchanged.

## Current boundaries

- Requires the optional pinned PyDYNA dependency for reference schema inspection.
- Uses complete mesh snapshots, currently bounded to 20,000 nodes/elements. This operation has not inherited the larger scoped coordinate-edit path.
- Supported reference families: `SET_NODE_LIST[_TITLE]`, `SET_SEGMENT[_TITLE]`, `BOUNDARY_SPC_NODE[_ID]` and `BOUNDARY_SPC_SET[_ID]`. SPC_SET membership follows the repaired Node LIST; no new coordinate system or constraint meaning is inferred.
- Rejects collapse/unsupported geometry, duplicate Segment faces, conflicting target SPC DOFs, nonzero source/target NODE TC/RC and known unsupported direct-node references. Include/parameter models and other element families require separate implementations. Schema checks are not proof of all-keyword coverage.
- Geometry metrics are not a full native quality or physics certificate; follow with native quality/keyword checks and explicit gates. Shell orientation continuity and arbitrary automatic repair are separate capabilities.
- No solver response, large-model, 4.8/4.10 or headless certification is implied.

## Persistent export path correction

The acceptance flow also exercises reset → create Hex8 → export. LS-PrePost can retain an internal open folder different from Python's working directory. Relative `save keyword "model.k"` then places output outside the request directory. Persistent GUI dispatch now supplies a quoted absolute native Windows path; forward-slash drive paths were rejected by the tested native temporary-file naming logic. Other execution adapters retain their separately tested path rules.
