# 节点、节点集力与力矩

归属 model / D04 / T12-ENTITY，串联 WF-MESH 和 WF-AUTO。入口 `create_gui_nodal_load` 复用受管选择、原生keyword片段导入、完整网格摘要、显隐检查、卡片回读和录制参数化，不另建执行后端。

## 明确载荷含义

必填 `axis`（x/y/z力、rx/ry/rz力矩）、`curve_id`、`time_unit`、`value_unit` 和 `distribution`。例如力用N，力矩用N*mm；只检查量纲，不自动换算或猜测模型单位。

目标在 `node_ids`、`node_set_id`、同一会话的 `selection_job` 中选一个。公开ID始终是用户节点号。选区必须属于当前模型代际及几何状态；单次成员上限20000，不是模型规模上限。

- `per_node`：曲线值乘scale施加给**每个节点**。选择节点集时生成 `*LOAD_NODE_SET`，随后修改集合成员会改变受载节点及合力。
- `total_equal`：曲线值乘scale是当前选择节点的总力/总力矩，按人数均分。生成 `*LOAD_NODE_POINT` 固定当前成员，即使输入是node_set_id也不维持集合链接；随后集合编辑不会改变这批载荷。不是按面积或质量加权，不保证任意参考点上的力矩等效。

返回 `affected_node_count`、`per_node_scale`、`summed_scale`、`set_membership_linked` 和具体卡片读回文件。三个节点、曲线末值90N、scale=1：per_node的合力为270N；total_equal各节点30N、合力90N。真实曲线自身的SFA/SFO/OFFA/OFFO保留，不隐式改写。

提供points和curve_title创建新 `DEFINE_CURVE`；不提供则复用已存在的一般时间曲线。新曲线必须至少两点、有限且时间严格递增；曲线/表/函数命名空间冲突拒绝。scale要求有限非零；支持负值。全局固定方向之外的局部系、随动力/随动力矩、刚体载荷及命名ID变体暂不创建。

## 叠加与约束

工具解析已有POINT/SET成员，默认拒绝相同节点相同全局DOF的重复载荷。设置 `allow_superposition=True` 明确允许叠加，保留原有卡片。遇到相交范围中不能明确解释的局部/随动载荷时拒绝；不靠相同DOF整数猜测坐标含义。

在SPC或规定运动节点上施力可能是用户有意的反力场景，所以不会一律禁止，也不会修改约束。`constraint_review` 提醒存在约束重合或约束无法完整判定；这不是求解物理有效性认证。力矩是否有有效转动自由度、载荷是否足以支撑用户工况均须结合单元与模型判断。

## 完整流程与验收

选择 → 集合或节点列表 → 工程单位/分布/曲线 → 引用及叠加检查 → 导入片段 → 验证网格/显隐/旧卡片保持 → 导出 → 显式新进程重开。

录制会把selection_job转换为步骤结果引用；更换节点数量后回放total_equal会重新计算均分因子。未修改的原始输入保留。当前原生验收为Windows4.13.4；4.8/4.10、无GUI、求解器及任意Include/参数卡保持不因此通过。

- `tools/run_nodal_load_acceptance.py`：合成混合网格，六轴、新建/复用曲线、逐节点/均分、选区→载荷录制和参数回放、重复加载显式叠加、受约束节点提示、集合变更语义、错误引用、原生保存和新进程重开。
- `tools/run_public_nodal_load_acceptance.py`：官方Example11原文件副本，41节点/21单元含ELEMENT_MASS。最初被共用摘要拒绝；增加[标准质量单元保真](MASS_PRESERVATION.md)后，同一完整原例已通过既有SET冲突、曲线复用、叠加及重开，不删除质量单元。测试单位仅为显式API标签，不声称推断出历史例的完整单位制。质量glyph显隐未验证。

## 依据

- [官方LoadPt面板](https://lsdyna.ansys.com/loadpt/)将节点/节点集/刚体载荷与通用选择连接；本工具先实现节点与节点集创建。
- [LS-DYNA关键字手册](https://ansyshelp.ansys.com/public/Views/Secured/Doc_Assets/Release/v242/LS-DYNA_Manual_Volume_I_R14.pdf)：LOAD_NODE施加给节点或集合内每个节点，不能自动当集合总力。
- [官方Example11](https://lsdyna.ansys.com/example-11/)提供包含既有LOAD_NODE_SET、曲线和梁的公开回归输入。
- 本地PyDYNA0.12.1的LoadNodePoint/DataFrame与LoadNodeSet字段定义；仅生成目标片段，不用PyDYNA全量重排用户模型。
