# 结果选择与取值位置合同

本批落实 T01/T06 的一部分，将 ResultSelection、SamplingSpec 和 FieldSpec 接入现有原生 SCL 场/应力提取与 LASSO 标量/应力提取。没有新增同义工具，保留原有 CSV/返回字段，在任务参数和结果中增加同一份 field_spec。

| 请求 | 记录的取值类型 | 不能据此推断 |
|---|---|---|
| 原生 shell/tshell 的 mid/inner/outer | native_shell_layer，保留 MID/INNER/OUTER | 不自动对应读取器第 1/2/3 个存储点 |
| 原生 solid 的旧参数 mid | native_default，实际选择器 0 | 不是壳中面，也不自动等于读取器第 1 点 |
| 原生单元数值积分点 | native_integration_point，显式正整数选择器 | 不推断跨后端点顺序/物理等价 |
| 原生 node 的旧参数 mid | not_applicable，选择器 0 | 节点没有壳层；拒绝节点的 outer 或数值积分点 |
| 读取器应力积分点 | stored_integration_point，公共下标从 1 开始 | 不自动解释为上下表面/材料层 |
| 读取器标量切片 | stored_axes，逐轴保留下标 | 不自动解释 history 槽位的材料含义 |

## 随结果保存的内容

- 后端、请求字段、实体域、真实用户 ID、1 起始状态。
- 有序选择摘要：数量、最多 20 项样本、SHA-256；完整请求在 job.parameters，避免响应重复展开大数组。
- 取值类型与 cross_backend_equivalence=not_inferred。
- 坐标分量来源、额外平均规则、有效/失效筛选的实际范围。
- 单位标签、dimensional_validation=false 和 conversion=none，不把标签当作量纲已验证。
- 明确已有变换：固定 LASSO 版本的 node_displacement 由状态坐标减参考坐标，记录 state_coordinates_minus_reference_nodes。

这些是请求和来源描述，不自动证明材料历史变量、剪应变约定、平均规则或物理结果正确。没有额外失效掩码时会明确记录。

## 校验与范围

拒绝重复/非正/布尔 ID 和状态；冻结选择列表；Global 没有实体 ID，CSV 的既有 0 是占位值。禁止原生选择器与读取器槽位混用；单位、坐标、平均与有效范围需显式。

上述四类提取接口在 MCP 入参层也使用严格整数，避免布尔值先被类型转换成节点 1/状态 1。导出实现使用合同中冻结的请求副本，调用者随后修改原列表不会改变实际脚本与结果描述。

原有数值算法/文件格式/导出规模限制保持。原生节点接口不再接受假积分点，是有意收紧。实际导出仍走已有 SCL 或读取器路线，未变成新的可见 GUI 后处理执行器。本批合同、SCL 生成/解析、读取器数组提取测试通过，不扩展原生数值/版本认证。

剩余：完整 ModelRef、GUI keyword/result 统一选择、量纲与列级单位、history 变量字典、坐标转换/平均、有效单元掩码与可见 GUI 后处理适配。
