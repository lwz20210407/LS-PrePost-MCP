# 待评估需求

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
