# 含标准质量单元模型的保真操作

归属runtime / model / T03 / T12-ENTITY，为WF-MESH与WF-AUTO的选择、集合和载荷操作补共用校验。不是新建质量、编辑质量矩阵或完整辅助单元工具。

## 原生证据与实现

本地Scripting API手册列出 `num_mass_elements`。4.13.4应用内Python实测：官方Example11共有41节点、21单元，其中20梁、1质量单元；`DataCenter.Type`列出BEAM/NODE/PART/SHELL/SOLID/SPHNODE/TSHELL，没有MASS。该构建查询 `num_inertia_elements` 会报不存在，尽管本地手册列有它。因此不猜枚举整数，也不把手册字段直接认作当前构建能力。

结构读回前，由LS-PrePost保存本次请求独立的原生keyword。保留既有梁连接读取路径，并在无梁但有质量单元时同样导出。针对标准 `ELEMENT_MASS` 读取：

- 质量单元用户ID、连接节点用户ID、质量值、Part ID（允许原生PID=0）。
- CSV或原生8/8/16/8列布局，非有限/负质量、重复ID、额外字段拒绝。
- 导出记录数与当前SDK质量计数一致；所有连接节点必须属于当前注册节点。
- 壳＋实体＋梁＋已验证质量数必须等于原生总单元数。其他单元不靠忽略数量差异“兼容”。

质量值与连接加入完整几何摘要，Part归属加入成员摘要；任意前后变化都会使原有保真校验失败。载荷/集合操作还核对原生keyword卡片未被额外修改。比较基准是载入后的原生导出；不承诺LS-PrePost导出恢复原始文本排版或所有浮点尾数。原始用户文件始终不覆盖。

## 可用范围与明确边界

已验证：节点选择、节点集创建、节点载荷、录制参数回放、显式新进程重开。在含标准质量单元的模型中，这些流程不再因为总单元数不等于壳/实体/梁之和而一律失败。

`auxiliary_elements` 返回质量数量、来源和校验范围。质量单元glyph显隐未由可靠接口读回，不能生成假的active标记：`display_active_preserved`/`entity_display_active_preserved`在这种模型上为null，`structural_display_active_preserved`单独表示壳/实体/梁及适用Part状态保持。质量Glyph不是侵蚀状态。

目前仍拒绝含质量单元的全element选择、壳拓扑/法向操作及实体Blank工具；完整旧式网格快照也仍只覆盖已声明单元族。惯性单元、质量矩阵、离散/安全带、TSHELL/SPH等不由这次实现获得认证。新桥接代码在新建GUI会话加载，旧版本和无GUI单独验证。

## 验收

- `tools/run_public_nodal_load_acceptance.py`：官方[Example11](https://lsdyna.ansys.com/example-11/)完整输入保留ELEMENT_MASS；既有SET载荷重合拒绝、复用曲线新增X载荷、显式Y叠加、保存、新进程重开和卡片比较通过。
- `tools/run_mass_preservation_acceptance.py`：2节点/2质量、无梁壳实体的合成模型，节点选择→集合→力→修改节点参数回放→保存重开，质量、连接和PID均保持。
- 单测包含质量/节点/PID变化、未知连接节点、计数不匹配、重复和非有限质量、无梁时导出，以及未认证显隐操作的拒绝。

原始失败见[COVERAGE-MASS-003](NATIVE_KNOWN_ISSUES.md)。此次修复该标准质量单元阻断，不把有限实机矩阵推广为任意复杂装配模型稳定性。
