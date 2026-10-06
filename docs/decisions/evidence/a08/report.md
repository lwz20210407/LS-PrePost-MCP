# A08 第三轮批处理复测与历史证据

新复测 r3a08n1 的实际 Git revision 为
`fe75f0b435b9a860d5b1397b9e6c2bce9f799eef`，带未提交的前序合并及 A02
状态修正。运行前记录的 `git diff HEAD --binary` SHA256 为
`7d11a984d8f504e1c852bab4e6c66979d642c79b415d1ad33a854405974b46a5`，
两版运行后均复核不变。去路径的逐项结果、报告哈希和运行身份见
[evidence.json](evidence.json) 的 review_runs。

| 版本 | 通过 | xfail / evidence_only | 范围 |
|---|---:|---:|---|
| 4.13.4 | 10 | 1 | 五个默认批处理配方、尺寸变体；runc 的 PNG 仍失败 |
| 4.10.1 | 7 | 4 | 五个默认批处理配方、尺寸变体及 runc 建盒；其余 runc 失败 |

失败模式保留原诊断，未改用另一个模式冒充成功。此轮仅后台批处理，
没有 GUI 或 UU 运行。A08 仍 partial（后续配方与旧模板迁移未完成）；
A02 也保持 partial，其原生身份缺口不由本次配方模式登记替代。

## 历史记录（未绑定当时的完整 Git 身份）

A08 配方工作树实测：4.13.4 默认批处理五配方及参数变体通过；runc 四配方通过、PNG 失败。4.10.1 默认批处理六例通过；runc 仅建盒通过，其余四例失败并记 evidence_only。原始日志/路径不入库，失败模式不计为能力通过。

本附件从已有本机记录提取，没有新增原生运行。原始路径、原生日志正文和私有数据不入库。

| 日志 | 原记录摘要 |
|---|---|

| 来源组 | 用例 | 当时报告状态 |
|---|---|---|
| a08-native-report-final | tests/test_recipes_native.py::test_builtin_recipe[box_mesh] | passed |
| a08-native-report-final | tests/test_recipes_native.py::test_builtin_recipe[translate_nodes] | passed |
| a08-native-report-final | tests/test_recipes_native.py::test_builtin_recipe[snapshot] | passed |
| a08-native-report-final | tests/test_recipes_native.py::test_builtin_recipe[node_coordinates] | passed |
| a08-native-report-final | tests/test_recipes_native.py::test_builtin_recipe[model_inventory] | passed |
| a08-native-report-final | tests/test_recipes_native.py::test_recipe_runc_capability[box_mesh] | passed |
| a08-native-report-final | tests/test_recipes_native.py::test_recipe_runc_capability[translate_nodes] | passed |
| a08-native-report-final | tests/test_recipes_native.py::test_recipe_runc_capability[snapshot] | evidence_only |
| a08-native-report-final | tests/test_recipes_native.py::test_recipe_runc_capability[node_coordinates] | passed |
| a08-native-report-final | tests/test_recipes_native.py::test_recipe_runc_capability[model_inventory] | passed |
| a08-native-report-final | tests/test_recipes_native.py::test_box_recipe_uses_supplied_dimensions | passed |
| a08-native-410-report | tests/test_recipes_native.py::test_builtin_recipe[box_mesh] | passed |
| a08-native-410-report | tests/test_recipes_native.py::test_builtin_recipe[translate_nodes] | passed |
| a08-native-410-report | tests/test_recipes_native.py::test_builtin_recipe[snapshot] | passed |
| a08-native-410-report | tests/test_recipes_native.py::test_builtin_recipe[node_coordinates] | passed |
| a08-native-410-report | tests/test_recipes_native.py::test_builtin_recipe[model_inventory] | passed |
| a08-native-410-report | tests/test_recipes_native.py::test_box_recipe_uses_supplied_dimensions | passed |
| a08-runc-410-report | tests/test_recipes_native.py::test_recipe_runc_capability[box_mesh] | passed |
| a08-runc-410-report | tests/test_recipes_native.py::test_recipe_runc_capability[translate_nodes] | evidence_only |
| a08-runc-410-report | tests/test_recipes_native.py::test_recipe_runc_capability[snapshot] | evidence_only |
| a08-runc-410-report | tests/test_recipes_native.py::test_recipe_runc_capability[node_coordinates] | evidence_only |
| a08-runc-410-report | tests/test_recipes_native.py::test_recipe_runc_capability[model_inventory] | evidence_only |

[证据 JSON](evidence.json) 保存 442 个原文件的相对标识、字节数和 SHA256，以及可提取的状态/计数。

这些历史用例不证明公开 Win32 路径、全部 GUI 验收或未执行的 UU 格已通过；任务缺口仍以 tasks.yaml 为准。
