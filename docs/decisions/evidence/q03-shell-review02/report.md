# Review02: explicit shell points and field validity

P1-9 is fixed in the shared reader: multiple shell/tshell stored points require an explicit 1-based stored_point, for six-component stress, scalar invariants and plastic strain alike. A solid may retain its reported Gauss-point mean. An arithmetic shell point mean is never described as a thickness integral. Q05 currently has no public stored_point parameter and therefore refuses implicit multi-point shell histories; that API gap remains tracked by Q05.

Scalar and tensor calls share family confinement, state-range and deletion-data prechecks. Both expose alive_total_count before masking, active_count among returned rows, and finite_count among returned rows (all six components finite for tensors). Counts with unknown deletion flags remain null. Artifact frame labels are `as stored`; no CMPFLG interpretation or coordinate transformation is claimed.

Native stress tolerances now use rtol=2e-5 and, independently for each component, atol=1e-6 times the maximum absolute native reference value. An all-zero reference component has zero absolute tolerance. This rejects small/zero-field mismatches previously hidden by a fixed 1e-6 floor.

| Run | Result | 当前有效 / 已被取代 |
|---|---|---|
| [r01 4.13](r01-413-headless-report.md) | 7 passed / 1 failed | 历史失败；旧夹具误用未确认的 Part ID，被身份守卫拒绝 |
| [r02 4.13](r02-413-headless-report.md) | 8 passed | 对登记产品 blob 有效 |
| [r02 4.10](r02-410-headless-report.md) | 8 passed | 对登记产品 blob 有效 |

The final runs execute clean revision a1c6a5e396e0a70508c04efead77610b200fa228. Each includes six positive comparisons and two deliberate wrong shell-slot/native-layer pairs rejected as failed, with no verified export artifacts. The public solid compares the full explicit element-ID set; title ordinals are not invented user Part IDs. Both public source-family hashes and directory listings remain unchanged. Synthetic Part-filter controls retain confirmed Part IDs. Independent public title/keyword oracles were also rerun on this clean revision: three passed, sixteen Parts checked.

Baseline 0563045: sampling/dispatch regressions 12 failed / 3 passed controls; validity/frame/tolerance regressions 6 failed. Failure output hashes, actual revisions, clean-tree/diff scope, product blobs, test blobs, executable hashes and case results are in [evidence.json](evidence.json). No solver, GUI or remote-disconnection test was run.

Reproduce serially from a clean checkout, with PYTHONPATH=src plus repository root, PYTHONDONTWRITEBYTECODE=1, OPENBLAS_NUM_THREADS=1 and LSPP_CORPUS_DIR pointing at the external registered corpus:

```text
python -m pytest tests/test_shell_sampling_review02.py tests/test_field_validity_review02.py tests/test_field_metrics.py tests/test_tensor_field.py tests/test_history_tools.py tests/test_entity_query.py -q
python -m pytest tests/test_tensor_field_native.py -m native --run-native --native-strict --native-executable <4.13-or-4.10-executable> --native-output <fresh-external-report-directory> -q
```

Q03 remains partial: no universal shell depth mapping or unified legacy/native-primary extraction surface. Two full-family SHA256 passes are retained to detect changes during extraction; their large-family cost remains a performance gap, not weakened to a stat-only cache. Historical Q03 evidence is retained and marked superseded for current sampling/tolerance semantics.
