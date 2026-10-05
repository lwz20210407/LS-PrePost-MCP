# A08 原生历史证据附件

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
