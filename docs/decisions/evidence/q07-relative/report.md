# Q07 相对曲线（2026-10-22）

`curve_ops` 新增 `difference(a, b, output, alignment?)`，实现 `a(t)-b(t)`。
不增加 MCP 工具名，不改变旧 combine_history_curves 行为，Q07 保持 partial。

## 时间、单位与数值合同

- 默认 `alignment="exact"`：两条输入的时间数组逐值相同；不使用近似相等来隐藏时钟差异。
- 调用者显式选择 `alignment="intersection"` 时，使用公共时间区间内两套采样点的并集，
  线性插值，不外推；复用 Cross Plot 的对齐实现。相交于一个点或完全不相交时拒绝。
- 公共工具要求两条曲线声明相同的时间和数值单位；不同单位先用 convert_units 显式转换。
  元数据逐步记录公式、源曲线名、alignment、插值策略、实际区间、样本数和输出单位。
- 非有限样本、重复/倒序时间、相减溢出、对齐后的样本数超限均拒绝。输入不修改；
  每一步沿用 JobResult、产物 SHA256 复核和 CSV 导出。

示例：

```json
[
  {"op":"difference","a":"moving","b":"base","output":"relative"},
  {"op":"cross_plot","x":"relative","y":"force","output":"force_displacement"},
  {"op":"engineering_stress_strain","input":"force_displacement","output":"engineering","area":2,"gauge_length":10,"length_unit":"mm"}
]
```

## L1 回归

新增回归测试位于 [test_curve_difference.py](../../../../tests/test_curve_difference.py)。
原先 22 项在 main `4e3a9a84bffc5443a463911ffe9eca2c012dbff1` 上全部失败：
域层没有 difference，公共工具拒绝该操作；实现后通过。后续增加两项资源边界和公共插值用例。

解析解使用 `a(t)=3t+2`、`b(t)=t-1`，相减应为 `2t+3`，在同一采样及交集采样上逐值核对。
完整链路核对相对位移 `[0,.8,1.6]`，初始面积 2、标距 10，工程应变 `[0,.08,.16]`、
应力 `[0,4,8]`。另验证 ms/m 到 s/mm 的显式转换、时钟微差、坏单位与源文件字节不变。

```text
python -m pytest tests/test_curve_difference.py tests/test_results_curves.py tests/test_curve_ops_tool.py -q
```

本次不启动 LS-PrePost。SAE/Butterworth 与原生 XYPlot 的 L2 对照仍未完成，
保留原验收和该 gap，不以解析解测试替代原生一致性。

本地完整依赖回归：**2408 passed / 294 skipped**（Python 3.11）。
Ruff、import-linter（三项合同）、任务/生成文档/工具迁移/语料登记/链接检查均通过。
最终跨平台与最小依赖结果以本 PR 精确头的正式 CI 为准。
