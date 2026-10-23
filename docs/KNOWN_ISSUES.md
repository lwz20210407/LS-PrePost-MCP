# 当前限制与已知原生边界

本页列当前未完成的边界、平台限制和必要规避；每节关联任务。
历史修复、能力原文、驱动注释和扫描哈希保留在 [清理前快照](archive/2026-10/known-issues-before-review02.md)。
能力入口查 [工具目录](TOOLS.md) 和 [运行时范围元数据](../src/ls_prepost_mcp/data/capabilities.json)，验收范围查 [任务目录](TASKS.md) 与各 evidence/report.md。
历史原生记录只对应登记的构建、来源与语料，不外推为当前全面认证。

## KI-001 SELECT-BLANK

- 跟踪：G02 / G03

- 现象：pall 重置单元 Blank；by-part 节点选择会遗漏 Blank 单元上的节点。
- 版本：4.13.4
- 规避：避免 pall；只临时恢复必要部件，以真实 ID 选择并核对显示标志。
- 来源文档：[ENTITY_CREATION.md](archive/2026-10/ENTITY_CREATION.md)
- 证据：[原文及其验收范围](archive/2026-10/ENTITY_CREATION.md)；[复现驱动](../tools/run_selection_scene_acceptance.py)

## KI-002 SELECT-MODEL

- 跟踪：G03 / I01

- 现象：genselect 固定 /0 模型后缀在模型重开后选错或选不到。
- 版本：4.13.4
- 规避：面向当前模型使用无固定后缀 ID；读回集合与坐标。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)

## KI-003 SELECT-BUFFER

- 跟踪：G03

- 现象：Buffer 界面编号从 1 开始，命令索引从 0 开始；模型变更后旧缓存失效。
- 版本：4.13.4
- 规避：Buffer3 对应 genselect save 2；读回真实成员和模型身份。
- 来源文档：[TUTORIAL_INTEGRATION.md](archive/2026-10/TUTORIAL_INTEGRATION.md)
- 证据：[原文及其验收范围](archive/2026-10/TUTORIAL_INTEGRATION.md)

## KI-004 MODEL-NAMESPACE

- 跟踪：I01

- 现象：Model Selection 行号与 Remove 显示编号不同；移除非活动模型也可能改变活动模型。
- 版本：4.13.4
- 规避：刷新清单；选择使用行号、移除使用显示编号，操作后核对实际来源。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)；[复现驱动](../tools/run_model_inventory_acceptance.py)

## KI-005 MODEL-PATH

- 跟踪：I01

- 现象：保存或切换后 model_directory 与模型列表路径可变成最新检查点位置。
- 版本：4.13.4
- 规避：接受有会话归属和哈希证明的检查点别名；不凭相邻路径认同模型。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)；[复现驱动](../tools/run_resident_activation_acceptance.py)

## KI-006 MODEL-STALE

- 跟踪：I01

- 现象：结果→keyword 打开报 Invalid entity ID 后可能仍读到旧结果计数。
- 版本：4.13.4
- 规避：增量日志、输入路径和模型代际一起校验；失败不推进来源。
- 来源文档：[MODEL_REPLACEMENT.md](archive/2026-10/MODEL_REPLACEMENT.md)
- 证据：[原文及其验收范围](archive/2026-10/MODEL_REPLACEMENT.md)；[复现驱动](../tools/run_stale_model_regression.py)

## KI-007 MODEL-RESULT-SWITCH

- 跟踪：I01

- 现象：结果直接切换结果、或结果活动时卸载另一结果曾退出或失去响应。
- 版本：4.13.4
- 规避：使用已验证 resident keyword 中间模型；缺中间模型时拒绝。
- 来源文档：[MODEL_REPLACEMENT.md](archive/2026-10/MODEL_REPLACEMENT.md)
- 证据：[原文及其验收范围](archive/2026-10/MODEL_REPLACEMENT.md)；[复现驱动](../tools/run_model_replacement_acceptance.py)

## KI-008 NATIVE-REPLACE-001

- 跟踪：I01

- 现象：官方 load_body.shell.k 在同进程替换后导出时退出；完成计数回执后仍可能保存失败。
- 版本：4.13.4
- 规避：保留检查点并显式新建进程恢复；卸载后实际导出检查提前暴露故障，不自动重试。
- 来源文档：[NATIVE_KNOWN_ISSUES.md](archive/2026-10/NATIVE_KNOWN_ISSUES.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_KNOWN_ISSUES.md)；[复现驱动](../tools/run_public_motion_acceptance.py)

## KI-009 NATIVE-LOAD-002

- 跟踪：I01

- 现象：CONSTRAINED_LINEAR 被报无效并跳过；81 节点/64 单元计数仍可能正确。
- 版本：4.13.4
- 规避：把跳读纳入失败判据；原例保留作负例。
- 来源文档：[NATIVE_KNOWN_ISSUES.md](archive/2026-10/NATIVE_KNOWN_ISSUES.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_KNOWN_ISSUES.md)；[复现驱动](../tools/run_prescribed_motion_acceptance.py)

## KI-010 MASS

- 跟踪：Q11

