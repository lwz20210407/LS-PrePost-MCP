# DPF–LS-DYNA integration

Status: optional adapter implemented, with synthetic semantics/dispatch tests. On2026-10-03 the local diagnostic found PyDPF-Core0.16.1 but no discoverable DPF Server. **No real DPF extraction, operator compatibility or numerical cross-backend acceptance is claimed.** LS-PrePost remains the primary native GUI/command/SCL/Python backend; DPF outputs are marked `backend=dpf` and `ls_prepost_native=false`.

## Official examples reviewed and adopted

The supplied [LS-DYNA gallery](https://dpf.docs.pyansys.com/version/stable/examples/14-lsdyna/index.html) has three examples. They are different workflows, not a guarantee that every operator is available on every file.

| Official source | Adopted behavior | Remaining work |
|---|---|---|
| [Result providers](https://dpf.docs.pyansys.com/version/stable/examples/14-lsdyna/00-lsdyna_operators.html) | d3plot/binout source keys; optional actunits; runtime result discovery; labelled part/contact histories; each field's own time IDs | Real Server acceptance, other database branches and MPP/restart groups |
| [Beam manipulation](https://dpf.docs.pyansys.com/version/stable/examples/14-lsdyna/01-lsdyna_beam.html) | Eleven typed beam scalar results; local-direction metadata; separate signed minimum/maximum and absolute-peak witnesses | Real beam data, local/global transformations, deformed multi-scene views and full-history workflows |
| [Element erosion](https://dpf.docs.pyansys.com/version/stable/examples/14-lsdyna/02-lsdyna_erosion.html) | Explicit binary active/eroded flag; per-field counts; physical validity distinct from display visibility | Real eroding case, surviving connectivity/sub-mesh, nodal transpose, deformation and native visual comparison |

Binout histories retain `part`, `interface`, `idtype` and all other returned labels. Master and slave contact forces remain separate. Branch time scoping is resolved by ID against the result container's time support, never by row position against a global axis. Missing requested branch sets fail rather than receiving zero values. Beam absolute peaks retain their signed values and element/time witnesses; they are not labelled maximum positive stress. The erosion adapter requires exact0/1 flags and does not infer flags for files lacking them.

## Current interfaces and contracts

- `probe_dpf_runtime`: isolated discovery of client/version/server root, without starting DPF. `status=succeeded` means the probe ran; inspect `ready_for_runtime_attempt`. A discovered directory is not a validated runtime.
- `inspect_dpf_results(path, file_type, actunits=None)`: source availability and time-set IDs using a local owned Server. Each result distinguishes source availability from this adapter's supported export list.
- `export_dpf_result(path, file_type, result, units, states=None, entity_ids=None, label_filter=None, component=None, actunits=None)`: labelled long CSV, shared `FieldSpec`, per-label semantics and extrema. `component` is zero-based. Select one label/entity/component history before feeding `time,value` into engineering curves or native XYPlot; multiple histories must not be treated as a single curve.

Supported initial results are nodal displacement/velocity/acceleration, the documented beam scalars, erosion flags, selected global/part energies and mass, and interface contact-force vectors. Inspect the typed list in `dpf_fields.py`; discovered stress tensors/history slots are **not** automatically exported. Native `Nodal`, `Elemental` or `TimeFreq_steps` locations are required. Unexpected averaging locations, multi-point payloads, missing entities and nonfinite values fail. No arbitrary operator/script execution is exposed.

CSV columns preserve result, field index, full labels, location, DPF set ID, time, entity ID, component, value, reported unit and time unit. Time-history mesh-entity IDs are blank; part/interface IDs live in labels. Shared contracts distinguish DPF source-location sampling from LS-PrePost layer/point selectors and LASSO slots. Cross-backend state equivalence is not inferred. `units` is a caller declaration; no unit conversion or dimensional certification occurs. Reported DPF units can remain empty if unavailable.

Resource bounds:2GiB staged input,500,000 scalar output rows,512 labelled fields; up to2,000 requested sets and20,000 explicit entity IDs. Full-domain spatial exports use one explicit state. Input copies and logs stay in the private job directory. Interior numbered d3plot gaps and recognized binout shard groups are rejected; a missing final continuation cannot be inferred from filenames alone. Unsupported variants must not be called complete datasets.

## Installation conditions

1. Install the optional client with `pip install 'ls-prepost-mcp[dpf]'`. This pins `ansys-dpf-core==0.16.1`; it does not install Server, LS-PrePost or a solver.
2. Supply a compatible local Windows/Linux DPF Server installation. The adapter requires Server7.1+ for this client, and8.0+ for beam/erosion exports. Prefer a supported Ansys2024R2+ installation and check the current [compatibility table](https://dpf.docs.pyansys.com/version/stable/getting_started/compatibility.html). Standalone LS-PrePost4.13 is not a DPF Server installation.
3. Set `LSPP_DPF_PATH` to the installation root, or use PyDPF's documented local discovery. Run the probe before extraction. Remote endpoints, Docker and PyPIM fallback are disabled; this adapter requests local in-process execution, not an insecure gRPC workaround.
4. Follow the vendor's [licensing conditions](https://dpf.docs.pyansys.com/version/stable/getting_started/licensing.html). An Ansys installation and standalone Server have different agreement requirements. The adapter never accepts an agreement, changes license configuration or downloads a Server. It requests the Entry context, preventing license checkout; operators needing licensed transformations may still fail. Server binaries, license files and example result datasets are not redistributed.

Next acceptance gate: provision an authorized compatible Server, validate each source/result family against official/synthetic truth and representative native LS-PrePost outputs, then promote only the proven rows of the capability matrix. Tests with fake field objects prove parsing/error handling, not the vendor reader.
