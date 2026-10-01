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

## 可见结果会话选择（T04/A03）

keyword 与 d3plot 会话现共用 EntitySelection（真实用户 ID）及原生选择验证。允许节点、单元、部件 ID、部件关联节点和参考坐标谓词；保持当前结果时刻，逐项核对坐标、连接、部件成员和最终选区。切换时刻后可恢复模型指纹一致的节点缓冲区。结果会话仍拒绝网格修改。

4.13.4 可见 GUI 的代表性结果副本已通过 8 项验收：节点 ID、实体单元 ID、部件 ID、部件关联节点、保存缓冲区、清空、切换时刻后恢复、参考球形区域。原文件族哈希前后相同，没有导出 keyword 检查点。测试工具为 `tools/run_result_selection_acceptance.py`，必须指定私有工作目录与授权源文件；结果数据、ID、图片和日志不公开。

按部件选择在预检确认实体集合一致后使用原生批量命令，避免大量逐节点命令；依然核对完整原生 ID 集合。已证明几何不变的选区/时刻不一致会报告失败并保留模型可用状态，未知模型变化继续标为 uncertain。

范围仍有限：最多 20000 节点/单元；坐标为参考配置；没有 alive/deletion 掩码、变形空间选择或跨模型映射。梁域及完整材料层/历史语义未获得新增原生认证。

### 部件显隐范围（A04）

`select_gui_entities(scope="all")` 包含隐藏部件，完成后恢复并核对原有部件活动标志。`scope="active_parts"` 以操作前活动部件及其连接为范围；节点共享于活动/隐藏部件时仍纳入，孤立节点不纳入。显式 ID 仍先验证存在性，再与范围求交；反选只在范围内进行。它不表示屏幕像素可见、逐单元隐藏、遮挡裁剪或有效/失效过滤。

共用选择、空间谓词、布尔集合和缓存保存/加载验证部件显隐不变；没有完整读回标志的旧会话会在发命令前拒绝，需重启受管会话加载新桥接代码。4.13.4 合成双部件的 9 项验收，以及结果副本的 11 项验收通过（后者增加隐藏部件全域选择、活动部件过滤和隐藏节点缓存恢复）。并非所有显示模式均已覆盖。

剩余：完整 ModelRef、GUI 选择到场提取/云图的统一绑定、量纲与列级单位、history 变量字典、坐标转换/平均、有效单元掩码与可见 GUI 后处理适配。

## 选区到原生节点历史与工程曲线（T07/WF-POST）

`extract_node_history` 仍输出原有 nodal.csv，新增可选 `curve_components=["x","y","z","magnitude"]`（按需选取）和显式 `time_unit`。每个节点/分量另存标准 `time,value` 曲线，返回 `data.curves`，可直接绑定给 `combine_history_curves`。最多 100 条标量曲线；至少两个递增状态且物理时间严格递增；位置的 magnitude 被拒绝，不能冒充位移。

节点向量也携带 FieldSpec、用户 ID/状态和原生分量来源；单位仍是调用者标签，未推断量纲。GUI 工作流中的 `extract_node_history` 自动走同一会话，并非额外后台 LSPP。先停止动画，提取后通过原生命令恢复原时刻并单独读回确认；不自动重新播放动画。独立批处理仅报告恢复请求，不能冒充已验证的 GUI 恢复。

可复用三步模板见 [visible_gui_relative_displacement.json](../examples/workflows/visible_gui_relative_displacement.json)：选择 → 节点历史 → 第一个选中节点减第二个选中节点。选择 ID 以升序返回，差值正方向因此明确按升序 ID 定义；它不是任意轴投影、随动参考系或自动应变计。必须提供恰好两个节点、状态列表、结果单位和共同时间单位。

`tools/run_gui_post_workflow_acceptance.py` 在代表性私有结果副本上连续执行两个分量版本，各三步；曲线逐点相减、原生位置减参考坐标与原生位移的恒等关系、时刻/选区/几何/显隐保持、原文件族哈希和零 keyword 导出均核对通过。测试使用未知模型单位标签，不据此认证实际单位或材料响应。

实测发现 Python 回调内的 `switch_state` 不能作为 GUI 显示完成证据，且状态读取会改变工作目录。GUI 状态切换改用外部命令流的绝对 `state N` 并读回确认；曲线使用任务绝对路径。旧版 Python 向量 ABI 仍被阻止，未因本批 4.13.4 通过而放开。

## 同一可见 GUI 的 SCL 场与六分量应力

`gui_session_action` 现支持 `action="extract_native_fields"` / `"extract_native_stress"`；参数沿用原工具但省略 `path`，使用当前已暂存的 d3plot。工作流在提供 session_id 时自动使用这一通道；独立调用原工具仍是原来的暂存批处理通道。GUI 请求显式传入 path 会被拒绝，避免误解为重开其他结果。

两条通道复用字段白名单、FieldSpec、SCL 生成、完整 ID×状态矩阵校验以及应力解析。GUI 通道不执行 new/open/exit、不启动额外 LSPP；核对前后参考网格、连接、部件成员、选区、活动标志和原时刻。SCL 诊断或上下文不一致会失败，未知模型变化将会话标为 uncertain。当前验证仍依赖完整快照，上限 20000 节点/单元；不支持快照尚未覆盖的单元族。

4.13.4 代表性实体结果已验：选择 → 原生 SCL 六应力分量及 Mises → Python 三轴度/Lode 派生与原生 Mises 对照；另外导出六个应变分量和等效塑性应变。应变输出保留原生约定，未声明工程剪应变/材料坐标/平均方式的额外解释；壳层、厚壳和特殊实体仍需分别实测。GUI 完成验证使用应用内 Python，因此不能把批处理 SCL 的“不依赖 Python”标签照搬过来。

应力工作流已通过托管录制 → 将 states 参数化 → 原生重开暂存结果 → 同一 GUI 回放，录制的上下文检查也保留。公开 [visible_gui_selected_stress.json](../examples/workflows/visible_gui_selected_stress.json) 提供选择到应力的两步模板，必须填写 element_ids、states、units；默认实体 solid 与原生 default/mid，不代表壳层已获得此次认证。

本机构建的 SCL 加载器要求 Windows 原生反斜杠路径；正斜杠盘符路径会被错误拼接到已有打开目录。路径修复仅作用于专用 SCL 命令，不修改用户配置；生成的 SCL 输出使用明确绝对路径。原命令接口参考仍见 [官方说明](https://lsdyna.ansys.com/command/)，运行结论以此处指定构建实测为准。
