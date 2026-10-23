# Review02 Q01 bounded clocks and native failure diagnostics

Native failures now retain their execution diagnostic without running observation validation on absent/malformed data. Successful native observations still undergo state/time checks. No false format error is appended to a crash.

Reader and native clocks above 10000 entries move to state-times.json, with full vectors, 1-based state context and model-time units. Native agreement compares all samples before bounding the response; times=null and times_storage=artifact explicitly direct callers to the verified artifact. Artifact output failure returns a failed bounded job. The remaining inventory fields are not paginated by this change.

| Evidence | 当前有效 / 已被取代 |
|---|---|
| Baseline 0563045: four regressions failed | Historical failure evidence |
| Clean wrapper regressions: related 58 passed / 4 external skips | Current for recorded product blobs |
| Three independent paired keyword checks: 16 Parts | Refreshed title provenance; no native title claim |

Actual unit execution revision: `35df3aa1fc87dea130d9dc3bfa75f8225dd38512`; evidence.json binds product and test blobs and the baseline stdout SHA256. PostTools' tool description was subsequently updated to describe the artifact threshold; no further executable behavior changed. No new LS-PrePost/solver run is claimed. Q01 stays partial, including the 4.8 native crash and wider inventory comparison gaps.

Reproduce: python -m pytest tests/test_overview_payload_review02.py tests/test_result_overview.py tests/test_result_overview_validity.py tests/test_part_title_identity_review02.py -q, with the shared locked environment, PYTHONPATH=src plus repository root, and output/cache in the dated scratch directory.
