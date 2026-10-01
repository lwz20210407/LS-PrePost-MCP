# Model size and verification scope

The20,000 node/element limit is an implementation bound on **legacy full-mesh snapshots and tools that depend on them**. It is not an LS-PrePost limit, a license restriction, or a limit on all MCP operations. Increasing the constant would still serialize complete coordinates/connectivity for each operation and would not solve the design problem.

| Route | Current behavior |
|---|---|
| `inspect_gui_mesh` without `entity_type` | Legacy full snapshot; rejects if either global node/element count exceeds20,000 |
| `inspect_gui_mesh(entity_type="node" or "shell" or "solid" or "beam", offset=..., limit=...)` | Native registry pages of1–5,000 entities; only selected node-coordinate slices or selected element connectivity are materialized. No20,000 global check. Offset is zero-based, IDs are user IDs, returned `next_offset=null` marks completion |
| Explicit `select_gui_entities` IDs with `scope=all`, `invert=false`; explicit set combinations and saved buffers | Complete geometry fingerprints and exact selected-ID readback; no global20,000 bound. Explicit requested-ID sets remain bounded to20,000 |
| `translate_gui_nodes`, `rotate_gui_nodes`, `set_gui_node_coordinates` | Streamed before/after geometry fingerprints plus requested coordinates, native checkpoints; no global20,000 bound. Translation/rotation accept up to10,000 explicit nodes; absolute corrections up to100 |
| Part-filter/region/inverted selection, merge, normals, renumbering, mesh-quality/edit tools still using full snapshots | Remain bounded by the legacy snapshot; those migrations are not complete |
| Named native field CSV/PNG | Separate SCL path; no whole-mesh JSON; resource guards and semantic scope in NATIVE_MEDIA.md |

Pages use native registry order, not sorted user IDs. Node coordinates are reference coordinates, including for a d3plot. They are read-only observations, not alive-only selection. The managed lock protects each native request, but does not create a snapshot across separate page calls or prevent a human from editing the GUI. Do not use unchecked pages as edit-before/edit-after proof. Thick-shell connectivity paging is not yet exposed.

Windows4.13.4 native acceptance on a private solid-only model exceeding300,000elements passed first/middle/last node and element pages in both keyword and result models, matching IDs/reference coordinates/connectivity. Full-domain native Mises CSV/PNG and representative independent six-component checks passed; source hashes were unchanged. This is a real private-model test, not a synthetic100,000-entity edit benchmark. No fixture, local path, field value or image is distributed.

Scoped edit verification now scans every native reference coordinate, element connectivity and part membership. SHA-256 digests cover full node IDs/topology and every unrequested coordinate; requested nodes are checked numerically against the transform/absolute targets. Native registry order is part of the fingerprint, so a reordered registry fails conservatively. One element-domain ID array is materialized to avoid transient SDK-buffer reuse; unrequested coordinates/connectivity are not retained or serialized. This is O(model size) verification, not constant-time or sample-only verification. It does not establish mesh quality, all keyword references or material/load-axis semantics. Start a fresh owned session for the updated embedded bridge; old buffer signatures need resaving.

Windows4.13.4 passed explicit node selection→translation→rotation→absolute-coordinate correction→native save/reopen on both a native-generated100,000-shell/100,651-node plate and a private solid model over300,000elements. All unrequested coordinates, connectivity and part membership were checked, with native export precision normalized before the reopen comparison. Private input hashes remained unchanged. This verifies the synthetic scale target for these operations, not every mesh tool. Generic driver: `tools/run_scoped_mesh_acceptance.py --workspace <private-output> --executable <lspp> [--source <private.k>]`.

Architecture itemT03 remains open for broader part/region selection and the remaining snapshot-based edits/checks. Paged keyword/result plus native field driver: `tools/run_mesh_page_acceptance.py --workspace <private-output> --executable <lspp> --keyword <input.k> --result <d3plot>`.
