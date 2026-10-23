# Q05: multi-entity history extraction

extract_history exposes node, solid/shell/tshell/beam, Part and global time histories through
the shared LASSO readers. d3plot supports all four semantic modes; explicit source_kind=binout
uses shared GLSTAT/MATSUM and MPP merging for global/Part histories. Units/time_units are required
declarations, with no conversion. Every curve records entity ID (null for global), component,
backend, sampling, source-ID scope, units, sample count and time policy. Complete samples remain
in per-entity CSVs. Every request consumes core ModelRef/FileIdentity/CurveSpec and records the
full immutable request in job.parameters.curve_spec.

Input families are confined and fully hashed, missing/duplicate IDs never become partial success,
source/CSV changes fail without verified artifacts. d3plot duplicate times remain unchanged;
binout merging follows the existing documented union/duplicate-collapse policy and reports it.
Limits are 100 explicit entity curves and one million total samples, not a silent truncation.

Six initial feature tests fail before implementation. Three shared-reader counterexamples also
fail on the old implementation (duplicate IDs, fractional IDs, vector globals silently taking
column one); one scalar-column control passes. Related final Python tests: 70 passed.
A further native-comparison counterexample first succeeded incorrectly when time columns used
the value absolute tolerance. Time/value tolerances are now separate and the case is rejected;
both native versions re-ran the changed Part/global branch.

L2 acceptance:

| Requirement | Evidence |
|---|---|
| Node, element, Part, global | Real 4.13 and 4.10 headless SCL comparisons, four modes each |
| Multiple requested entities | Two node, two solid and two Part curves, one global curve |
| Identity/component/units | Shared-reader/CSV unit tests and per-artifact semantic metadata |
| Values agree with LASSO | All 22 node/solid states, all 3201 binout time samples per curve, checked against independently exported native values |

The complete runs [4.13](r413a-batch-report.md) and [4.10](r410a-batch-report.md) each pass four
cases. Stricter time checks [4.13](r413b-batch-report.md) and [4.10](r410b-batch-report.md) each
pass the two changed Part/global cases. [Structured evidence](evidence.json) retains each actual
clean revision, source Git blobs, binary/config/report hashes and source preservation checks.

Limits: native d3plot comparison is for node/one-point element quantities up to 1000 states;
native Part/global comparison requires explicit single-file binout, with no hidden d3plot or MPP
fallback. MATSUM IDs are stored database IDs, never inferred from another model. D3plot multi-point
means are recorded as means, not mislabeled as native shell layers. Missing data, nonfinite values
or ambiguous axes are refused. No filtering/interpolation/resampling or deletion filtering is added.
4.8 was not run. Raw/public corpus contents and local environment paths were not committed.

After these native runs only request provenance was clarified: ModelRef.units remains unknown
(null), while CurveSpec carries the explicit quantity/time units. A component unit does not
define a complete model unit system. No reader, CSV or native numerical path changed after the
recorded strict-time runs; this provenance-only correction has its own contract regression.
