# I08：客户端迁移元数据（L1）

本轮补齐已有兼容元数据的客户端可见性，不改变 I08 原 done/L1，不新增工具或改变默认暴露。原来“全部 legacy_until=null”已由7bd43ba修复，本轮没有重做该项，也没有编辑 operations.json。

实际运行来源为 clean `7fb814cf0575b0bb5c55a2ee419d33ff9732e780`（合并 main9301 后的仪表提交），结果见 [evidence.json](evidence.json)。源码在运行前后保持一致；没有调用 LS-PrePost、solver 或 GUI。

| 入口 | 本轮行为 | 有效性 |
|---|---|---|
| full list_tools | `_meta["ls-prepost-mcp"]`给 operation_id、migration_target、legacy_until、compatibility_alias、migration_target_registered | 当前来源有效 |
| full description | 只对兼容名追加期限/目标短提示；现行工具描述原样 | 当前来源有效 |
| compact find / describe | 同一 registry helper；名称与 operation_id 查询一致 | 当前来源有效 |
| 默认 full / compact | 仍为163工具 / 3入口；142兼容名保留至v0.6，21现行名不误标兼容 | 未改变策略 |

注册目标只是迁移指导，不承诺调用等价或原生支持。recipe/alias/规划目标明确标为不是注册工具；没有删除旧名或悄悄切换 profile。typed签名、直接/GUI路由、参数验证与执行目标保持。

| 验证 | 实际结果与范围 | 有效性 |
|---|---|---|
| 旧产品回归 | main15ac产品上10项失败；新增测试当时为WIP，产品blob单列。正常MCP list包裹解码随后仅作测试适配，不改变缺元数据失败点 | 历史，已修 |
| 合并源码回放 | 31 passed，含专属迁移、既有registry/compact、知识零命中诊断与真实full/compact stdio；原型20/11子集不相加 | 当前7fb来源有效 |
| 可选SDK缺席 | 进程内阻PyDYNA/LASSO，18通过、2个stdio deselected；不冒称子进程也禁SDK | 合并前同三代码blob的有限控制 |
| 原P03流程 | 四原文件60/60、stdio两例和新offline wheel真实回放 | [独立新上下文](../p03-migration-metadata-refresh/report.md)，非native |

P03来源先显式选了原20文件加registry代码共21；收编审计发现还实际消费registry数据 operations.json。原producer/capture/wheelproof的21口径和SHA保持，另从**当时真实clean7fb完整before/after source_files**提取数据raw身份，核两边相等、Git7fb/current blob相等、immutable已生成wheel对应成员等同GitLF。归档口径是 **explicit21 + archived data1 = 22**，不是声称原producer显式选择22，也不是新跑60或新revision。I08自身为显式三代码加同源归档数据一项；current门禁要求代码和数据，并有遗漏/数据blob漂移拒绝控制。

根代理对源码和上述归档的核对是内部Codex复核，不是用户安排的独立外部done审阅。Part Data原生回读、材料物理校准、更多参数/版本覆盖仍为P03缺口；没有扩大已有任务的完成等级。11个检索产品blob与原来源相同，旧P03两轮与A10/98题全部对象保留，没有重新打开旧SQLite、重建全文索引或冒称新的98题运行。