- 现象：标准 ELEMENT_MASS 曾使总单元计数校验失败；标准质量保真已修复，glyph、惯性等未认证。
- 版本：4.13.4
- 规避：读取原生导出、质量/节点/PID摘要与 SDK 计数；未支持族继续拒绝。
- 来源文档：[MASS_PRESERVATION.md](archive/2026-10/MASS_PRESERVATION.md)
- 证据：[原文及其验收范围](archive/2026-10/MASS_PRESERVATION.md)；[复现驱动](../tools/run_mass_preservation_acceptance.py)

## KI-011 BEAM-HEAP

- 跟踪：I01 / P08

- 现象：梁 element_connectivity 数组读取复现堆损坏，SCL 数组实验也失败。
- 版本：4.13.4
- 规避：GUI 导出新 keyword 后读标准梁端点；独立 batch 梁连接仍拒绝。
- 来源文档：[GUI_VISIBILITY.md](archive/2026-10/GUI_VISIBILITY.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_VISIBILITY.md)

## KI-012 PYTHON-ABI

- 跟踪：I01 / A04

- 现象：旧内置 Python 向量值未通过数值对照；标量程序通过不能解除该限制。
- 版本：4.10
- 规避：阻止旧 ABI 原生向量；显式使用 4.13 或标明读取器后端。
- 来源文档：[COMPATIBILITY.md](COMPATIBILITY.md)
- 证据：[原文及其验收范围](COMPATIBILITY.md)

## KI-013 SOLID-IP

- 跟踪：Q03

- 现象：请求实体积分点 8 时返回点 1 张量，full-integration 标志不足以证明正确。
- 版本：4.13.4
- 规避：原生实体选择器 2–8 前置拒绝；default/point1 与读取器槽位分开。
- 来源文档：[RESULT_VALIDITY.md](archive/2026-10/RESULT_VALIDITY.md)
- 证据：[原文及其验收范围](archive/2026-10/RESULT_VALIDITY.md)；[复现驱动](../tools/run_result_validity_acceptance.py)

## KI-014 LASSO-DISPLACEMENT

- 跟踪：Q05

- 现象：node_displacement 数组是状态坐标，直接返回会把初始位置当位移。
- 版本：LASSO 2.0.4
- 规避：先减 reference coordinates；与 LS-Reader 交叉核对。
- 来源文档：[BACKENDS.md](archive/2026-10/BACKENDS.md)
- 证据：[原文及其验收范围](archive/2026-10/BACKENDS.md)

## KI-015 LASSO-SHELL

- 跟踪：Q03

- 现象：复材鸟撞读取出现 n_shell_vars 不匹配和塑性应变 reshape 错误。
- 版本：LASSO 2.0.4
- 规避：显式暴露读取警告；节点/状态数不能证明场数组正确。
- 来源文档：[UI_AUDIT_POST_GAPS.md](archive/2026-10/UI_AUDIT_POST_GAPS.md)
- 证据：[原文及其验收范围](archive/2026-10/UI_AUDIT_POST_GAPS.md)

## KI-016 MPP

- 跟踪：Q06

- 现象：当前 binout 入口拒绝 MPP 分片，不能只读一个分片当完整结果。
- 版本：当前适配器
- 规避：Q06 实现合并前使用已核实单文件语料；缺口明确报告。
- 来源文档：[BACKENDS.md](archive/2026-10/BACKENDS.md)
- 证据：[原文及其验收范围](archive/2026-10/BACKENDS.md)

## KI-017 SCL-PATH

- 跟踪：I03 / A03

- 第六轮复核：统一 UTF-8 字面量仍须为 SCLBinoutOpen 保留 Windows 反斜杠，正斜杠绝对路径对照失败；修正后公开 Binout 数值对照通过。见 [SCL 路径证据](decisions/evidence/i03-scl-literals/report.md)。

- 现象：runscript/SCLBinoutOpen 对正斜杠 Windows 绝对路径解析错误。
- 版本：4.13.4
- 规避：原生命令使用转义后的反斜杠路径，SCL 输出用明确绝对路径。
- 来源文档：[POSTPROCESSING.md](archive/2026-10/POSTPROCESSING.md)
- 证据：[原文及其验收范围](archive/2026-10/POSTPROCESSING.md)；[复现驱动](../tools/run_gui_binout_acceptance.py)

## KI-018 SAVE-PATH

- 跟踪：I03 / P11

- 现象：部分批处理构建给绝对 keyword 输出路径加临时前缀；GUI 开模型又会漂移 cwd。
- 版本：4.10/4.13，路径策略依适配器
- 规避：批处理固定 cwd + 相对文件名；持久 GUI 使用经验证绝对 Windows 路径；核对实际新产物。
- 来源文档：[VERIFICATION.md](archive/2026-10/VERIFICATION.md)
- 证据：[原文及其验收范围](archive/2026-10/VERIFICATION.md)；[复现驱动](../tools/run_node_replacement_acceptance.py)

## KI-019 RESULT-CWD

- 跟踪：I01 / Q01

- 现象：长路径加载曾访问违规；GUI 偏好可能恢复工作目录。
- 版本：4.8/4.10/4.13 的已记载样例
- 规避：结果父目录按文件名加载或有界暂存，再恢复 job cwd。
- 来源文档：[COMPATIBILITY.md](COMPATIBILITY.md)
- 证据：[原文及其验收范围](COMPATIBILITY.md)

## KI-020 STATE

- 跟踪：Q01 / Q03

