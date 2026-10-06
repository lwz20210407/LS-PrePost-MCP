# Segment压力与无反射边界

属于T12-ENTITY、WF-MESH与WF-AUTO。复用原生受管会话、检查点、片段导入、网格/显示验证和保存重开；只增加请求的曲线/载荷/边界，其他原生导出卡片必须保持。

## 压力

`create_gui_segment_pressure` 接收Segment集ID、曲线ID/名称、严格递增的时间—压力点，以及明确的时间/压力/坐标单位。新建DEFINE_CURVE和LOAD_SEGMENT_SET；提供load_id/load_title可建立命名载荷。支持倍率、到达时间及transient/relaxation/both曲线用途。

单位只核对量纲，不从模型猜单位，也不偷偷换算。正压力方向与参考Segment法向相反；每个Segment的方向记录在本地报告。二维边要求XY连续体边界，SECTION_SHELL为12/13/14/15；不把普通薄壳边当二维实体边界。三维面不强制为模型外表面，允许明确指定的面载荷。

拒绝空集、非法/不增时间、非有限数值、曲线/表/函数ID冲突、载荷ID冲突以及同一集重复压力。曲线点读回允许2e-6相对误差、零绝对容差，但不能把原本不同的时间读成同一时刻。原始请求、实际读回、最大误差和方向报告留在任务目录；大型曲线不重复塞进MCP摘要。

## 无反射边界

`create_gui_nonreflecting_boundary` 要求显式维度、目标求解器版本和坐标单位。求解器版本与LS-PrePost版本是两个独立条件。

| 路线 | 生成方式 | 关键检查 |
|---|---|---|
| 三维，手册目标R11–R16 | BOUNDARY_NON_REFLECTING引用Segment集 | 线性Hex8/Tet4唯一外表面；两种面片绕序均可；AD/AS参数读回 |
| 二维，R14–R16 | BOUNDARY_NON_REFLECTING_2D以负NSID引用Segment集 | XY连续体13/14/15公式；有向边界逆时针 |
| 二维，R11–R13 | 由每条边创建独立有序两节点集，再以正NSID引用 | 必须给node_set_start_id；逐ID检查冲突，逐对核对原生节点顺序；只提供旧手册默认的两类波同时启用 |

API的dilatational/shear使用布尔语义，底层AD/AS为0表示启用。普通节点集接口会按集合语义整理成员，不能替代旧版无反射边界需要的有序节点链；专用路线保留逆序ID的边，并在原生读回与重开后核对。多个条件即使引用不同集合ID，只要覆盖同一拓扑面/边也会被拒绝。

这里不自动调整材料、动态松弛、时间步或非线性区域，也不计算吸收效果。其适用假设与物理响应仍由模型和求解器决定。目标版本当前限已采用的R11–R16手册范围；其他版本、不支持的集合/单元变体、非匹配网格交界及整域ALE空卡形式需要另验。

## 验收与依据

`tools/run_boundary_creation_acceptance.py` 在最大化可见4.13.4通过39个阶段：选择建面、压力与倍率回放、多个命名载荷、ID冲突/重复压力、跨集合无反射重叠拒绝、反向三维面、二维负SID、有序节点集分配冲突与逆序ID保留、旧新二维路线保存重开，以及薄壳公式拒绝。合成原文件未变。没有启动LS-DYNA求解器；“R11路线”表示按该手册组织并经LS-PrePost读写核对，不是R11求解验收。

规则来源：[R11关键词手册](https://lsdyna.ansys.com/wp-content/uploads/2026/08/LS-DYNA_Manual_Volume_I_R11.pdf)、[R16关键词手册](https://lsdyna.ansys.com/wp-content/uploads/2026/08/LS-DYNA_Manual_Vol_I_R16.pdf)的LOAD_SEGMENT/SET、BOUNDARY_NON_REFLECTING/2D章节，以及[R14发布说明](https://lsdyna.ansys.com/ls-dyna-r14-0-0-released-2023-05/)。本地只保存阅读与验收证据，仓库不分发厂商手册或用户模型。
