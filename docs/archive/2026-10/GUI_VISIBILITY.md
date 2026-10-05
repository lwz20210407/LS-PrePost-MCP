# Native entity visibility

## Selection interoperability (2026-10-03)

Selections now avoid `pall` and compare before/after native display-active descriptors. With any inactive elements, native whole/by-part selection is replaced with exact IDs: 4.13.4 by-part node selection was observed to omit nodes attached to Blank elements. The fallback accepts at most20,000 selected IDs and rejects larger requests before dispatch; this is not a model-size limit. All-active bulk selection retains its existing bound. Descriptor comparison occurs with original part flags; it is not an independent hidden-part erosion/Blank classification. Mixed-domain native acceptance additionally reveals/restores hidden parts and verifies their underlying flags.

`tools/run_selection_scene_acceptance.py` passed visible maximized4.13.4 mixed shell/solid/beam explicit, part, box, boolean, buffer, hidden-part and recorded display-setup+selection replay checks, preserving geometry/state and original fixture bytes. A keyword checkpoint does not store Blank flags: record explicit display setup if a replay must reconstruct that scene. Full checkpoint scene recovery remains open.

`set_gui_entity_visibility(session_id, entity_type, mode, entity_ids=None, capture=False)` supports standard shell, solid, beam or their combined `element` domain. Modes are hide, show, isolate, reverse and owned restore_last. IDs are user IDs. None selects the whole domain; an empty list is an explicit empty scope (therefore isolate with [] hides the whole domain). Unknown IDs or globally ambiguous cross-domain element IDs are rejected.

The tool checks all display-active flags, reference geometry/connectivity/membership, state and original part flags. This is a display contract, not physical alive/erosion classification. Original part visibility is restored; general selection is cleared and animation stopped. A restore belongs to the last verified change in that session/model/state and checks that touched flags have not changed externally. Opening/resetting a model invalidates that history. A failed or uncertain native request is not automatically replayed.

`pall` was observed to reset entity Blank state, so it is not used for baseline inspection. Only necessary hidden parts are temporarily revealed. Whole-type commands and the smaller selected/complement set avoid thousands of per-ID commands when isolating a small subset. The guard is one million readback records and 20,000 explicit transition IDs; it is not a model-size certification.

The application writes display flags in 40,960-byte chunks to `visibility.bin`. The `native_display_active_v1` descriptor records big-endian `!BqB` rows (type byte, signed 64-bit user ID, binary flag), count, byte length and SHA-256. Type bytes are 1=beam, 2=shell, 3=solid. The host validates location, count, identity uniqueness, flags and hash before using them. Geometry remains a streamed hash summary; this does not turn the entire model into a binary snapshot. The host still uses bounded dictionaries for exact comparison.

## Native beam connectivity workaround

A mixed synthetic mesh reproduced Windows heap corruption after native beam `element_connectivity` array reads, including the SCL-array experiment. The visible 4.13.4 workaround exports a fresh native keyword copy when beams are present and reads standard `*ELEMENT_BEAM` endpoints from that copy; no failing beam-array getter is called. Registry/count matching is mandatory. It costs a full native keyword export for each structural read on models containing beams, so no zero-copy or instant large-beam claim is made. Special beam variants and long-format records outside the checked parser remain unsupported. Non-beam pages avoid this export. Standalone batch beam connectivity is explicitly rejected until its safe route is validated.

Start a new protocol4 GUI session to use this bridge. This compatibility boundary is independent of the LS-PrePost version label.

## Verification

The maximized visible 4.13.4 driver `tools/run_gui_visibility_acceptance.py` passed 49 operations: synthetic solids, mixed shell/solid/beam state changes, combined isolation, stale-restore rejection, hidden part preservation, compact-interface creation, dynamic menu/prompt resolution, managed recording/replay, and representative private d3plot state operations. The private result family stayed unchanged. The smaller-complement isolation took approximately four seconds in that specific run; this is neither a general latency guarantee nor a million-element benchmark.

Preserved failed evidence includes `pall` resetting masks, per-ID command latency, an invalid New Session experiment, and the native connectivity heap faults. Node glyphs, special element types, deleted-element semantics and complete Blank-panel controls remain open. Private evidence and user-derived PNG/CSV are not distributed.