- 现象：Python 回调内 switch_state 不能证明 GUI 显示已切换，读状态还会改变 cwd。
- 版本：4.13.4
- 规避：外层命令流使用 state N 并读回；曲线输出使用绝对路径。
- 来源文档：[RESULT_CONTRACTS.md](archive/2026-10/RESULT_CONTRACTS.md)
- 证据：[原文及其验收范围](archive/2026-10/RESULT_CONTRACTS.md)；[复现驱动](../tools/run_gui_post_workflow_acceptance.py)

## KI-021 VIEW-SAVE

- 跟踪：G01

- 现象：view save 在没有命名视图时无数据；加载视图还可追加外观/颜色。
- 版本：4.13.4
- 规避：先创建命名视图，再保存/恢复并比较图像；跨进程书签仍待验。
- 来源文档：[GUI_CAMERA.md](archive/2026-10/GUI_CAMERA.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_CAMERA.md)；[复现驱动](../tools/run_gui_camera_acceptance.py)

## KI-022 NEW-SESSION

- 跟踪：I01

- 现象：new 在部分 GUI 状态下被解释为重启并弹确认框。
- 版本：4.13.4
- 规避：不把 new 当受管 GUI 启动命令。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)

## KI-023 GUI-DESKTOP

- 跟踪：I01

- 现象：命令框与对话框驱动依赖未锁定桌面，首次安装可能弹初始化设置。
- 版本：Windows 4.13.4
- 规避：当前驱动先检查桌面；E5 分别验证锁屏/RDP，不能推断两者相同。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)

## KI-024 GUI-CONTROLS

- 跟踪：I01

- 现象：部分控件 ID 与英文菜单仅在当前构建录制，其他构建不可直接套用。
- 版本：4.13.4
- 规避：按版本探测与读回；ui_entry 需截图审计。
- 来源文档：[MCP_TOOL_PROFILES.md](archive/2026-10/MCP_TOOL_PROFILES.md)
- 证据：[原文及其验收范围](archive/2026-10/MCP_TOOL_PROFILES.md)

## KI-025 SPC-ROWS

- 跟踪：P05

- 现象：原生多行 SPC_NODE_ID 导入曾截断；标题/数据映射也需单独核对。
- 版本：4.13.4
- 规避：每节点单独具名卡，读回完整 ID/DOF/引用。
- 来源文档：[ENTITY_CREATION.md](archive/2026-10/ENTITY_CREATION.md)
- 证据：[原文及其验收范围](archive/2026-10/ENTITY_CREATION.md)；[复现驱动](../tools/run_entity_creation_acceptance.py)

## KI-026 MOTION-TITLE

- 跟踪：P05

- 现象：含逗号的规定运动 heading 导入会改变文字。
- 版本：4.13.4
- 规避：前置拒绝逗号，保留已验证 ASCII 标题；共享分组 ID 不等于节点 DOF 无冲突。
- 来源文档：[PRESCRIBED_MOTION.md](archive/2026-10/PRESCRIBED_MOTION.md)
- 证据：[原文及其验收范围](archive/2026-10/PRESCRIBED_MOTION.md)；[复现驱动](../tools/run_prescribed_motion_acceptance.py)

## KI-027 NR-ORDER

- 跟踪：P05

- 现象：二维旧版无反射边界需要有序节点链；普通集合排序会改变边方向。
- 版本：LSPP 4.13.4 读写；LS-DYNA R11–R16 文档
- 规避：旧路线保留两节点顺序；新版负 SID 与旧版正节点集路线分开。
- 来源文档：[BOUNDARY_CONDITIONS.md](archive/2026-10/BOUNDARY_CONDITIONS.md)
- 证据：[原文及其验收范围](archive/2026-10/BOUNDARY_CONDITIONS.md)；[复现驱动](../tools/run_boundary_creation_acceptance.py)

## KI-028 SEGMENT-TOPOLOGY

- 跟踪：P04

- 现象：共节点外表面筛选不等于非匹配网格相交检测；局部选区共享面不能当外表面。
- 版本：4.13.4
- 规避：核对全域拓扑归属；拒绝退化/倒置/非流形，明确 20000 请求预算。
- 来源文档：[SEGMENT_SETS.md](archive/2026-10/SEGMENT_SETS.md)
- 证据：[原文及其验收范围](archive/2026-10/SEGMENT_SETS.md)；[复现驱动](../tools/run_segment_creation_acceptance.py)

## KI-029 QUALITY-ZERO

- 跟踪：P09

- 现象：Hex8 质量通过时原生日志不一定输出零；各准则数量不可相加当失败并集。
- 版本：4.13.4
- 规避：核对完成命令和 Save Failed 禁用状态；按真实 ID 去重。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)；[复现驱动](../tools/run_gui_solid_quality_acceptance.py)

## KI-030 QUALITY-BUFFER

- 跟踪：P09

- 现象：失败 ID 捕获占用 Buffer1 并清空通用选区。
- 版本：4.13.4
- 规避：显式备份/失效 Buffer1，保留其他槽；空集合不得转为全选。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)；[复现驱动](../tools/run_gui_failed_ids_acceptance.py)

## KI-031 XYPLOT-PRECISION

- 跟踪：Q08

- 现象：XYPlot 数值实际以 float32 存储，0.1 会读回约 0.10000000149。
- 版本：4.13.4
- 规避：按 float32 可表示值核对；拒绝溢出/下溢，保留原 CSV 与滞回点序。
- 来源文档：[NATIVE_MEDIA.md](archive/2026-10/NATIVE_MEDIA.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_MEDIA.md)；[复现驱动](../tools/run_gui_curve_acceptance.py)

