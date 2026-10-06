# 显式单位转换与曲线对齐

本批对应 A09/T08/WF-POST。依据 [NIST SI 基本与导出单位](https://www.nist.gov/pml/owm/metric-si/si-units)及[十进制前缀](https://www.nist.gov/pml/owm/metric-si-prefixes)，实现长度、质量、时间维度上的机械单位运算。只转换调用者明确声明的单位，不能从 k 文件、数值量级或曲线形状推断模型单位制。

`convert_history_units` 接受一个有限、严格递增时间的单实体标量 CSV，显式给出源/目标时间与数值单位。默认读 time/value 列，可指定其他列名；多实体交织的重复时间将被拒绝。输出新的 time/value CSV，原文件不修改。

支持：m/cm/mm/um（µ/μ 归一化为 u）、kg/g/tonne、s/ms/us/ns、N/kN/MN、Pa/kPa/MPa/GPa、J/kJ/mJ、1/dimensionless/%/microstrain。支持明确的 `*`、`/`、`^` 组合，例如 `N/mm^2`、`mm/ms^2`、`g/cm^3`、`N*mm`；不支持括号、隐含乘法、温度偏置或任意单位名称。最多八项，单项指数 −6…6。

| 合成校验 | 换算结果 |
|---|---|
| N/mm^2 → MPa | 倍率 1 |
| N*mm → J | 倍率 0.001 |
| mm/ms^2 → m/s^2 | 倍率 1000 |
| g/cm^3 → kg/m^3 | 倍率 1000 |
| tonne*mm/ms^2 → MN | 倍率 1 |
| microstrain → % | 倍率 0.0001 |

单位比例内部使用有理数，结果保留精确分子/分母字符串以及实际浮点倍率。样本运算仍使用浮点数，拒绝非有限结果、非零样本下溢成零，以及时间精度塌缩导致的重复时刻。量纲兼容不代表物理量含义相同；例如不能凭单位代替分量、坐标系、符号或平均方式的确认。

## 不同输入单位先统一，再对齐

`combine_history_curves` 增加可选声明：

```json
{
  "paths": ["moving.csv", "reference.csv"],
  "operation": "difference",
  "units": "mm",
  "time_unit": "s",
  "source_units": [
    {"time": "ms", "value": "mm"},
    {"time": "s", "value": "cm"}
  ]
}
```

每条曲线先转换为目标时间/数值单位，之后才在共同时间区间内线性插值、求和/平均/相减，不外推。输入单位声明数必须等于文件数；时间轴必须具有时间量纲；不同值量纲会被拒绝。

旧的三参数调用保持可用，但返回 `mode="assumed_shared"`、`dimensional_compatibility_checked=false`，表示单位已相同只是调用者的前提。显式转换时为 `declared_conversion`，依然保留 `source_unit_labels_verified=false`：检查了声明之间是否相容，并未验证求解模型真正采用这些单位。

## 完整工程配方

[declared_unit_tensile.json](../../../examples/workflows/declared_unit_tensile.json) 将力曲线统一到 N/s，将两条位移曲线统一到 mm/s 后相减，再按显式 mm² 面积、mm 标距和符号构造工程应力/应变及外功。它不自动辨认载荷方向、真实截面变化或颈缩。

`tools/run_engineering_unit_acceptance.py --workspace <output>` 使用新生成的合成 CSV，跑通 kN/ms 力、cm/s 移动端和 mm/ms 参考端的混合输入；应力、应变和 1.8 J 功与解析真值一致。将力误标为 MPa 时，工作流在转换步骤停止。原输入字节保持不变。该验收在 CI 运行，不启动 LS-PrePost，不构成原生软件或真实材料响应认证。
