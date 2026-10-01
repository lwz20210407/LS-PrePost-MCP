# Model size and verification scope

The20,000 node/element limit is an implementation bound on **legacy full-mesh snapshots and tools that depend on them**. It is not an LS-PrePost limit, a license restriction, or a limit on all MCP operations. Increasing the constant would still serialize complete coordinates/connectivity for each operation and would not solve the design problem.

| Route | Current behavior |
|---|---|
| `inspect_gui_mesh` without `entity_type` | Legacy full snapshot; rejects if either global node/element count exceeds20,000 |
| `inspect_gui_mesh(entity_type="node" or "shell" or "solid" or "beam", offset=..., limit=...)` | Native registry pages of1–5,000 entities; only selected node-coordinate slices or selected element connectivity are materialized. No20,000 global check. Offset is zero-based, IDs are user IDs, returned `next_offset=null` marks completion |
| General selection, merge, normals, renumbering, mesh-quality/edit tools using full snapshots | Still bounded by the legacy snapshot. Paging alone does not certify these operations on large models |
| Named native field CSV/PNG | Separate SCL path; no whole-mesh JSON; resource guards and semantic scope in NATIVE_MEDIA.md |

Pages use native registry order, not sorted user IDs. Node coordinates are reference coordinates, including for a d3plot. They are read-only observations, not alive-only selection. The managed lock protects each native request, but does not create a snapshot across separate page calls or prevent a human from editing the GUI. Do not use unchecked pages as edit-before/edit-after proof. Thick-shell connectivity paging is not yet exposed.

Windows4.13.4 native acceptance on a private solid-only model exceeding300,000elements passed first/middle/last node and element pages in both keyword and result models, matching IDs/reference coordinates/connectivity. Full-domain native Mises CSV/PNG and representative independent six-component checks passed; source hashes were unchanged. This is a real private-model test, not a synthetic100,000-entity edit benchmark. No fixture, local path, field value or image is distributed.

Next under architecture itemT03: scoped identity/selection, incremental before/after geometry and topology verification, then representative edit→save→native-reopen acceptance. The overall large-model editing gap remains open. Opt-in generic driver: `tools/run_mesh_page_acceptance.py --workspace <private-output> --executable <lspp> --keyword <input.k> --result <d3plot>`.