## KI-032 MOVIE-RANGE

- 跟踪：G01 / I04

- 现象：原生 Movie 非默认起点/跳步探查失败，现有限定 state1/step1 路线。
- 版本：4.13.4
- 规避：核对帧数、fps、尺寸和完整解码；Q09 完整范围待验。
- 来源文档：[NATIVE_MEDIA.md](archive/2026-10/NATIVE_MEDIA.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_MEDIA.md)

## KI-033 FRINGE-PRESENTATION

- 跟踪：G02

- 现象：SCLFringeDCToModel 会重置显示默认值；CSV 原始样本不是 MinMax 显示平均。
- 版本：4.13.4
- 规避：重新应用同一平均和范围；分别检查 CSV 与图像语义。
- 来源文档：[NATIVE_MEDIA.md](archive/2026-10/NATIVE_MEDIA.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_MEDIA.md)；[复现驱动](../tools/run_result_validity_acceptance.py)

## KI-034 DELETION

- 跟踪：Q04

- 现象：物理删除、Blank、刚体和变量缺失是不同维度；正材料码不是布尔 1。
- 版本：LASSO 2.0.4 MDLOPT2；原生 4.13.4
- 规避：正材料码表示存在、0 表示删除；缺掩码拒绝推断，删除高值不得污染极值。
- 来源文档：[RESULT_VALIDITY.md](archive/2026-10/RESULT_VALIDITY.md)
- 证据：[原文及其验收范围](archive/2026-10/RESULT_VALIDITY.md)；[复现驱动](../tools/run_shell_validity_acceptance.py)

## KI-035 CHECKPOINT

- 跟踪：P11 / I01

- 现象：keyword 检查点不保存完整 Blank/视图/选择状态；零实体模型仍可能有材料。
- 版本：4.13.4
- 规避：显式记录显示设置；零实体保存 keyword 并绑定 expected_empty；恢复不能认证完整场景。
- 来源文档：[SESSION_RECOVERY.md](archive/2026-10/SESSION_RECOVERY.md)
- 证据：[原文及其验收范围](archive/2026-10/SESSION_RECOVERY.md)；[复现驱动](../tools/run_checkpoint_context_acceptance.py)

## KI-036 RECOVERY

- 跟踪：I01

- 现象：原生命令完成但主机几何校验缺失时，迟到 complete.json 不足以认证事务。
- 版本：4.13.4
- 规避：分开命令完成与后验校验；保留 uncertain，不自动重放。
- 来源文档：[SESSION_RECOVERY.md](archive/2026-10/SESSION_RECOVERY.md)
- 证据：[原文及其验收范围](archive/2026-10/SESSION_RECOVERY.md)；[复现驱动](../tools/run_session_recovery_acceptance.py)

## KI-037 INCLUDE

- 跟踪：P02 / I01

- 现象：当前通用 deck 编辑遇 INCLUDE/PARAMETER 拒绝，不能保持原文件组织。
- 版本：当前 PyDYNA 适配
- 规避：P02/I07 建立 raw-preserving 引擎；此前仅处理声明支持的独立 deck。
- 来源文档：[PYDYNA_INTEGRATION.md](archive/2026-10/PYDYNA_INTEGRATION.md)
- 证据：[原文及其验收范围](archive/2026-10/PYDYNA_INTEGRATION.md)

## KI-038 ENERGY-MISSING

- 跟踪：Q12

- 现象：请求的沙漏能缺失不能补成零；内能为零的比值不可计算。
- 版本：当前原生/数学适配
- 规避：缺请求量失败，未请求量留空；不靠 KE/IE 一个比值判断完整能量守恒。
- 来源文档：[WORKFLOWS_v0.3.md](archive/2026-10/WORKFLOWS_v0.3.md)
- 证据：[原文及其验收范围](archive/2026-10/WORKFLOWS_v0.3.md)

## KI-039 MEASURE

- 跟踪：Q11

- 现象：投影角在零投影下可能无定义；错误活动模型 token 会读错对象。
- 版本：4.13.4
- 规避：仅解释已验证 3D 角；活动模型 token + measure axes set0；坐标独立校验。
- 来源文档：[COMMON_OPERATIONS_COVERAGE.md](archive/2026-10/COMMON_OPERATIONS_COVERAGE.md)
- 证据：[原文及其验收范围](archive/2026-10/COMMON_OPERATIONS_COVERAGE.md)

## KI-040 DPF

- 跟踪：Q01 / Q03

- 现象：只有客户端不等于本地 Server 可用；当前真实 DPF 提取未完成验收。
- 版本：ansys-dpf-core 0.16.1
- 规避：先探测 Server；合成字段测试仅证明适配合同。
- 来源文档：[DPF_INTEGRATION.md](archive/2026-10/DPF_INTEGRATION.md)
- 证据：[原文及其验收范围](archive/2026-10/DPF_INTEGRATION.md)

## KI-041 MACRO-NAME

- 跟踪：A05

- 现象：create_native_macro/run_native_macro 实际为 JSON 模板，不是 .mac 原生宏。
- 版本：当前接口
- 规避：A08 并入配方库并保留别名；自由脚本需明确 language 与执行上下文。
- 来源文档：[NATIVE_PROGRAMS.md](archive/2026-10/NATIVE_PROGRAMS.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_PROGRAMS.md)

