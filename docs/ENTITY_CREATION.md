# 选择与 Entity Creation 完整流程

2026-10-03 用户再次确认的核心前处理要求，列入首个实用版本验收，不以通用关键字编辑、目录条目或网格实体创建代替。

所属模块：selection / model / checks；工作项 T12-ENTITY；主流程 WF-MESH，可由 WF-AUTO 录制复用。已有 `create_gui_nodes`、`create_gui_elements` 创建的是网格节点/单元，并不意味着 Entity Creation 面板全部实现。

## 资料核对与落地顺序

本地已读取 2026 R1 用户指南 §6.2.3（印刷页408–411）、§6.2.3.14.21–22 Set Data / Sample（475–480）、§6.2.3.14.24 SPC（482起）。前者明确把集合、约束、载荷等分为不同实体族；不公开厂商手册正文。示例段落存在面板命名疑似不一致，操作顺序必须实机核对，不盲抄。

公开原始来源：

- [官方通用选择器帮助](https://lsdyna.ansys.com/selection/)：选择工具供其他面板复用，区分 BySet、BySegm、3Dsurf、Prop/Ang 等；这些按钮存在不代表仓库已封装。
- [官方 SPC 创建教程](https://lsdyna.ansys.com/p5-spc1/)：演示区域选择节点并建立约束。网页是旧界面流程参考，不能当作4.13命令串证据。
- [Ansys 支持论坛：节点集约束路径](https://innovationspace.ansys.com/forum/forums/topic/boundary-constraint-to-fix-node-set-all-dof-0/)：说明先建立节点集再由 SPC_SET 引用的流程，仍需当前构建验证。
- [2026 R1 官方教程](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/pdf/LS-DYNA_LS-PrePost_Tutorials.pdf)：检索到 IC/BC 与边界条件示例，后续按案例逐页核对，尚未声称全部阅读/执行。

| 验收项 | 输入与完整流程 | 必须验证 | 当前状态 |
|---|---|---|---|
| EC01 节点集与 Part 集 | 已验证的节点/部件选区 → 创建命名集合 → 查询、修改、保存重开 | 真实成员ID、空集策略、同类集合ID冲突、未选成员不混入 | 4.13.4 LIST集合限定闭环通过，见下文 |
| EC02 三维 Segment 集 | 标准实体外表面或显式壳面 → 定向面片集合 | 三角/四边节点顺序、重复/内部面、面积、朝向；不可只拿单元ID当面 | 4.13.4 Hex8/Tet4及Quad4壳面限定原生闭环通过，见SEGMENT_SETS.md |
| EC03 二维边界 Segment | 指定二维网格边界 → 有方向的边界段 | 原生卡片格式、端点顺序、平面/轴对称适用规则；不复用三维面片假设 | 4.13.4 XY二维边界闭环通过；边界条件适用性另验，见SEGMENT_SETS.md |
| EC04 SPC 约束 | 节点/节点集 → 显式平动与转动DOF、坐标系 → 约束卡 | 集合引用、DOF、重复/冲突约束；不自动把所有DOF固定 | 4.13.4 全局SPC_SET/NODE_ID限定闭环通过，非求解验证 |
| EC05 压力载荷 | Segment 集 + 用户给定载荷曲线/倍率/单位 → 载荷 | 曲线与集合引用、符号/法向、时间与压力单位、未请求面不受载 | 4.13.4限定原生闭环通过，见BOUNDARY_CONDITIONS.md |
| EC06 无反射边界 | 二维/三维适用边界 → 对应原生条件 | 对应关键字、适用单元、边界法向和参数；建卡/重开不等于求解吸收效果验证 | 三维、二维负SID和旧版有序节点集路线的原生闭环通过；未做求解吸收验证 |

每项提供合成正常例和至少一个错误例。完成流程是：选择并读回实际ID → 参数/实体作用域预检 → 检查点 → 原生创建 → 查询成员/卡片引用 → 保存 → 原生重开 → 复核。创建方式必须标注原生命令/面板或受控原生 keyword fragment 导入，后者不能宣传成已覆盖面板所有操作。

集合从当前选区创建时必须携带模型身份和实体域；实体/集合ID不混用，模型改变后拒绝过期选区。二/三维 Segment 的规则在手册和实机核实之前，不输出猜测命令。

## 先修选区基础

本批实机发现 `pall` 会重置 Blank；`genselect ... add part` 在存在 Blank 时还会遗漏隐藏单元连接的节点。因此先保护显示现场，并在有隐藏实体时用明确ID选区验证。不能用“选择命令执行成功”替代集合成员正确性。

完整场景恢复仍单列：keyword 检查点不保存 Blank，录制回放若需要保留显示场景，必须记录显隐设置步骤。

## 本批实现接口

### 2026-10-05：Shell / Solid / Beam 显式集合

在已有 `create_gui_entity_set` / `inspect_gui_entity_sets` 中增加 `entity_type=shell|solid|beam`。仍可用显式用户ID或同会话、同模型代次、同实体域的选择结果；不会把节点ID或一个笼统的element选区当作特定单元域。

布局按R16 Volume I的SET章节核对：Shell为SID+DA1–DA4；Solid为SID+SOLVER及版本相关ITS（新建MECH，ITS留默认0）；Beam只有SID。新建片段采用每行8个成员的10列定宽格式，原生导出再独立解析；本机PyDYNA `SetSolid` 的固定k1–k8接口不能作为任意长列表的正确性依据，因此这里使用受控目标片段，不全量重写原模型。

4.13.4可见GUI合成验收：每类12个稀疏单元ID，同SID=41的节点/Shell/Solid/Beam集合共存；保留隐藏实体状态及完整网格。随后录制回放把三类成员改为各自末3个、SID改为42，选择结果依赖自动传到集合创建；保存重开后成员和其余原生卡片一致。分页、错域ID、同域SID碰撞、错类型选区、重开后的旧选区均有验证。27步通过，源文件未变；全套590项测试通过。

可复现入口：`tools/run_element_set_acceptance.py --workspace <本地测试目录> --executable <LS-PrePost路径>`。该验收只创建并关闭自己拥有的会话。

边界：新增三类当前支持create/query，不开放 `replace_members`；集合成员变化会影响载荷、接触、截面等消费者，必须补引用影响分析。Generate/General/Add/Collect/Column、Discrete/Seatbelt/ThickShell、Include和求解器物理验证未由本批认证。每次最多20000成员，不是全模型网格上限。

### 按已有集合选择，并传给Entity消费者

`select_gui_entities` 新增 `set_ids`，与 `entity_ids`、`part_ids` 三选一；指定node/part/shell/solid/beam域。多个集合取成员并集，再应用现有 `scope` 和 `invert`。集合SID不等于实体ID；不使用含义不确定的通用element域。`set_ids`非空，已有空列表集可以产生空选区；未识别变体不会默默展开。

解析与选择共用一个会话请求锁：先从当前keyword模型临时原生导出集合，再查询当前实体登记、执行选择并核对准确ID、完整网格和显示状态。证据包含集合编号、各集合成员数、去重并集数及导出来源指纹。额外原生全模导出有I/O成本，但不会将它登记为新的受管检查点或清除dirty标志；这不是无导出的快速数据库API。

4.13.4可见GUI已验证五类列表集、跨集并集、Part域反选、隐藏单元仍按all作用域选择、缺集合拒绝，以及BySet→新节点集→SPC的换集合回放。修改源集合成员后重新选择得到新成员；保存重开后源集合与消费者集合成员分别正确。`tools/run_set_selection_acceptance.py`提供完整复现流程，源文件保持。

仅认证当前keyword显式列表集；不隐式关联d3plot与keyword，不认证Generate/General/Collect或Segment面选择。union最多20000成员（非全模大小限制）。录制保留集合编号，回放重新解析成员；旧桥缺少登记查询读回时拒绝，不退化成全选。

- `create_gui_entity_set`：`entity_type=node|part`，`mode=create|replace_members`。从显式实体ID或同会话 `selection_job` 创建 `SET_NODE_LIST` / `SET_PART_LIST`；新建拒绝ID冲突，替换要求已有集合，保留DA、solver、ITS属性。成员最多20000，不是整个模型大小上限。只允许明确支持的列表集合；同域其他集合变体未解析时拒绝操作。
- `inspect_gui_entity_sets`：从原生临时导出读取集合名称、属性、数量及分页成员；不改受管检查点归属。未知集合变体显式报告，不能作为空集合。
- `create_gui_spc`：`node_set_id`或`node_ids`二选一；六个显式0/1自由度按X/Y/Z/RX/RY/RZ排列，坐标系0为全局。SPC_SET使用给定约束ID；多个单节点约束按节点ID排序，从给定ID开始连续分配，每个节点一张原生SPC_NODE_ID卡，返回对应关系并检查全部ID冲突。原生4.13导入一张多行SPC_NODE_ID时只保留了第一条，因此不能使用这种格式批量建约束。

三个接口使用已有的受管会话、事务、检查点、原生 keyword fragment 导入/导出和工作流。仅解析目标实体卡，不用PyDYNA全量重写原模型。对比完整网格摘要、状态、显示标志、其他原生导出卡片及目标成员/约束引用；源模型保持不变。原生完整导出仍有I/O成本，不是增量Include保存引擎。可打印ASCII名称最长70字符；Unicode标题、其他集合变体、完整约束物理相容性仍需另验。

选择源必须是当前拥有会话中的成功选择，并核对模型加载代次、几何身份和状态。重开同一几何也使旧选择源失效。录制时把选择任务引用转换成前一步结果依赖；未录到选择来源的记录标记需审阅，避免回放使用旧任务路径。

SPC冲突检查覆盖受支持SPC卡的实际节点重叠、自由度、坐标系及约束ID；已有未解析SPC/规定运动卡会阻断创建。节点集替换会检查关联SPC是否引入新的重叠。这里不认证刚体/材料约束、运动时间段或求解器物理适用性，也不隐式固定全部自由度。非零坐标系引用有代码检查，当前原生验收以全局系为限。

列表成员采用明确的10列定宽或逗号语法解析，避免已复现的PyDYNA SeriesCard逗号行截断；只剔除空列和0占位，不吞掉尾部成员。其他原生卡片以去注释、保留数据行的哈希比较，不能宣传成用户原文件字节保真。

可复用验收入口：`tools/run_entity_creation_acceptance.py`。2026-10-04 在最大化可见4.13.4中通过混合壳/实体/梁、Blank保持、选区建节点/Part集、SPC_SET、换选区及SID参数回放、分页查询、成员替换与DA属性保留、多节点SPC_ID映射、ID/节点/坐标系/旧选区/重复约束/修改引入冲突的拒绝，以及原生保存重开后的集合、SPC和其余卡片一致性。合成源文件字节未变。失败探查与成功日志均只存本地；公开驱动不含用户模型。

原生SPC_ID导出还会把多个“ID/名称+自由度行”连续写在同一keyword块中；专用读回解析器按成对记录读取，并用包含逗号的名称与截断反例测试，避免把后续约束当作丢失。本三个接口的验收不能替代其他接口的验收；Segment、压力和无反射边界已有的各自限定证据，分别见[Segment集合](SEGMENT_SETS.md)与[边界条件](BOUNDARY_CONDITIONS.md)。
