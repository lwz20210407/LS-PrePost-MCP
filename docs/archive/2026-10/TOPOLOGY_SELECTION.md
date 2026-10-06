# Native shell adjacency and feature propagation

`select_gui_shell_topology(session_id, seed_ids, mode="propagate", ...)` adds
two distinct native operations for **currently visible keyword-model shells**:

- `mode="adjacent", rings=1`: shared-node adjacency, including vertex-only
  contact. Each native `genselect adjacent` adds one ring. Range1..100; default1.
- `mode="propagate", feature_angle=30`: shared-edge propagation with a local
  unoriented face-normal angle. Default30degrees; supported interval(0,180].
  Reversed shell normals do not stop a smooth continuation. The comparison is
  between neighboring faces, not every face and the initial seed.

Do not provide an angle for adjacency or a ring count for propagation: these
are different operations, not interchangeable filters. Seed IDs are user IDs.
Hidden parts and Blank elements form boundaries; a hidden or unknown seed is
rejected before selection commands and leaves the session usable.

The adapter issues actual `genselect propagate on/off`,
`genselect propagate featang`, and `genselect adjacent` commands. An independent
graph built from native connectivity/reference coordinates checks the exact
selected IDs. Full geometry/part-membership digests, current state, part flags
and element display flags must remain unchanged. An older already-running
bridge that lacks the query contract fails explicitly; start a new owned session.

Scope: standard Tri3/Quad4; up to1,000 seeds and a one-million-visible-shell/
selected-ID resource budget. The reference graph materializes shell connectivity
and needed coordinates, so this is O(model/scope) work, not constant memory or
a measured million-shell performance certificate. Deformed-result propagation,
adaptive constraints, arbitrary high-order/nonmanifold behavior, and whole
hidden-model propagation are not certified. The operation leaves propagation,
adaptive propagation and3dsurf options off, with the requested feature angle;
it does not claim to restore every selection-panel preference.

## End-to-end native evidence

Visible maximized LS-PrePost4.13.4 passed
`tools/run_topology_selection_acceptance.py` on original folded Tri3/Quad4 data:

1. One/two shared-node rings include the intended vertex-touching component.
2. Feature angle30 excludes the60degree fold;80 crosses it. A separate30+30degree
   chain probe confirmed local propagation rather than a seed-global angle.
3. Part hiding and Blank block the expected path; hidden-seed rejection does not
   change session readiness. Reversing a shell normal does not change the
   propagated set under the verified unoriented rule.
4. Selection feeds `create_gui_segment_set` and native pressure creation.
   Recording then changing angle30→80 grows the loaded Segment set3→4 faces;
   saved keyword reopening preserves the set. No solver/pressure-response claim.

Local evidence: `topology-3f19c35bf5214771accd2772fba18feb` in the dated task
directory. A legacy native snapshot regression was also fixed: the beam-safe
DataCenter proxy now forwards positional node-type arguments while continuing
to intercept the known-unsafe beam connectivity getter.

The basic connection-editing increment is now published as
[`replace_gui_node`](NODE_REPLACEMENT.md): native directed replacement plus
supported Node/Segment/SPC reference repair and native reopen. This does not
complete arbitrary connection editing or remove that operation's snapshot bound.
