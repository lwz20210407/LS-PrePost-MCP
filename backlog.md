# 待评估需求

- 2026-10-22 用户确认登记：四项目调研转开发输入（meshioplusplus、Crash-Analyst_mAgent、AgentFEM、DynaSense / vscode-lsdyna）。状态：**待评估、未实施**；保持当前 Q12 / PR 积压修复顺序，不插队，不改变 `tasks.yaml` 的里程碑、验收或状态。
  - 完整方案位于本机工作区根目录的 `docs/lspp-umat-four-project-implementation-plan.md`，不是本仓库的 docs。修改位置、验收和探针证据见该方案。配套报告为工作区 `temp/20261021-meshioplusplus-assessment/assessment-report.md`、`temp/20261022-cae-agents-assessment/assessment-report.md`、`temp/20261022-vscode-lsdyna-assessment/four-project-assessment.md`。这是本机交接定位，不表示这些文件已在远端仓库；发布时不得提交私人绝对路径或手册。
  - 采用方式：meshioplusplus 固定版本作可选几何/网格交换后端；DynaSense 固定发布版作独立伴随编辑器。AgentFEM 借鉴实验身份、科学验收、Campaign 合同；Crash-Analyst 借鉴检索元数据与冻结评测。不整仓部署，不另建第二套 PyDYNA AST 字段提供者。
  - U01/E01/U02/R01/B01/M01/D01/K01/D02 是方案工作包标记，不是正式任务 ID。现有范围对照 Q01/Q03/Q04/Q05/Q06、P02/P07/P09、A09/A10；超出范围先登记正式任务及验收，新增 T1 名称还需 target_tools 和操作注册表。以下优先级为技术依赖建议，不重排当前里程碑。
  - 优先 U01（外部 UMAT V2 项目）：现有 PowerShell/Python 验证贯通 RunRoot；两个运行根互不覆盖，历史结果/V1 不变，现有编译和材料点回归通过。UMAT runner/求解器提交不擅自扩展进本 MCP 当前范围。
  - 优先 E01：在 `core/experiment_contracts.py`、schema、`domain/experiments/` 新增实验 sidecar/科学 claim/冻结 profile，复用 JobResult/v1、Jobs；缺数据/NaN/轴或单位不明不得科学 PASS；大文件、递归 Include、UMAT/求解器/编译器/profile 内容变化拒绝复用旧结果。产物身份 verified 不等于科学验证通过。
  - 优先 R01（结果相关范围）：复用 `post_tools.py` 已有 `inspect_result_fields` / `extract_d3plot_field` 原始 stored-axis 出口和共享 LASSO/MPP 层，增加 TC4 60 HSV profile/轴元数据；验收保留原 ID、时间、层/IP、槽位、单位、alive，不把平均值冒充原始 IP，不解除原生实体点 2～8 的现有限制，保留各 binout 数据库独立时间轴。
  - U02（外部 UMAT V2 项目）：沿用唯一 Fortran 和驱动，分层验收材料点、目标 R13.1.1 double 实际链接、单元算例、restart、完整 HSV/删除及网格/步长；R11、stub、对象干编译不能代替目标宿主验收。
  - 后续 B01（A09）：在 `workflow_sweeps.py` 扩展隔离并行/恢复；仍按 A09 原验收，50 组、单组失败隔离、打断续跑、身份变化拒绝复用、汇总可追溯；保留旧 20 组顺序接口语义。
  - 后续 M01：可选 meshioplusplus worker、网格草稿、ID 映射/有损报告、递归路径约束和真实试件回读。禁止完整生产 .k 往返重写（材料/接触等会丢失），禁止统一 binout 时间序列替代峰值审计；分发前核对 OCCT 许可。
  - 后续 D01/D02：先独立 DynaSense 发布版试用，后评估文件/JSON 审阅桥接；验收包含已保存文件 hash/版本、脏缓冲区/过期 Include 拒绝、预览与新修订。GPL 代码/资产不直接复制进主仓；UMAT 布局可读不等于安全自动写；IORTHO 差异先做版本对照，不当作已证实本地 bug。
  - 后续 K01（A10）：沿用 `domain/model/keyword_docs` 唯一字段来源，对照精确/FTS5 与候选语义检索的冻结盲测；保留旧 24 题回归，新题集目标仅为候选门槛，不替换 A10 原验收。Crash-Analyst 有占位模块、接口漂移和脚本问题，其 README 不作现成 CAE 能力证据。
  - 第一批技术候选 U01、E01a/E01b、R01a；实施前按当时分支重定位代码，评估范围并补正式任务/测试。本条登记不代表任何工作包已完成。

