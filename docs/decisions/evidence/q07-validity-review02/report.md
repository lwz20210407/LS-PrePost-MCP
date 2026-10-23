# Q07 / Q05 曲线输入有效性（review02 后续）

当前有效：曲线算术不再把显式删除或未知样本当作有效测量。任务仍为 partial。

`extract_history` 保留原始零值和 `alive`；这不授权下游把删除后的零当成应变或应力。
共享 `engineering.read_curve` 现在检查可选的 `alive` 列：每行必须严格为 `1`。
`0` 为 deleted、空值/缺行项为 unknown、其他值为 malformed；重复 alive 列亦拒绝。
拒绝包含样本序号，不产生算术产物，不改源文件，不删点、补零或跨无效区间插值。
该入口同时覆盖 curve_ops、convert_history_units、combine_history_curves、build_tensile_curves
及使用同一读取器的旧能量筛查入口；其他独立消费者不能据此推断已覆盖。

无 alive 列的普通 CSV 保持兼容，curve_ops 明确记录 `not_declared`；带全1列记录
`all_samples_alive`。每步和产物保留所有原始输入的扁平有效性来源，不随多步运算丢失。
这只验证文件声明，不认证物理正确性；另存产物后重新作为普通 CSV 读入，不自动推断旧声明。

## 回归与证据

精确命令、执行提交、产品 blob、输出摘要及哈希见 [evidence.json](evidence.json)。
原始 review02 基线 0563045 和修复前主干 461d95c 均复现；不是用缺依赖或导入错误代替失败。
解析对照为 `y=i`、`t=.001*i`，梯形积分 `.001*i²/2`；全活和无声明两种输入数值一致。
另从真实共享读取器的数组回执导出 Q05 CSV，再接 Q07：删除/未知均明确拒绝。

| 范围 | 结论 | 有效性 |
|---|---|---|
| 原始基线和修复前主干 | 新回归失败：错误接受无效输入、无有效性来源 | 修复前行为 |
| Python CSV 校验及解析数值 | 见 evidence.json 的干净提交记录 | 当前有效 |
| LS-PrePost XYPlot 滤波 / GUI / UU / R11 | 本项未运行 | 未验证 |

本项无新增 MCP 工具或参数，无依赖变更；Q07 原生滤波 L2 仍是 gap，不改 done。
