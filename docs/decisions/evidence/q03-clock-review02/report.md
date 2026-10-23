# Review02 native time and force tolerance follow-up

Additional regression probes found the fixed 1e-9 time tolerance accepted different tiny timestamps in tensor and d3plot/binout history checks. Time comparisons now keep rtol=1e-6 with atol=0 in the model's written time units; a zero reference time needs zero. No interpolation, time shift or resampling is introduced. The Q06 native force adapter also had a fixed 1e-6 value floor; it now uses 1e-6 times each reader entity/side curve's maximum absolute value, with zero atol for an all-zero reference curve.

Metadata records the actual rules: tensor adds time_rtol/time_atol/time_reference; history's tolerances.time uses zero atol; Q06 tolerances.value replaces the single fixed atol with atol_rule/atol_by_curve, and each comparison row carries value_atol. Tool signatures and JobResult/v1 are unchanged. No result values are replaced with native values.

| Evidence | Result | 当前有效 / 已被取代 |
|---|---|---|
| Original 0563045 tensor/history time regressions | 6 failed / 1 equal-time control passed | 历史错误接受证据 |
| Current-main 4cf2cdf Q06 adapter regressions | 4 failed | 原0563045尚无此适配器，未把import错误算回归 |
| Clean b6b372b related host tests | 85 passed | 对登记产品实现有效 |
| [4.13 headless](r01-413-headless-report.md) | 19 passed | 对登记产品blob有效 |
| [4.10 headless](r01-410-headless-report.md) | 19 passed | 对登记产品blob有效 |

Both native runs execute clean b6b372b95f91ac47d5e6c1385fa832b0ebf1ca5b, empty tracked diff, untracked files excluded. Each covers eight tensor tests, four history modes and seven named force tests. Each includes three expected failed comparisons (wrong shell slots/component) with clean native jobs; all input bytes and directory inventories remain unchanged. The two runs contain 46 native processes. Actual product modules, native test/installation-fixture blobs, binary/config hashes, baseline stdout hashes and all verdicts are in [evidence.json](evidence.json). Older evidence remains scoped to its old implementation and is not relabeled as the new tolerance proof.

Reproduce with the shared full locked environment, PYTHONPATH=src plus repository root, PYTHONUTF8=1, PYTHONDONTWRITEBYTECODE=1, OPENBLAS_NUM_THREADS=1 and LSPP_CORPUS_DIR pointing to the external public corpus; run versions serially with fresh external output directories:

```text
python -m pytest tests/test_native_time_tolerance_review02.py tests/test_force_tolerance_review02.py tests/test_field_validity_review02.py tests/test_tensor_field.py tests/test_history_native_tolerance_review02.py tests/test_history_tools.py tests/test_database_native_check.py -q
python -m pytest tests/test_tensor_field_native.py tests/test_history_native.py tests/test_database_forces_native.py -m native --run-native --native-strict --native-executable <version-executable> --native-output <fresh-external-directory> -q
```

Q03/Q05/Q06 stay partial. These selected datasets do not certify all shell layers, Part/global d3plot histories, 4.8, every force quantity or MPP/SMP equivalence. No GUI/UU test or LS-DYNA solve was run.
