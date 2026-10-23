# Q03: six-component stress field extraction

extract_field(quantity="stress") now uses the shared lasso_backend.field and shared field exporter
to emit one CSV/NPZ row per user element with sxx, syy, szz, sxy, syz, szx. Part filters, 1-based
public states and Q04 deletion masks apply to the whole tensor. Explicit units are required and
not converted. Metadata carries components, state/time, backend, mask, raw coordinate-frame scope
and either the stored-point mean or a chosen 1-based stored point. Large tensors stay in artifacts;
the MCP response holds shape, per-component extrema and at most 20 preview rows.

native_check=true calls the existing native SCL field exporter and compares the independently
written CSV by every returned user ID, state/time and component. The native selector is an independent
explicit parameter, never inferred from the reader slot. Means of multiple points, more than 1000
comparison entities and unverified solid native points remain explicit refusals. CSV/NPZ output
verification uses the shared read_field; no parallel result reader/math implementation was added.

Six initial feature regressions fail against clean main c0a4549; the initial red attempt before
creating its scratch parent failed in pytest setup and is not counted as a code regression.
Related Python tests pass 73 cases with two external-corpus skips. A new 1000-ID source bound
test addresses the actual native compilation failure: OR conditions now occupy bounded SCL lines,
without dropping IDs, with a fresh keep flag per entity.

Native evidence: [first run](r413a-batch-report.md) (3 passed, 3 failed),
[final 4.13](r413b-batch-report.md) and [4.10](r410a-batch-report.md) (8 passed each).
Each final run includes six positive exports and two deliberately wrong shell slot/layer pairs
that return failed without verified artifacts. The first shell assumptions (slot 3=MID, slot 1=INNER)
were wrong for this file; observed stored order is MID=1, INNER=2, OUTER=5. No universal map was added.
See [structured provenance and checks](evidence.json).

Q03 remains partial for the wider legacy backend/sampling surface: the new tensor path is LASSO
with optional native validation, not a native-primary extraction backend, and does not map arbitrary
shell layer names or transform local/material coordinate systems. Existing scalar calls stay compatible.
Raw logs, CSV/NPZ contents, binary inputs and local paths remain outside Git.

Final related Python coverage is 78 passed / 2 external-corpus skips. After clean native revision
1be3f45, product-source changes only clarify the extract_field module docstring and the JobResult
scope wording (sampling is explicit metadata, not always a mean). No native script, reader, mask,
numeric comparison or exporter behavior changed after these native runs; the runtime revision is
recorded as executed rather than relabeled as the final PR head.
