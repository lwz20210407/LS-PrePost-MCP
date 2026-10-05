# 选择驱动的规定运动

所属 model / selection / checks，T12-ENTITY，WF-MESH 与 WF-AUTO。Windows 4.13.4 可见最大化GUI已完成限定验收；创建方式为PyDYNA目标片段生成及LS-PrePost原生导入/导出，不代表整个Entity Creation面板或求解器物理验证完成。

## 输入合同

`create_gui_prescribed_motion` 支持节点集SID、节点ID列表、同会话成功节点选区 `selection_job` 三选一。创建 `BOUNDARY_PRESCRIBED_MOTION_NODE_ID` / `SET_ID`；轴为 x/y/z/rx/ry/rz，类型为 displacement/velocity/acceleration。普通节点集当前须为显式LIST，单次最多20000目标节点，是操作预算而非模型大小限制。

传入 `points` 和 `curve_title` 时创建新的普通瞬态 `DEFINE_CURVE`，最多10000点；省略两者时复用已有普通曲线。新曲线ID必须不与curve/table/function命名空间冲突。复用要求DATtyp=0、原始横坐标严格递增、有效横坐标倍率为正，保留原有曲线倍率、偏移与其他属性，不隐式重采样。

`time_unit` 和 `length_unit` 是用户声明的模型单位；输入数值须已经使用这些单位。平动量分别为长度、长度/时间、长度/时间²；转动量使用弧度、弧度/时间、弧度/时间²。本接口不自动换算，也不能由k文件自动验证整个单位体系。若用户数据单位不同，先显式换算再建卡。

`BIRTH` 平移运动曲线时间原点；`DEATH=0` 按原生语义视为1e28默认值，必须晚于BIRTH。工具保留请求倍率和时段并从原生导出读回；没有把BIRTH仅解释为开关时间。

`motion_id` 是运动分组ID，LS-DYNA不要求它在运动记录之间唯一。本次调用的多个节点共享此ID。已有同名分组需显式 `append_to_group=True` 才能追加；这不绕过节点/自由度冲突检查。该构建导入带逗号的运动heading会改变文字，因此提前拒绝逗号，保留其余已验证ASCII标题；不自动改写标题。

## 引用与冲突

- 新运动检查已有全局SPC、已解析的全局运动和NODE的TC/RC约束；新SPC也检查已有运动。
- TC/RC是枚举编码，不是二进制掩码：例如TC3为Z，TC4为X/Y，TC6为Z/X。只流式记录非零节点约束，不保存全量坐标副本。
- 重叠节点、相同自由度的运动拒绝；不同自由度可共存。非全局SPC坐标系重叠保守拒绝，未实现坐标变换或互斥时段组合证明。
- 被运动引用的节点集替换成员时，重新检查SPC/运动冲突；未解析相关约束变体拒绝修改。
- 刚体、材料约束、CNRB、接触及其他消费者的完整物理相容性未认证；转动自由度在目标节点是否实际可用仍由模型/求解器决定。向量、局部、刚体、IGA、自适应集合变体另行开发。

每次事务有检查点、节点登记读回、网格与显隐保持核对、曲线/运动卡片比较及独立JSON读回文件。数值读回相对容差2e-6，零值不靠大绝对容差放行。原文件不变；这里比较原生导出中的逻辑卡片与哈希，不宣称Include结构或原始排版字节保真。

## 原生验收

`tools/run_prescribed_motion_acceptance.py` 验证BySet→Node Set→规定运动、直接节点选区→运动、换集合/节点/曲线幅值回放、三个运动类型与六个轴向、显式共享分组追加、SPC双向冲突、过期选区、缺曲线/节点、集合变更冲突、保存及同进程原生重开。最终16条运动记录及曲线保持。可选 `--public-keyword` 用已知旧版不支持的案例验证部分导入拒绝与显式重启检查点恢复。

`tools/run_public_motion_acceptance.py` 使用官方 `load_body.shell.k`（6节点、2壳）：已有两条无ID的RY速度记录、NODE内联约束、新增节点3的Y位移、原曲线/卡片保持和**显式新进程重开**通过。`--same-session-replace` 是保留的未通过稳定性诊断分支，见[已知原生问题](NATIVE_KNOWN_ISSUES.md)，不能把新进程验收冒充原位替换通过。

另一官方旧例 `constrained.linear.plate.k` 在本机报告无效 `CONSTRAINED_LINEAR` 并跳过数据；即使81节点/64单元读出正确，也必须判定载入失败。即时及迟到回执使用相同错误检查，源身份/代际不推进。未修改原例来伪造通过。

## 依据

- [R16 Volume I](https://lsdyna.ansys.com/wp-content/uploads/2026/08/LS-DYNA_Manual_Vol_I_R16.pdf)：本地选读PDF749–760页规定运动、3485–3487页NODE约束；ID分组、BIRTH/DEATH、DOF/VAD、TC/RC据此核对。
- [官方广义载荷壳算例](https://lsdyna.ansys.com/generalized/)与[旋转壳示例](https://lsdyna.ansys.com/shell/)：已有普通节点规定运动与曲线，用于原始格式兼容性检查。
- PyDYNA0.12.1的生成类作为片段构造接口，原生导出独立解析验证；不把生成类存在当作原生验收。

厂商手册、下载模型、原生日志与测试产物只留本地。