## KI-042 SET-LIST-PADDING

- 跟踪：P04

- 现象：原生 SET_NODE_LIST 补零曾被引用检查误认为缺失节点。
- 版本：4.13.4。
- 规避：0 占位不计入集合，真实缺失的非零节点仍报错。
- 来源文档与证据：[GUI_WORKFLOWS 原生网格验收记录](archive/2026-10/GUI_WORKFLOWS.md)。

## KI-043 M0 原生执行与会话实验

- 跟踪：I04 / A05

UU 的历史 12 格有提交绑定记录；剩余 13 格 runc/原生宏仍属 I04 待验，RDP 未验。远程状态不能从 Console 会话名推断，断开测试需要用户窗口。
证据口径见 [ADR 0001](decisions/0001-session-transport.md)；旧实验经过保留于历史快照。

## KI-044 锁屏状态不能由输入桌面名推断

- 跟踪：I01 / I04

- 现象：实际锁屏期间 OpenInputDesktop 可读到 Default，旧实验探针误报已解锁。
- 版本：本次 Windows x64 会话；不是对全部 Windows 构建的推断。
- 规避：实验使用 WTS 会话的 SessionFlags，区分连接状态与锁定状态；未知值不当成功。产品 WindowsCommandTransport 的相应检查留给 M1/I01/I03。
- 来源与证据：[ADR 0001](decisions/0001-session-transport.md)、[探针回归](../tests/test_m0_experiments.py)、[Microsoft SessionFlags 定义](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ns-wtsapi32-wtsinfoex_level1_w)。v6 的状态中断结果被排除，v7 完整重跑。

## KI-045 顶层 inctreeinfo2file 无效

- 跟踪：I03

- 现象：顶层 cfile 调用 `inctreeinfo2file "tree.txt"` 被报 `Invalid command inctreeinfo2file!`，没有生成文件；进程仍返回 0。
- 版本：4.13.4（17Dec2025），本轮原创 8 节点 keyword。
- 规避：不能仅以退出码判断命令成功；Include 树另经已验证接口核对，不依赖这个顶层拼写。
- 来源文档与证据：[ADR 0001 的附加复现](decisions/0001-session-transport.md)、[原始报告与命令哈希](decisions/0001-experiment-evidence.json)。

## KI-046 连续 genselect add 为并集

- 跟踪：G03

- 现象：依次添加节点 11、13，最终原生读回为 `[11,13]`、数量 2，不是只保留第二次选择。
- 版本：4.13.4（17Dec2025），c= -nographics + 应用内 Python。
- 规避：覆盖选区前显式 clear；每次组合后核对真实成员。
- 来源文档与证据：[ADR 0001 的附加复现](decisions/0001-session-transport.md)、[报告哈希](decisions/0001-experiment-evidence.json)。

## KI-047 宏面板出现与初始化完成是两件事

- 跟踪：A05

- 现象：启动时过早打开 Macro 面板并 Exec，输入模型尚未载入，原生计数为 0；同步菜单调用可能超时而面板实际已打开。
- 版本：4.13.4（17Dec2025），原始 .mac 文件。
- 规避：先要求独立载入回执与预期节点数一致，再查实际菜单/面板；超时不重复点击，以本次关联回执与新产物验证结果。
- 来源与证据：[ADR 0001](decisions/0001-session-transport.md)、[更新后的 macro/session/unlocked 三项记录](decisions/0001-experiment-evidence.json)。产品级迁移留给 M1。

## KI-048 4.10 队列会话的模型目录读回

- 跟踪：I01

- 现象：I01 的主线程队列会话打开独立 keyword 后，读到 8 节点、3 单元，但 DataCenter model_directory 仍为会话根目录，与已暂存输入目录不一致；来源校验明确失败。
- 版本：本机 4.10；同一队列流程在 4.13 通过打开、连续读取、保存重开和关闭。
- 处理：保留失败和来源身份校验，4.10 当前验收五个批处理调用方子集；I03 已在版本能力表中禁止启动 4.10 队列；替代来源读回尚未验证，现有来源校验保留。
- 证据：[I01 原生回归](../tests/test_engine_native.py)、[来源检查](../src/ls_prepost_mcp/model_context.py)。原始回执与日志仅存本地。

## KI-049 含空格/中文工作目录的原生配置解析

- 跟踪：I03 / I01

未配置别名、4.8、宏和图形路径的非 ASCII job 场景仍缺完整覆盖；GUI/Movie 需集中窗口。源文件名与 job 目录须分别判断，不能把安全名称暂存外推为任意工作目录通过。
显式 LSPP_NATIVE_ALIAS_ROOT 只适用于支持联接的本地 NTFS ASCII 根目录；按 [安装说明](INSTALL.md) 配置，已登记子集见 [工作区别名证据](decisions/evidence/i03-workspace-alias/report.md)。
中文目录的部分 SCL 路线仍有严格 xfail，条件见 [binout 路径用例](../tests/test_scl_binout_paths_native.py) 和 [SCL 字面量证据](decisions/evidence/i03-scl-literals/report.md)。未知构建下生成了文件也不足以认证成功，仍须核对进程、回执、输入与产物。

## KI-050 缺少用户配置时拒绝启动

- 跟踪：I01