- 2026-10-06 用户指出的运动副/连接建模缺口：铰链等运动副的创建与编辑、两侧实体/刚体归属、连接节点、轴线/局部坐标系、允许与受限自由度、悬空引用及过约束检查，并通过保存重开与运动/受力算例核对。当前 P05 验收没有 JOINT 流程；已有 SPC、规定运动、CNRB 或通用关键字字段能力不能据此算完成。已记入 backlog，将在 M1 结束时评估；涉及 Claude 的 domain/model 后端，先协调归属与任务验收，不在 M1 擅自新增实现。
  - 2026-10-06 用户确认由 Claude 接手，已登记为 tasks.yaml P12（M3）。

- I08 / Claude 审阅 P2：补齐 17 个 legacy alias 的明确指向对象；解决 open_model 同时作为 T1 目标名和旧别名的命名冲突。保留到后续迁移，不在本轮 P1 修复中改变路由行为。

以下为旧清单中超出 tasks.yaml 当前验收范围的未完成需求；没有新增排期或完成状态。与现有任务重合的 Include、接触、曲线库、宏、显示、测量、网格八项操作等不重复列入。里程碑结束时评估，用户明确要求立即插队时另行处理。

- 屏幕 Area/Poly、遮挡与可见像素拾取；来源：[旧 B01](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- ByPath/ByEdge 连续路径及 Prox 到表面距离选择；来源：[旧 B03/B04](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 按 fringe 区间/材料筛选与跨模型持久选区名称、自动 ID 映射；来源：[旧 B06/B07](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 节点向任意直线/平面/CAD 投影、等距分布；来源：[旧 C01](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 定向 Replace 的更多引用族、删除未引用节点；来源：[旧 C02](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 梁/离散单元创建、既有连接编辑、壳 Split/合并/局部细化；来源：[旧 C03/C04](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 重复单元、自由边/孔洞检测及自动修复；来源：[旧 C05](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 材料轴/载荷向量随动变换、任意方向多部件拉伸/扫掠/旋转成体；来源：[旧 C08/C09](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 厚壳/Segment 法向、复材铺层专门编辑与 SPH 粒子生成；来源：[旧 C06/C11/C12](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 部件分割/合并、Subsystem/Group、多模型装配比较；来源：[旧 D01/D06](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 材料/截面/曲线等全部卡片编号空间重编号；来源：[旧 D04](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 定向修复建议与自动优化循环，梁/厚壳专门质量检查；来源：[旧 D07/D08](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 过滤器的 GUI 编辑与 Keyword Manager 联动；来源：[旧 D09](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- SALE、轴对称等完整工况模板与独立工程案例库；来源：[旧 D10/D11](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 材料相关 HSV 解释、梁/厚壳/特殊实体局部及随动坐标结果；来源：[旧 E02/E04](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 重启时段拼接与非固定实体 ID 的 ELOUT 多积分点数据库语义；来源：[旧 E06](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)、[UI ELOUT 观察](docs/archive/2026-10/UI_AUDIT_POST_GAPS.md)。
- 随动参考、区域平均、虚拟引伸计/应变计；来源：[旧 E09](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 路径结果、矢量/轨迹/Follow，接触侧力的矢量和与模之和区分；来源：[旧 E10](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)、[UI NCFORC 观察](docs/archive/2026-10/UI_AUDIT_POST_GAPS.md)。
- 热能预算、颈缩后塑性段与截面变化修正、实验曲线比较；来源：[旧 E11/E12/E13](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 碎片/连通域、残余速度和分组质量/能量统计；来源：[旧 E14](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 温度偏置单位与完整列级单位传播；来源：[旧 A09](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- keyword/d3plot 外的导入导出、保存选区、精度选项；来源：[旧 F01](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- Split Window、多模型同步相机/色标、Annotation 和批量报告布局；来源：[旧 F05/F07](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- 任意工作流分支、完整模型/显示/选择/宏状态预览与回退；来源：[旧 G06/G07](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。
- keyword/result 显式关联、多模型录制、所有 resident 模型崩溃恢复；来源：[旧 F11 及后续条目](docs/archive/2026-10/REQUESTS_AND_PRIORITIES.md)。
- DPF Server 上的真实数据验收与版本/许可适配；来源：[DPF](docs/archive/2026-10/DPF_INTEGRATION.md)。
- 几何/CAD 创建、修复、中面与几何驱动划网格；来源：[旧 H06/G01–G03](docs/archive/2026-10/REQUESTS_AND_PRIORITIES.md)。
- 求解服务、许可证、队列、资源监控与行业高级模块；来源：[旧 H07](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)。

原生稳定性缺陷与复现风险集中在 [KNOWN_ISSUES](docs/KNOWN_ISSUES.md)；不把未验证风险改写为已完成任务。
