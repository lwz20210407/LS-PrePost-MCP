# Review02 I04 legal Include variants and focused public rerun

Legal INCLUDE_TRANSFORM/AUTO_OFFSET cases are product_unsupported_include_variant, rather than input restrictions. They now execute an independent raw native read before remaining failed product round trips. There is no xfail exemption for this category. Missing/unreadable inputs retain separate input-limit classification.

| Evidence | Result | 当前有效 / 已被取代 |
|---|---|---|
| Old clean public100 c46bb9d recorded report | 45 passed / 5 failed / 50 evidence_only | 历史记录保留；50 中11条误列输入限制 |
| Corrected interpretation of that historical run | 45 passed / 16 failed or product gaps / 39 input limits | 45/61 runnable; does not invent native runs |
| First new harness attempt a031f86 | 1 failed | SCL main defined but not called; failed observation retained |
| Clean 046b512 focused run | 3 passed / 12 failed | 本次15例真实运行 |
| Latest frozen ledger | 48 passed / 13 failed / 39 input limits | 混合执行提交，不是同头全100例重跑 |

The focused run tested the eleven legal variants plus 010/025/063/082. All eleven variant raw reads succeeded in 4.13, with positive node observations, headless clean native exits and unchanged inputs. The product round trips remain unsupported and failed. 025/063/082 completed full node-ID/coordinate, count and Part-list comparisons after real save/reopen; 010 still fails saved-reload parameter checks. No failure was reclassified as a pass.

Actual execution revision: 046b512ea424f9fd08a2c01072744a24d0e6f174, clean worktree, empty tracked diff, untracked files excluded. This produced 366 headless native processes and compared 1,694,880 node entities (5,084,640 coordinate components) across the three large save cases. All 15 input trees and recursive source-directory inventories were unchanged. The first harness failure and all historical verdicts remain in [evidence.json](evidence.json), alongside product/test blobs, file-tree hashes and per-case scopes. The [ledger](r02-413-headless-report.md) marks every row's actual revision; the other 85 cases were not rerun and are not new acceptance evidence.

Reproduce serially with the shared locked full environment, PYTHONPATH=src plus repository root, PYTHONUTF8=1, PYTHONDONTWRITEBYTECODE=1 and OPENBLAS_NUM_THREADS=1. Set LSPP_CORPUS_DIR to the external registered public corpus; --native-executable must identify 4.13. No GUI/UU window was used.

```text
python -m pytest tests/test_public_corpus_native.py -q -m native --run-native --native-strict --native-executable <4.13-executable> --native-output <fresh-external-directory> -k "extra-keyword-006 or extra-keyword-010 or extra-keyword-022 or extra-keyword-024 or extra-keyword-025 or extra-keyword-026 or extra-keyword-030 or extra-keyword-032 or extra-keyword-038 or extra-keyword-046 or extra-keyword-050 or extra-keyword-063 or extra-keyword-066 or extra-keyword-074 or extra-keyword-082"
```

Expected current process exit is 1 because the twelve product failures remain real test failures. Runtime was 7,122 seconds; complete node paging repeatedly opens the large models, so this is not an optimized throughput benchmark. No new environment or corpus clone was created.

Baseline 0563045: three new verdict regressions failed (legal variant classified as input; raw native step skipped). The subsequent native-failure control also ensures no exemption is substituted for failed raw reference reads. Related offline tests pass. Old hardcoded 29/11 transition assertions were replaced by evidence/report consistency.

I04 remains partial. The 39 incomplete/unreadable cases have not entered functional testing: keep IDs/source hashes frozen, restore complete Include trees, or publish a separately versioned replacement set without erasing historical failures. Other Include semantics, 010 parameters, result-03 EOF handling, remaining native coverage and remote tests remain gaps. No corpus/model/log data or private paths are committed.