缺少初始化 lsppconf、正确 Python home 或首次运行设置时，原生进程可能等待或不能加载接口。需先初始化对应安装，或显式配置 LSPP_CONFIG_SOURCE；不提供自动代写初始配置的保证。
环境准入与限制见 [安装说明](INSTALL.md) 和 tests/test_engines.py。

## KI-051 退出码为零也可能有原生诊断失败

- 跟踪：I01

原生进程 returncode=0 不足以证明输入完整或命令成功。已知错误行由共享引擎识别，未知版本/语言的诊断格式仍需复现登记；操作还必须验证自己的计数、身份和输出。
回归入口为 tests/test_engine_native.py 与 tests/test_engines.py。

## I01：批处理输入路径暂存补修

- 跟踪：I01 / I03

TRANSFORM/opaque/参数化文件名及嵌套 INCLUDE_PATH_RELATIVE 的原生加载仍拒绝；4.8 Python 环境未认证。源路径、job 工作目录和正式另存路径须分别验证。
4.13/4.10 的规范化读取副本不等于原保存树路径认证；对应范围见 [输入快照证据](decisions/evidence/i01-keyword-snapshot/report.md)、[P11 原路径证据](decisions/evidence/p11-raw-review02/report.md)。
对应未覆盖输入和平台分歧见 [I04 诊断](decisions/evidence/i04-diagnostics/report.md)；旧拒绝与失败记录保留在页首历史快照。

## I04：LASSO 结束标记后尾数据

- 跟踪：I04 / Q01

LASSO 2.0.4 按末尾非零字节估计状态数，没有在第一个结束标记处停止。公开例
`extra-result-03` 原生为 2 状态，LASSO 却静默返回 11 状态，第三时间为 `-999999`；
原创两状态夹具在结束标记后加非零尾数据，也复现了额外状态。这是共享读取器的既有缺陷，
2026-10-18 Codex 接手后增加共享时间轴准入：完整读取、元数据清点、节点导出及
state_filter 读取前的完整时间元数据统一检查；EOF 标记被当作时间、非有限时间、二维时间轴或时间倒退
会明确拒绝，不再返回看似成功的工程结果。允许合法的负起始时间、重复时间及空几何清点。
Claude 原审阅记录和上游 LASSO 2.0.4 行为仍保留：上游边界解析未修复，当前是拒绝异常输入，
不是恢复截断文件。若尾数据恰好形成有限且有序的时间，单靠时间校验仍无法确认文件结构完整。
处置：保留后端分歧并明确报告，不删状态、不重编号、不调整容差，不把异常数组当已验证结果。
历史证据及接口需求见 [I04 两例诊断](decisions/evidence/i04-diagnostics/report.md)；
回归见 [共享时间轴校验](../tests/test_d3plot_time_validation.py) 和
[原创 EOF 尾数据复现](../tests/test_public_corpus_diagnostics.py)。

## P12 运动副：R11 实测要点

- 跟踪：P12

以下是 LS-DYNA R11（SMP，双精度）实测得到的结论，证据见 [P12 证据](decisions/evidence/p12/report.md)。

- 转动电机在默认罚函数下明显滞后：转动铰加转动电机，从静止以 2π rad/s 驱动 0.5 s，RPS=1 只转了 1.73 rad（目标 π），RPS=100 为 3.00 rad，`*CONTROL_RIGID` LMF=1 为 3.14147 rad。check_model 对 LMF≠1 的转动电机给出警告。移动电机在默认罚函数下误差约 0.2%。
- 节点对间距影响罚函数的柔度：同一转动铰单摆，第二对节点离第一对 20 mm 时，沿转轴方向漂移 0.32 mm；拉开到 100 mm 时降到 0.10 mm。add_joint 默认取两侧尺寸的一半作为间距。
- 两侧节点不在同一刚体时，R11 只给 Warning 30485 并继续计算，此时运动副实际只连接 N1 所在的刚体。check_model 把这种情况报为错误。球铰 N3 留空时 R11 也会给同一警告，这是误报，check_model 不报。
- `*DATABASE_HISTORY_NODE` 里同一节点出现两次会导致 Error 20449，计算直接停止。
- `*MAT_RIGID` 需要写满三张卡；`*INITIAL_VELOCITY_GENERATION` 的 PHASE 是整数字段，写成 0.0 会报 Error 10246。
- 与运动副无关，但验证中遇到：截面只有一个单元的 ELFORM 2 实体杆，在默认 TSSFAC=0.9 下只要有外载就会发散，改用 0.5 后稳定。

## A01/A02 原始脚本权限与输出名绑定

- 跟踪：A01 / A02

bind_output_paths 仍按完整 token 绑定输出，未按输入/输出命令角色区分；同名 open 参数也会改写，应使用不同输入名并核对执行副本。
用户脚本拥有原生进程权限；声明产物检查不是文件访问沙箱。受信原始脚本的副作用不能由输出哈希穷尽，见 [脚本规则](../tests/test_script_command.py)。

## I05：Windows 索引发布的短暂共享锁

- 跟踪：I05

Windows 长期共享锁、实际 FAT/exFAT 与网络盘发布尚无完整实机覆盖；短暂锁的有界重试仍可能失败。非 Windows 无硬链接的文件系统明确拒绝发布，以保留不覆盖既有索引的约束。
失败时保留主要错误和本次拥有的临时文件线索，勿删除其他进程正在使用的索引。

## A10：旧 schema-v2 索引的字段查询耗时

- 跟踪：A10 / I05

