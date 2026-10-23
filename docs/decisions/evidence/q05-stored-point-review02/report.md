# Review02 Q05 explicit history stored points

extract_history now accepts an optional positive 1-based stored_point for d3plot element curves and an independent native_sampling selector. The shared reader passes the same point choice into stress components, invariants and plastic strain as field extraction. Multiple shell/tshell points still refuse an implicit arithmetic mean. Node/Part/global and binout calls reject a point selector. There is no extra parser, unit conversion, interpolation or layer inference.

Contract change: strict frozen CurveSpec adds stored_point (default null, d3plot element curves only). The request manifest binds it; curves/artifacts add stored_point and sampling_spec while retaining the existing human-readable sampling note. Native selector choice is stored separately from the reader point and numerical mismatch fails without silently remapping. Existing calls keep their defaults.

| Evidence | Result | 当前有效 / 已被取代 |
|---|---|---|
| 0563045 missing-point regressions | 6 failed | 真实缺少参数的 TypeError；未当作测试装载错误 |
| Clean 2ccdc34 related unit/title cases | 118 passed | 当前登记源码 |
| [4.13 explicit shell slots](r01-point-413-headless-report.md) | 4 passed | 3正确配对，1故意错配拒绝 |
| [4.10 explicit shell slots](r01-point-410-headless-report.md) | 4 passed | 3正确配对，1故意错配拒绝 |
| [4.13 default history/tensor](r01-defaults-413-headless-report.md) | 12 passed | 保留原调用的行为 |
| [4.10 default history/tensor](r01-defaults-410-headless-report.md) | 12 passed | 保留原调用的行为 |

All native runs execute clean 2ccdc34bdaa7027f4bd830535355ebf9ebc742f9, with empty tracked diff and untracked files excluded. The public shell fixture selects two curves with nonzero slot discrimination, then checks every saved state: slots 1/2/5 numerically match independent mid/inner/outer selections in this file. Slot 3 versus mid fails. This is not a universal geometrical map. The 32 history/field tests use 34 headless native processes; source bytes and directory inventories stayed unchanged. [evidence.json](evidence.json) records actual product/test/installation-fixture blobs, binary/config hashes and verdicts.

The shared core contract changed, so P11's strict product-source guard also received fresh r05 4.13/4.10 raw-save runs, 12 passed each; older captures remain historical. Three independent keyword/title oracles were rerun (16 Parts). No LS-DYNA solver, GUI or UU test ran. Q05 remains partial for other families, Part/global d3plot, 4.8, universal layers and deletion-aware curve consumers.

Reproduce with the locked full shared environment, PYTHONPATH=src plus repository root, PYTHONUTF8=1, PYTHONDONTWRITEBYTECODE=1, OPENBLAS_NUM_THREADS=1, and external LSPP_CORPUS_DIR. Native versions run serially into fresh external output directories:

```text
python -m pytest tests/test_history_stored_point_review02.py tests/test_history_tools.py tests/test_core_contracts.py tests/test_entity_query.py tests/test_shell_sampling_review02.py tests/test_history_deletion_review02.py -q
python -m pytest tests/test_history_points_native.py tests/test_history_native.py tests/test_tensor_field_native.py -m native --run-native --native-strict --native-executable <version-executable> --native-output <fresh-external-directory> -q
```
