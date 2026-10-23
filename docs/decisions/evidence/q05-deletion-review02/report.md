# Q05 review02: deletion validity and a discriminating native oracle

Element histories now retain raw stored values with an explicit alive column: 1=active, 0=deleted, empty=unknown. Each curve records deletion_status and the first observed deleted_from_state (1-based). Missing flags never become all-active. The reader refuses malformed flag/state/ID axes; no curve is silently dropped or backfilled. Raw zeros after deletion are NOT physical active-element measurements. Warnings and CSV metadata state this; node/Part/global CSVs keep their existing two-column shape.

A frozen public projectile regression checks solid ID 1: active states 1-2, deletion from state 3, three quantities (plastic strain, Mises, sxx), unchanged input-family hashes. Plastic strain just before deletion is about .527, followed by stored zeros flagged alive=0. The regression failed on 0563045 because the exported curves carried no validity column.

The shared history reader requests only its quantity, times and deletion state arrays (geometry metadata still loads; selected arrays still contain their full entity axes). This avoids reading unrelated state fields; it is not a custom binary entity-slice reader. Native value atol is now 1e-6 times each reference curve's maximum absolute value, without a unit-dependent floor; an all-zero reference has zero atol. Two deliberately wrong small/zero curves that passed on old main are rejected. Beam/unsupported native quantities receive explicit diagnostics rather than a Part/global binout message or KeyError.

| Evidence | Baseline 0563045 | Fixed | 当前有效 / 已被取代 |
|---|---|---|---|
| Deletion/axis/filter/public CSV regressions | 11 failed | 11 passed | Recorded product scope |
| Small-value tolerance/unsupported diagnostics | 4 failed | 4 passed | Recorded product scope |
| Native node evidence discriminator | 1 failed (missing nonzero oracle) | passed | Recorded product scope |
| [4.13 headless](r01-413-headless-report.md) | Previous weak node choice retained historically | 4 passed | Recorded product scope |
| [4.10 headless](r01-410-headless-report.md) | Previous weak node choice retained historically | 4 passed | Recorded product scope |

Clean execution revision: `8c972f58f45344fbd45543b2dc85dfd0c6f9e4c5`. [evidence.json](evidence.json) binds product modules, actual revision, test blobs, executable/config hashes, reports and the public result-family hash list. Node IDs 36/365 have nonzero Z-displacement peaks about 80.013/79.735 and curve separation .2776, compared with native readback; both value errors are zero. Each version covers d3plot node/solid and explicit binout Part/global. Global and Part binout cases have 3201 and 6402 samples respectively; these are not d3plot aggregate evidence.

The three independent public keyword/title oracles were also refreshed after the shared lasso_backend change (3 passed, 16 Parts, all source bytes unchanged); prior captures remain in their own evidence history. No raw corpus, CSV, native log, configuration or private path is published.

```text
python -m pytest tests/test_history_deletion_review02.py tests/test_history_native_tolerance_review02.py tests/test_history_tools.py tests/test_results_lasso.py tests/test_entity_query.py -q
python -m pytest tests/test_history_deletion_corpus.py tests/test_part_title_keyword_oracle.py -q
python -m pytest tests/test_history_native.py -m native --run-native --native-strict --native-executable "<4.13 executable>" --native-output "<outside-repo>/history-413" -q
python -m pytest tests/test_history_native.py -m native --run-native --native-strict --native-executable "<4.10 executable>" --native-output "<outside-repo>/history-410" -q
```

Set PYTHONPATH=src plus repository root, PYTHONDONTWRITEBYTECODE=1, OPENBLAS_NUM_THREADS=1 and LSPP_CORPUS_DIR to the external registered corpus. Native runs are serial and headless. Local related code tests: 52 passed. Q05 stays partial/L1: d3plot Part/global, shell/tshell/beam native coverage and 4.8 remain missing. Native comparison remains limited to 1000 d3plot states and one binout file for aggregate histories. Stored-point selection and other curve consumers' automatic handling of the alive column are not added here; use explicit valid time intervals. Verification certifies serialized source data/identity with validity flags, not the physical validity of deleted samples.