#29 之前构建的 v2 索引没有 keyword_lookup 辅助索引。结构化过滤确保显式字段不被
说明文本挤掉，但旧索引每 100 次字段查询约 9–10 秒；此前文本检索约 0.7 秒且可能漏字段。
按新构建器另选仓库外路径重建，实测可降到约 0.35 秒。旧索引仍可读，schema_version 不变。
时间是本机该样本的测量值，不是性能保证；原始与重建对照见
[字段查找证据](decisions/evidence/a10-field-lookup/report.md)。

## I01 批处理取消与进程树生命周期

- 跟踪：I01

POSIX 正常退出后不清理同组遗留后代；取消/超时才清理。脚本主动脱离进程组或 Windows Job Object 的外部进程不在已验证回收范围，不据此终止用户进程。
生命周期限定证据见 [I01 进程树回归](decisions/evidence/i01-process-lifetime/report.md)。

## I01 日志 BOM 和非 UTF-8 诊断

- 跟踪：I01

未覆盖所有安装/语言的日志编码与诊断格式；有损解码会拒绝并保留 raw 日志，不能凭退出码或截断文本放行。显式编码设置仍需与本机原生输出一致。

## I03 路径版本提示与 Windows 资源不一致

- 跟踪：I03

资源版本不可读、安装包装器及未登记版本仍需独立探测；文件名/配置标签本身不能证明底层能力。版本冲突的已知回归不是对任意未来安装的认证。GUI/旧版本路径还需各自证据。

## I01：队列饱和时的明确拒绝

- 跟踪：I01

有限队列容量不等于并发执行保证。提交错误仍可能已抵达原生端，禁止自动重放；超时和待完成请求须按关联回执恢复。
宿主准备失败后模型仍可能被部分 Apply 改动；recover 前的只读空闲探测尚未接入，不能把未派发回读请求当作 Apply 已停止。

## A01/I01：会话日志元数据与脚本包装器的集成

- 跟踪：A01 / A02 / A03 / A04 / I01

GUI/会话链仍有旧集成树证据，不能外推到后续包装器、恢复和生命周期变更。当前批处理验证不替代 GUI/UU 窗口；四通道与面板需集中复验后再扩大等级。

## I01 / I04：多文件 INCLUDE 的原生加载检查（第九轮）

- 跟踪：I01 / I04

原生准入仍拒绝未支持 Include 变体和参数化文件名；合法关键字被产品拒绝应记产品缺口，不得当缺文件输入限制。
本地链接并发替换窗口尚未证明消除。共享预检在资源访问点受允许目录守卫保护，但任意受信原始脚本拥有进程权限，不能把它称作 OS 沙箱。

## I01：INCLUDE 漏读诊断与拒绝状态（第十一轮）

- 跟踪：I01 / I04

4.10/4.13 对相对 INCLUDE 的工作目录语义有差异；规范化读取成功不能替代真实另存树解析。未知诊断格式可能需要新增匹配与原生负例；应同时核对模型内容。
行首空白、*END 后 INCLUDE 与带引号文件名目前保留明确拒绝/未认证口径。复现实例见 [4.10 漏读证据](decisions/evidence/i01-include-diagnostics/report.md)。

## I01：输入路径在文件系统访问前拒绝网络与设备名

- 跟踪：I01

本地链接的并发替换窗口仍未完整认证；安装目录等管理员配置属于受信输入。直接 UNC/设备名必须在访问前拒绝，允许目录不能替代此规则。
关键字文件名无法按检测编码解码时，from_text 可能以 U+FFFD 显示，依赖随后报 missing；不会猜测相似文件，应先修正源编码。

## I04：公开案例按 INCLUDE 预检区分输入限制

- 跟踪：I04

历史 100 例中 39 例缺失或不可读，未进入功能验证。旧版 50 个 input restrictions 还错误包含 11 个合法但产品不支持的变体；纠正解释为 45/61 可运行例通过、16 个失败/产品缺口和 39 个输入限制，不代表新代码全量重跑。
干净046b512的15例定点复验已完成：025/063/082通过，010仍失败；11变体原生读入成功但产品往返仍失败。混合提交冻结账本为48通过/13失败/39输入限制，不是同头全量通过。冻结现有样本/源哈希，先补完整 Include 树；无法补齐时另建版本化替补集，不覆盖旧失败或静默更换语料。
逐例提交与限定范围见 [review02账本](decisions/evidence/i04-variant-review02/report.md)，历史原记录保留在 [public100](decisions/evidence/i04-current-public100/report.md)。

## Q12：能量缺项与筛查口径（2026-10-22）

- 跟踪：Q12

全量内容身份、全部输出变体及更广 L2 对照仍缺；源身份沿用 fingerprint 限制。缺总能/外功时不能认证平衡，也不能把普通数值表当作 GLSTAT。
限定数值口径见 [Q12 记录](decisions/evidence/q12-validity/report.md)。

## Q01：4.8 本机 Python 初始化限制（2026-10-23）

- 跟踪：Q01 / I04

本机 4.8 原生 result_info 路线曾无回执并退出 0xC0000409，原因未定；Python-home 配置尝试不构成通过。纯读取器不因此被断言不兼容。
限定记录见 [Q01 原生证据](decisions/evidence/q01-native-comparison/report.md)。

## P11 未覆盖的保存重开与路径情形（跟踪：P11 / I03）

- 跟踪：P11 / I03

