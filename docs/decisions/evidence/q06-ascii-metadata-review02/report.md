# Review02 Q06 ASCII metadata and all-column checks

SECFORC's written `ac ID` is now local_frame_reference, preserving the reference number and original prefix text after leading whitespace. It is not claimed to be a coordinate-system ID; there is no frame transformation, and unknown prefixes/layouts remain unsupported. Metadata remains aligned to original stored columns; stored_columns maps any requested reordering.

ASCII legend_titles maps stored IDs to titles. Conflicting titles for one ID are null with a warning; missing/unknown legend layouts are not invented. The existing UTF-8-sig replacement decoding policy remains, so titles with undecodable bytes are not certified byte-exact strings. Numerical records still require positive IDs, aligned strictly increasing times and finite complete columns.

| Evidence | Result | 当前有效 / 已被取代 |
|---|---|---|
| 0563045 metadata regressions | 4 failed | 历史失败证据 |
| Clean 49865a3 related tests | 97 passed / 2 skipped | 对登记产品 blob 有效 |
| Five public files, all 40 database/component combinations | 37 stored components matched; 3 missing components refused | 当前 Python/ASCII 原始列独立核对 |
| Independent raw-column values | 63,608 matched | 当前；不止 x_force |
| Prior six public checks / x_force only | historical, retained | 被本次更广列覆盖取代 |
| Prior 4.13/4.10 native force runs | retained with reconstructed product blobs | 仅对应旧执行代码；不外推新元数据/更多物理量 |

The independent test reader uses source text columns, not production parser helpers/constants. It covers every stored force, mass, moment, magnitude, centroid and area column supported by the selected files. Source bytes and directory listings stayed unchanged. [evidence.json](evidence.json) records actual clean revision 49865a32987f3f4d4a1f276bee44c15b4a0d7719, product/test Git blobs, source hashes, sample counts and artifact hashes; no raw titles, solver text, local paths or curve values are published.

ASCII does not collapse duplicate entity/time rows; it rejects them. The binary MPP shard path unites times only with matching stored entities, collapses repeated times only when all values agree, and reports repeated_times_dropped; conflicting duplicate values fail. These are explicit format policies, not an interpolation or physics rule.

RCFORC CSV keys include side whenever side metadata exists, including one-side/unique-ID results. This applies to both ASCII and binout; consumers should use named headers/column_key instead of assuming a fixed three-column CSV. The change does not remove side to hide ambiguity.

Reproduce from a clean checkout with the shared locked full environment, PYTHONPATH=src plus repository root, PYTHONUTF8=1, PYTHONDONTWRITEBYTECODE=1 and OPENBLAS_NUM_THREADS=1. Set LSPP_CORPUS_DIR to the external public corpus, and optionally LSPP_FORCE_EVIDENCE_DIR to a fresh external directory:

```text
python -m pytest tests/test_ascii_metadata_review02.py tests/test_ascii_force_database.py tests/test_ascii_force_corpus.py tests/test_force_corpus_adapter.py tests/test_results_target_tools.py -q
```

Q06 stays partial. No new LS-PrePost or solver run was performed; native moment/centroid/MPP-SMP equivalence remains unverified.