P11 仍为 partial。TRANSFORM/opaque、参数化文件名及嵌套 INCLUDE_PATH_RELATIVE 仍拒绝；
GUI 未保存编辑、4.8 和非 ASCII 另存文件名未验。没有节点的树仍被原生读取检查拒绝。
为防止原生数据库覆盖资产，另存根目录已经含有 lspost.db 时在启动前拒绝。
当前真实路径重开与产品绑定范围见 [审核02记录](decisions/evidence/p11-raw-review02/report.md)；
旧规范化副本或早期 revision 的记录不能外推为当前另存路径解析通过。
布局内部的链接物化仍未提供，当前明确拒绝；含未解析模板评论的保存只能是 partial/missing，不应自动当作完整模型。限定子集的两版本12项复验见 [保存保护证据](decisions/evidence/p02-save-layout-review02/report.md)。

## P02：绝对外部依赖另存的修改保护（2026-10-23）

- 跟踪：P02

绝对依赖修改后的可移植路径重写未提供，当前明确拒绝；未改外部子树仍是外部依赖，不保证输出自包含。
布局内部联接/符号链接当前明确拒绝；保真物化尚未提供。写失败可能保留 job 内部分树/空目录，不能当已验证的完整产物。

## P02：参数表达式中的函数逗号（2026-10-23）

- 跟踪：P02 / P09

当前格式识别在 fields/layouts/solver_rules 仍有表达式逗号的不一致；共享判定修复在 [#135](https://github.com/lwz20210407/LS-PrePost-MCP/pull/135) Draft。
R11 启动横幅后超时，控制算例同样失败，求解器侧解释尚未验证；用户要求先做其他项。旧 LSPP 坐标读回不等于 LS-DYNA 求解器语法认证。

## Q03：应力六分量、存储点与原生对照（2026-10-23）

- 跟踪：Q03 / Q04

通用壳层/存储点映射、CMPFLG 解释和坐标变换仍缺；多点壳/厚壳必须显式 stored_point，实体算术点均值不是壳厚积分。
对照最多 1000 实体、导出最多一百万实体；双整族 SHA256 成本尚未优化。只对登记槽位/数据成立的数值配对，见 [review02 场证据](decisions/evidence/q03-shell-review02/report.md)。

## I05：API 函数名的分词与旧索引（2026-10-23）

- 跟踪：I05 / A10

真实私有 API/指南来源尚未授权补齐，合成回归不代表真实手册召回。当前新索引 tokenization 为 identifier-parts-v2；v1/旧 schema-v2 需显式重建，零命中时重建提示只在日志中，返回合同仍为空列表。
当前公开语料复跑与未命中仍保留完整分母，见 [查询记录](decisions/evidence/i05-query-review02/report.md)。

## Q05 时程的未验证范围（跟踪：Q05）

- 跟踪：Q05

默认 d3plot 的 Part/global、tshell/beam 和更广 shell 时程仍缺少原生对照，4.8 未验证。
原生 d3plot 对照限节点及显式选点单元量、最多1000状态；Part/global 对照需显式单文件 binout，
不会把多分片降为单分片。没有真实 part_ids 的 d3plot 部件时程拒绝猜测用户 PID。
显式 stored_point 与独立 native_sampling 已有登记壳槽位子集对照，通用层映射仍待完善。
曲线运算遇到 alive 列中的 deleted/unknown/畸形标记直接拒绝；不自动裁剪、补值或跨删除区间插值。
没有 alive 列的数据仍由调用者负责有效性，curve_ops 标为 not_declared；其他消费者尚未逐项验证。
删除样本的原始值保留并标无效；未知删除状态不当作全活。已修经过与限定原生证据见
[审核02时程记录](decisions/evidence/q05-deletion-review02/report.md)，Q05 保持 partial。

## G04 实体查询的输入与结果边界（2026-10-23）

- 跟踪：G04

beam/tshell 识别、结果几何谓词、显式配套模型和材料映射仍缺。d3plot 用户 Part ID 不能当材料类型/用户材料 ID；缺少编号表时必须保持未知，不能从任意同目录 .k 补齐。
目前仅参考坐标关键字 Selector/显式结果 ID，最多1000实体；变形状态与单位不能猜测，非支持几何及删除数据缺项仍拒绝。
登记子集见 [G04 证据](decisions/evidence/g04-entity-query/report.md)。

## Q06 原生 ASCII 力曲线选择与对照（2026-10-23）

- 跟踪：Q06

binout 全库、力矩/质心及 MPP/SMP 原生一致性仍未完成；ac ID 只保留原文局部参考，不认证坐标系。未知 ASCII 布局仍拒绝。
原生命令的 Sec-ID、Sl-ID/Ma-ID 和显式 side 有各自语义，不可默认合并两侧；历史原生结果不能外推更多物理量。
当前纯 ASCII 全列核对见 [review02 记录](decisions/evidence/q06-ascii-metadata-review02/report.md)。

## Q01 / Q03 / Q05：缺失用户 Part-ID 表

- 跟踪：Q01 / Q03 / Q05

仅有 `part_titles_ids` 的 d3plot 尚不能确认用户 PID，不能自动把标题序号当成 PID。
这类库存观察显式标为未确认并返回 partial；按用户 PID 过滤与部件历史当前拒绝，
待补充原生/编号表证据后再扩展，跟踪 Q01、Q03、Q05。
