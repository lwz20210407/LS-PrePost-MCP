# 已知问题与原生经验

本页收敛历史文档、能力范围与原生驱动注释。历史结果限其具体构建与语料；“未验证”不是已知厂商缺陷。原始资料保留于 archive，未以新的通过结果覆盖失败证据。

## KI-001 SELECT-BLANK

- 现象：pall 重置单元 Blank；by-part 节点选择会遗漏 Blank 单元上的节点。
- 版本：4.13.4
- 规避：避免 pall；只临时恢复必要部件，以真实 ID 选择并核对显示标志。
- 来源文档：[ENTITY_CREATION.md](archive/2026-10/ENTITY_CREATION.md)
- 证据：[原文及其验收范围](archive/2026-10/ENTITY_CREATION.md)；[复现驱动](../tools/run_selection_scene_acceptance.py)

## KI-002 SELECT-MODEL

- 现象：genselect 固定 /0 模型后缀在模型重开后选错或选不到。
- 版本：4.13.4
- 规避：面向当前模型使用无固定后缀 ID；读回集合与坐标。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)

## KI-003 SELECT-BUFFER

- 现象：Buffer 界面编号从 1 开始，命令索引从 0 开始；模型变更后旧缓存失效。
- 版本：4.13.4
- 规避：Buffer3 对应 genselect save 2；读回真实成员和模型身份。
- 来源文档：[TUTORIAL_INTEGRATION.md](archive/2026-10/TUTORIAL_INTEGRATION.md)
- 证据：[原文及其验收范围](archive/2026-10/TUTORIAL_INTEGRATION.md)

## KI-004 MODEL-NAMESPACE

- 现象：Model Selection 行号与 Remove 显示编号不同；移除非活动模型也可能改变活动模型。
- 版本：4.13.4
- 规避：刷新清单；选择使用行号、移除使用显示编号，操作后核对实际来源。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)；[复现驱动](../tools/run_model_inventory_acceptance.py)

## KI-005 MODEL-PATH

- 现象：保存或切换后 model_directory 与模型列表路径可变成最新检查点位置。
- 版本：4.13.4
- 规避：接受有会话归属和哈希证明的检查点别名；不凭相邻路径认同模型。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)；[复现驱动](../tools/run_resident_activation_acceptance.py)

## KI-006 MODEL-STALE

- 现象：结果→keyword 打开报 Invalid entity ID 后可能仍读到旧结果计数。
- 版本：4.13.4
- 规避：增量日志、输入路径和模型代际一起校验；失败不推进来源。
- 来源文档：[MODEL_REPLACEMENT.md](archive/2026-10/MODEL_REPLACEMENT.md)
- 证据：[原文及其验收范围](archive/2026-10/MODEL_REPLACEMENT.md)；[复现驱动](../tools/run_stale_model_regression.py)

## KI-007 MODEL-RESULT-SWITCH

- 现象：结果直接切换结果、或结果活动时卸载另一结果曾退出或失去响应。
- 版本：4.13.4
- 规避：使用已验证 resident keyword 中间模型；缺中间模型时拒绝。
- 来源文档：[MODEL_REPLACEMENT.md](archive/2026-10/MODEL_REPLACEMENT.md)
- 证据：[原文及其验收范围](archive/2026-10/MODEL_REPLACEMENT.md)；[复现驱动](../tools/run_model_replacement_acceptance.py)

## KI-008 NATIVE-REPLACE-001

- 现象：官方 load_body.shell.k 在同进程替换后导出时退出；完成计数回执后仍可能保存失败。
- 版本：4.13.4
- 规避：保留检查点并显式新建进程恢复；卸载后实际导出检查提前暴露故障，不自动重试。
- 来源文档：[NATIVE_KNOWN_ISSUES.md](archive/2026-10/NATIVE_KNOWN_ISSUES.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_KNOWN_ISSUES.md)；[复现驱动](../tools/run_public_motion_acceptance.py)

## KI-009 NATIVE-LOAD-002

- 现象：CONSTRAINED_LINEAR 被报无效并跳过；81 节点/64 单元计数仍可能正确。
- 版本：4.13.4
- 规避：把跳读纳入失败判据；原例保留作负例。
- 来源文档：[NATIVE_KNOWN_ISSUES.md](archive/2026-10/NATIVE_KNOWN_ISSUES.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_KNOWN_ISSUES.md)；[复现驱动](../tools/run_prescribed_motion_acceptance.py)

## KI-010 MASS

- 现象：标准 ELEMENT_MASS 曾使总单元计数校验失败；标准质量保真已修复，glyph、惯性等未认证。
- 版本：4.13.4
- 规避：读取原生导出、质量/节点/PID摘要与 SDK 计数；未支持族继续拒绝。
- 来源文档：[MASS_PRESERVATION.md](archive/2026-10/MASS_PRESERVATION.md)
- 证据：[原文及其验收范围](archive/2026-10/MASS_PRESERVATION.md)；[复现驱动](../tools/run_mass_preservation_acceptance.py)

## KI-011 BEAM-HEAP

- 现象：梁 element_connectivity 数组读取复现堆损坏，SCL 数组实验也失败。
- 版本：4.13.4
- 规避：GUI 导出新 keyword 后读标准梁端点；独立 batch 梁连接仍拒绝。
- 来源文档：[GUI_VISIBILITY.md](archive/2026-10/GUI_VISIBILITY.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_VISIBILITY.md)

## KI-012 PYTHON-ABI

- 现象：旧内置 Python 向量值未通过数值对照；标量程序通过不能解除该限制。
- 版本：4.10
- 规避：阻止旧 ABI 原生向量；显式使用 4.13 或标明读取器后端。
- 来源文档：[COMPATIBILITY.md](COMPATIBILITY.md)
- 证据：[原文及其验收范围](COMPATIBILITY.md)

## KI-013 SOLID-IP

- 现象：请求实体积分点 8 时返回点 1 张量，full-integration 标志不足以证明正确。
- 版本：4.13.4
- 规避：原生实体选择器 2–8 前置拒绝；default/point1 与读取器槽位分开。
- 来源文档：[RESULT_VALIDITY.md](archive/2026-10/RESULT_VALIDITY.md)
- 证据：[原文及其验收范围](archive/2026-10/RESULT_VALIDITY.md)；[复现驱动](../tools/run_result_validity_acceptance.py)

## KI-014 LASSO-DISPLACEMENT

- 现象：node_displacement 数组是状态坐标，直接返回会把初始位置当位移。
- 版本：LASSO 2.0.4
- 规避：先减 reference coordinates；与 LS-Reader 交叉核对。
- 来源文档：[BACKENDS.md](archive/2026-10/BACKENDS.md)
- 证据：[原文及其验收范围](archive/2026-10/BACKENDS.md)

## KI-015 LASSO-SHELL

- 现象：复材鸟撞读取出现 n_shell_vars 不匹配和塑性应变 reshape 错误。
- 版本：LASSO 2.0.4
- 规避：显式暴露读取警告；节点/状态数不能证明场数组正确。
- 来源文档：[UI_AUDIT_POST_GAPS.md](archive/2026-10/UI_AUDIT_POST_GAPS.md)
- 证据：[原文及其验收范围](archive/2026-10/UI_AUDIT_POST_GAPS.md)

## KI-016 MPP

- 现象：当前 binout 入口拒绝 MPP 分片，不能只读一个分片当完整结果。
- 版本：当前适配器
- 规避：Q06 实现合并前使用已核实单文件语料；缺口明确报告。
- 来源文档：[BACKENDS.md](archive/2026-10/BACKENDS.md)
- 证据：[原文及其验收范围](archive/2026-10/BACKENDS.md)

## KI-017 SCL-PATH

- 现象：runscript/SCLBinoutOpen 对正斜杠 Windows 绝对路径解析错误。
- 版本：4.13.4
- 规避：原生命令使用转义后的反斜杠路径，SCL 输出用明确绝对路径。
- 来源文档：[POSTPROCESSING.md](archive/2026-10/POSTPROCESSING.md)
- 证据：[原文及其验收范围](archive/2026-10/POSTPROCESSING.md)；[复现驱动](../tools/run_gui_binout_acceptance.py)

## KI-018 SAVE-PATH

- 现象：部分批处理构建给绝对 keyword 输出路径加临时前缀；GUI 开模型又会漂移 cwd。
- 版本：4.10/4.13，路径策略依适配器
- 规避：批处理固定 cwd + 相对文件名；持久 GUI 使用经验证绝对 Windows 路径；核对实际新产物。
- 来源文档：[VERIFICATION.md](archive/2026-10/VERIFICATION.md)
- 证据：[原文及其验收范围](archive/2026-10/VERIFICATION.md)；[复现驱动](../tools/run_node_replacement_acceptance.py)

## KI-019 RESULT-CWD

- 现象：长路径加载曾访问违规；GUI 偏好可能恢复工作目录。
- 版本：4.8/4.10/4.13 的已记载样例
- 规避：结果父目录按文件名加载或有界暂存，再恢复 job cwd。
- 来源文档：[COMPATIBILITY.md](COMPATIBILITY.md)
- 证据：[原文及其验收范围](COMPATIBILITY.md)

## KI-020 STATE

- 现象：Python 回调内 switch_state 不能证明 GUI 显示已切换，读状态还会改变 cwd。
- 版本：4.13.4
- 规避：外层命令流使用 state N 并读回；曲线输出使用绝对路径。
- 来源文档：[RESULT_CONTRACTS.md](archive/2026-10/RESULT_CONTRACTS.md)
- 证据：[原文及其验收范围](archive/2026-10/RESULT_CONTRACTS.md)；[复现驱动](../tools/run_gui_post_workflow_acceptance.py)

## KI-021 VIEW-SAVE

- 现象：view save 在没有命名视图时无数据；加载视图还可追加外观/颜色。
- 版本：4.13.4
- 规避：先创建命名视图，再保存/恢复并比较图像；跨进程书签仍待验。
- 来源文档：[GUI_CAMERA.md](archive/2026-10/GUI_CAMERA.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_CAMERA.md)；[复现驱动](../tools/run_gui_camera_acceptance.py)

## KI-022 NEW-SESSION

- 现象：new 在部分 GUI 状态下被解释为重启并弹确认框。
- 版本：4.13.4
- 规避：不把 new 当受管 GUI 启动命令。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)

## KI-023 GUI-DESKTOP

- 现象：命令框与对话框驱动依赖未锁定桌面，首次安装可能弹初始化设置。
- 版本：Windows 4.13.4
- 规避：当前驱动先检查桌面；E5 分别验证锁屏/RDP，不能推断两者相同。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)

## KI-024 GUI-CONTROLS

- 现象：部分控件 ID 与英文菜单仅在当前构建录制，其他构建不可直接套用。
- 版本：4.13.4
- 规避：按版本探测与读回；ui_entry 需截图审计。
- 来源文档：[MCP_TOOL_PROFILES.md](archive/2026-10/MCP_TOOL_PROFILES.md)
- 证据：[原文及其验收范围](archive/2026-10/MCP_TOOL_PROFILES.md)

## KI-025 SPC-ROWS

- 现象：原生多行 SPC_NODE_ID 导入曾截断；标题/数据映射也需单独核对。
- 版本：4.13.4
- 规避：每节点单独具名卡，读回完整 ID/DOF/引用。
- 来源文档：[ENTITY_CREATION.md](archive/2026-10/ENTITY_CREATION.md)
- 证据：[原文及其验收范围](archive/2026-10/ENTITY_CREATION.md)；[复现驱动](../tools/run_entity_creation_acceptance.py)

## KI-026 MOTION-TITLE

- 现象：含逗号的规定运动 heading 导入会改变文字。
- 版本：4.13.4
- 规避：前置拒绝逗号，保留已验证 ASCII 标题；共享分组 ID 不等于节点 DOF 无冲突。
- 来源文档：[PRESCRIBED_MOTION.md](archive/2026-10/PRESCRIBED_MOTION.md)
- 证据：[原文及其验收范围](archive/2026-10/PRESCRIBED_MOTION.md)；[复现驱动](../tools/run_prescribed_motion_acceptance.py)

## KI-027 NR-ORDER

- 现象：二维旧版无反射边界需要有序节点链；普通集合排序会改变边方向。
- 版本：LSPP 4.13.4 读写；LS-DYNA R11–R16 文档
- 规避：旧路线保留两节点顺序；新版负 SID 与旧版正节点集路线分开。
- 来源文档：[BOUNDARY_CONDITIONS.md](archive/2026-10/BOUNDARY_CONDITIONS.md)
- 证据：[原文及其验收范围](archive/2026-10/BOUNDARY_CONDITIONS.md)；[复现驱动](../tools/run_boundary_creation_acceptance.py)

## KI-028 SEGMENT-TOPOLOGY

- 现象：共节点外表面筛选不等于非匹配网格相交检测；局部选区共享面不能当外表面。
- 版本：4.13.4
- 规避：核对全域拓扑归属；拒绝退化/倒置/非流形，明确 20000 请求预算。
- 来源文档：[SEGMENT_SETS.md](archive/2026-10/SEGMENT_SETS.md)
- 证据：[原文及其验收范围](archive/2026-10/SEGMENT_SETS.md)；[复现驱动](../tools/run_segment_creation_acceptance.py)

## KI-029 QUALITY-ZERO

- 现象：Hex8 质量通过时原生日志不一定输出零；各准则数量不可相加当失败并集。
- 版本：4.13.4
- 规避：核对完成命令和 Save Failed 禁用状态；按真实 ID 去重。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)；[复现驱动](../tools/run_gui_solid_quality_acceptance.py)

## KI-030 QUALITY-BUFFER

- 现象：失败 ID 捕获占用 Buffer1 并清空通用选区。
- 版本：4.13.4
- 规避：显式备份/失效 Buffer1，保留其他槽；空集合不得转为全选。
- 来源文档：[GUI_WORKFLOWS.md](archive/2026-10/GUI_WORKFLOWS.md)
- 证据：[原文及其验收范围](archive/2026-10/GUI_WORKFLOWS.md)；[复现驱动](../tools/run_gui_failed_ids_acceptance.py)

## KI-031 XYPLOT-PRECISION

- 现象：XYPlot 数值实际以 float32 存储，0.1 会读回约 0.10000000149。
- 版本：4.13.4
- 规避：按 float32 可表示值核对；拒绝溢出/下溢，保留原 CSV 与滞回点序。
- 来源文档：[NATIVE_MEDIA.md](archive/2026-10/NATIVE_MEDIA.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_MEDIA.md)；[复现驱动](../tools/run_gui_curve_acceptance.py)

## KI-032 MOVIE-RANGE

- 现象：原生 Movie 非默认起点/跳步探查失败，现有限定 state1/step1 路线。
- 版本：4.13.4
- 规避：核对帧数、fps、尺寸和完整解码；Q09 完整范围待验。
- 来源文档：[NATIVE_MEDIA.md](archive/2026-10/NATIVE_MEDIA.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_MEDIA.md)

## KI-033 FRINGE-PRESENTATION

- 现象：SCLFringeDCToModel 会重置显示默认值；CSV 原始样本不是 MinMax 显示平均。
- 版本：4.13.4
- 规避：重新应用同一平均和范围；分别检查 CSV 与图像语义。
- 来源文档：[NATIVE_MEDIA.md](archive/2026-10/NATIVE_MEDIA.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_MEDIA.md)；[复现驱动](../tools/run_result_validity_acceptance.py)

## KI-034 DELETION

- 现象：物理删除、Blank、刚体和变量缺失是不同维度；正材料码不是布尔 1。
- 版本：LASSO 2.0.4 MDLOPT2；原生 4.13.4
- 规避：正材料码表示存在、0 表示删除；缺掩码拒绝推断，删除高值不得污染极值。
- 来源文档：[RESULT_VALIDITY.md](archive/2026-10/RESULT_VALIDITY.md)
- 证据：[原文及其验收范围](archive/2026-10/RESULT_VALIDITY.md)；[复现驱动](../tools/run_shell_validity_acceptance.py)

## KI-035 CHECKPOINT

- 现象：keyword 检查点不保存完整 Blank/视图/选择状态；零实体模型仍可能有材料。
- 版本：4.13.4
- 规避：显式记录显示设置；零实体保存 keyword 并绑定 expected_empty；恢复不能认证完整场景。
- 来源文档：[SESSION_RECOVERY.md](archive/2026-10/SESSION_RECOVERY.md)
- 证据：[原文及其验收范围](archive/2026-10/SESSION_RECOVERY.md)；[复现驱动](../tools/run_checkpoint_context_acceptance.py)

## KI-036 RECOVERY

- 现象：原生命令完成但主机几何校验缺失时，迟到 complete.json 不足以认证事务。
- 版本：4.13.4
- 规避：分开命令完成与后验校验；保留 uncertain，不自动重放。
- 来源文档：[SESSION_RECOVERY.md](archive/2026-10/SESSION_RECOVERY.md)
- 证据：[原文及其验收范围](archive/2026-10/SESSION_RECOVERY.md)；[复现驱动](../tools/run_session_recovery_acceptance.py)

## KI-037 INCLUDE

- 现象：当前通用 deck 编辑遇 INCLUDE/PARAMETER 拒绝，不能保持原文件组织。
- 版本：当前 PyDYNA 适配
- 规避：P02/I07 建立 raw-preserving 引擎；此前仅处理声明支持的独立 deck。
- 来源文档：[PYDYNA_INTEGRATION.md](archive/2026-10/PYDYNA_INTEGRATION.md)
- 证据：[原文及其验收范围](archive/2026-10/PYDYNA_INTEGRATION.md)

## KI-038 ENERGY-MISSING

- 现象：请求的沙漏能缺失不能补成零；内能为零的比值不可计算。
- 版本：当前原生/数学适配
- 规避：缺请求量失败，未请求量留空；不靠 KE/IE 一个比值判断完整能量守恒。
- 来源文档：[WORKFLOWS_v0.3.md](archive/2026-10/WORKFLOWS_v0.3.md)
- 证据：[原文及其验收范围](archive/2026-10/WORKFLOWS_v0.3.md)

## KI-039 MEASURE

- 现象：投影角在零投影下可能无定义；错误活动模型 token 会读错对象。
- 版本：4.13.4
- 规避：仅解释已验证 3D 角；活动模型 token + measure axes set0；坐标独立校验。
- 来源文档：[COMMON_OPERATIONS_COVERAGE.md](archive/2026-10/COMMON_OPERATIONS_COVERAGE.md)
- 证据：[原文及其验收范围](archive/2026-10/COMMON_OPERATIONS_COVERAGE.md)

## KI-040 DPF

- 现象：只有客户端不等于本地 Server 可用；当前真实 DPF 提取未完成验收。
- 版本：ansys-dpf-core 0.16.1
- 规避：先探测 Server；合成字段测试仅证明适配合同。
- 来源文档：[DPF_INTEGRATION.md](archive/2026-10/DPF_INTEGRATION.md)
- 证据：[原文及其验收范围](archive/2026-10/DPF_INTEGRATION.md)

## KI-041 MACRO-NAME

- 现象：create_native_macro/run_native_macro 实际为 JSON 模板，不是 .mac 原生宏。
- 版本：当前接口
- 规避：A08 并入配方库并保留别名；自由脚本需明确 language 与执行上下文。
- 来源文档：[NATIVE_PROGRAMS.md](archive/2026-10/NATIVE_PROGRAMS.md)
- 证据：[原文及其验收范围](archive/2026-10/NATIVE_PROGRAMS.md)

## KI-042 SET-LIST-PADDING

- 现象：原生 SET_NODE_LIST 补零曾被引用检查误认为缺失节点。
- 版本：4.13.4。
- 规避：0 占位不计入集合，真实缺失的非零节点仍报错。
- 来源文档与证据：[GUI_WORKFLOWS 原生网格验收记录](archive/2026-10/GUI_WORKFLOWS.md)。

## KI-043 M0 原生执行与会话实验

- 现象：4.13 runc= 的数据操作通过，图形请求出现原生退出；4.10 的同一 runc= 程序未通过。c= -nographics 可生成 PNG，但两版本的 640×480 MP4 请求读回 640×476。
- 版本：4.13.4（17Dec2025）及本机 4.10 安装；仅本次原创语料。
- 规避：按模式/版本/配方登记结果；使用独立尺寸、帧数与完整解码检查，不把文件存在当通过。M0 不修改运行引擎。
- 来源与证据：[ADR 0001](decisions/0001-session-transport.md)、[50 格原始记录的去路径摘要和 SHA256](decisions/0001-experiment-evidence.json)。UU 12 格已测，13 格转 I04，RDP 未测。
- UU 12 格实际运行于 I01 提交 `a5a6166`，该提交不在本 M0 PR 历史中；UU 探针脚本事后整理入库，不存在于该执行提交。历史证据与本 PR 头重跑结果分别对待。
- 追加对照：两版本分别设置 w=1024x768、w=640x480，输出仍为 640×476；该参数不能作为修复。

## KI-044 锁屏状态不能由输入桌面名推断

- 现象：实际锁屏期间 OpenInputDesktop 可读到 Default，旧实验探针误报已解锁。
- 版本：本次 Windows x64 会话；不是对全部 Windows 构建的推断。
- 规避：实验使用 WTS 会话的 SessionFlags，区分连接状态与锁定状态；未知值不当成功。产品 WindowsCommandTransport 的相应检查留给 M1/I01/I03。
- 来源与证据：[ADR 0001](decisions/0001-session-transport.md)、[探针回归](../tests/test_m0_experiments.py)、[Microsoft SessionFlags 定义](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ns-wtsapi32-wtsinfoex_level1_w)。v6 的状态中断结果被排除，v7 完整重跑。

## KI-045 顶层 inctreeinfo2file 无效

- 现象：顶层 cfile 调用 `inctreeinfo2file "tree.txt"` 被报 `Invalid command inctreeinfo2file!`，没有生成文件；进程仍返回 0。
- 版本：4.13.4（17Dec2025），本轮原创 8 节点 keyword。
- 规避：不能仅以退出码判断命令成功；Include 树另经已验证接口核对，不依赖这个顶层拼写。
- 来源文档与证据：[ADR 0001 的附加复现](decisions/0001-session-transport.md)、[原始报告与命令哈希](decisions/0001-experiment-evidence.json)。

## KI-046 连续 genselect add 为并集

- 现象：依次添加节点 11、13，最终原生读回为 `[11,13]`、数量 2，不是只保留第二次选择。
- 版本：4.13.4（17Dec2025），c= -nographics + 应用内 Python。
- 规避：覆盖选区前显式 clear；每次组合后核对真实成员。
- 来源文档与证据：[ADR 0001 的附加复现](decisions/0001-session-transport.md)、[报告哈希](decisions/0001-experiment-evidence.json)。

## KI-047 宏面板出现与初始化完成是两件事

- 现象：启动时过早打开 Macro 面板并 Exec，输入模型尚未载入，原生计数为 0；同步菜单调用可能超时而面板实际已打开。
- 版本：4.13.4（17Dec2025），原始 .mac 文件。
- 规避：先要求独立载入回执与预期节点数一致，再查实际菜单/面板；超时不重复点击，以本次关联回执与新产物验证结果。
- 来源与证据：[ADR 0001](decisions/0001-session-transport.md)、[更新后的 macro/session/unlocked 三项记录](decisions/0001-experiment-evidence.json)。产品级迁移留给 M1。

## KI-048 4.10 队列会话的模型目录读回

- 现象：I01 的主线程队列会话打开独立 keyword 后，读到 8 节点、3 单元，但 DataCenter model_directory 仍为会话根目录，与已暂存输入目录不一致；来源校验明确失败。
- 版本：本机 4.10；同一队列流程在 4.13 通过打开、连续读取、保存重开和关闭。
- 处理：保留失败和来源身份校验，4.10 当前验收五个批处理调用方子集；I03 已在版本能力表中禁止启动 4.10 队列；替代来源读回尚未验证，现有来源校验保留。
- 证据：[I01 原生回归](../tests/test_engine_native.py)、[来源检查](../src/ls_prepost_mcp/model_context.py)。原始回执与日志仅存本地。

## KI-049 含空格/中文工作目录的原生配置解析

- I01 后续修复：仅 BatchEngine 的 ASCII 路径将两个工作目录配置字段改为 `.`，绝对日志路径不变；GUI/队列保留绝对工作目录。ASCII 空格目录的保存、PNG、重开已补测。
- 非 ASCII job 目录仍为 gap：4.13 使用相对配置的完整链路出现 `0xC0000374` 退出错误，未启用该实验路径，也未因文件已生成而标通过。非 ASCII 源文件会暂存到安全名称，与 job 目录限制分别报告。
- 优先级：高于其余 P2；普通用户目录也可能触发，必须优先处理。
- 现象：4.13.4 与 4.10.1 的 job 工作目录含空格或“中文 空格”时，原生未找到已暂存的 input_data，并报告 SCL parsing -2；进程仍可能返回 0。4.13 日志中的路径在空格前截断。
- 已验证子集：ASCII 工作目录中，可暂存中文/空格源文件名并运行 PNG、keyword 保存和原生重开。
- 处理：集中路径构建器拒绝分号、引号和控制字符；cfile 统一 UTF-8。中文 job 目录限制保留为严格 xfail；ASCII 空格批处理目录已通过。
- 证据：[路径原生回归](../tests/test_engine_native.py)；去路径报告随本 PR 附件保留，原始日志留在仓库外。GUI/Movie 路径仍待集中窗口。


## KI-052 Windows 深层 job 的临时 JSON 文件超长

- 现象：目标文件本身可写，但完整文件名后追加 32 位 UUID 的原子临时文件超过 Windows 路径限制；边界条件创建在写入模型身份旁车时失败。
- 修复：`atomic_json` 在同一目录独占创建短临时文件，保留原子替换和 Windows 短暂共享锁重试；不再重复目标文件名。测试框架也缩短用例目录前缀。
- 证据：[深层目录与原文件保留回归](../tests/test_atomic_json.py)。此次 GUI 窗口中边界条件创建用例修复后通过；原始失败记录保留在本地。

## KI-050 缺少用户配置时拒绝启动

- 现象：用仅含星号的私有 lsppconf 代替缺失的用户配置会丢失 Python home/首次运行设置，后台程序可能等待初始化。
- 处理：I01 现在直接拒绝缺配置，提示先启动对应安装完成设置，或显式指定 LSPP_CONFIG_SOURCE；不再生成空白替代配置。
- 证据：tests/test_engines.py 的缺配置拒绝与原配置不变回归；此检查在原生进程启动之前执行。

## KI-051 退出码为零也可能有原生诊断失败

- 行为：共享引擎检测到原生错误行即失败，即使 returncode=0。五个批处理调用方现在透传 engine_error.message，保留真实命令诊断，而非只报退出码和超时状态。
- 证据：tests/test_engine_native.py 的无效命令原生负例，以及 tests/test_engines.py 的公开 Service 错误透传回归。

## I01：批处理输入路径暂存补修

公开语料暴露了非 ASCII 源路径读取失败和 Include 相对目录丢失。独立 keyword 与 d3plot 文件族现在复用已有暂存器，使用 job 内的 ASCII 名称，并核对整个原文件族身份；已有普通 Include 的只读打开使用绝对根文件路径。Include 解析能力和编辑保存仍留 I07，不实现第二套关键字引擎。

- 已修：Include 打开期间 cwd 始终位于自有 job，不能切到用户源目录；离线与原生用例逐项比较源目录文件列表和字节身份。
- 明确限制：原生 d3plot 模型检查等入口超过 1000 个文件或 2 GiB 时在创建 job、启动进程前拒绝。小型真实结果强制走原地回退的实验在 4.13/4.10 均返回访问冲突，故不交付该回退；大结果支持仍为 I01 gap，读取器通道的限制独立于此。
- 已修：暂存之后整族文件被修改、添加或删除均导致失败。超限拒绝有模拟大文件及实际 1001 个小文件的离线回归，不声称运行过 2 GiB 原生模型。
- 原生 gap：中文 Include 根路径在两版失败；4.10 仍从 job cwd 查找相对 Include。只有匹配已观察到的特定诊断才严格 xfail，源目录不变断言始终先执行；其他错误仍失败。

证据：[输入暂存回归](../tests/test_batch_input_staging.py)；原生报告随本修复附于 [I01 路径证据](decisions/evidence/i01-staging/report.md)。
## 2026-10-06 复审后续项（按任务归属）

| 归属 | 待修事项或本轮处置 |
|---|---|
| I02 | 旧 failed 无 error、partial 无 warnings 会经 normalize_outcome 变成 unverified + LegacyContractError；gui_field_movie、gui_media、sessions、native_batch 的产出需适配 reason/restoration_error。 |
| I02 | failed.error.message 仍可为空；需收紧为非空字符串。FieldSpec 适配层及等价测试已登记为 tasks.yaml 中的 M2 gap。 |
| I10 | ADR 0001 已改为如实说明历史证据 JSON 没有探针脚本 SHA256，未补造该字段。 |
| I05 | 混合查询丢失中文词，例如“MPP 节点选择”；需保留两类查询词。 |
| I05 | os.link 发布索引不适用于 FAT/exFAT 及部分网络盘；需复制到同目录临时文件并原子改名的回退。 |
| I04 | KI-052 的短用例目录前缀在本 PR #5 补交，不属于 2f10da2 的改动。 |
| I04 | 原生证据必须写实际 Git revision；工作树未提交时另记改动身份，不得宣称为 PR 头运行。 |
| I03 | import keyword、open xydata、savefile xypair、modelcheck writetofile 尚有 8 模块 12 处；SCL 编码未统一。 |
| I03 | 路径兼容性变化：quoted_path 现在在启动前拒绝分号、引号及控制字符，旧调用者可能因此获得明确 ValueError。 |
| I01/I03 | KI-049 的空格/中文 job 工作目录问题列为最高优先级 P2；源文件路径与 job 工作目录须分别验证。 |
| I04 | 缺少可执行文件的提示已同时列出 --native-executable、LSPP_ENGINE_EXECUTABLE 和 LSPP_EXECUTABLE。 |
| I04 | CI 增加 ruff check .；新提交只有该 CI 步骤成功后才报告 CI Ruff 通过。既有附件中的本机 Ruff 结果不等于 CI 执行记录。 |

## A01/A02 原始脚本权限与输出名绑定

- `bind_output_paths` 按完整参数 token 匹配声明输出名，尚未按命令角色区分输入和输出。同名 token 即使出现在 open 命令中，也会改写为当前 job 的路径；读取已有文件时应使用不与声明输出同名的路径。请求原文和执行副本均保留以便核对。
- 用户提供的命令和 cfile 拥有 LS-PrePost 进程的原生权限，可以读写进程有权访问的任意路径。输出合同验证声明产物，不是脚本文件访问沙箱。
- 单命令入口拒绝 open command / openc command（含大小写及空白变体）；命令文件须使用 cfile 通道。JobResult 包装保留已有 warnings 与 checks，partial 不会因丢失警告而退成 unverified。
- 证据：[单命令合同回归](../tests/test_script_command.py)。A01 的旧记录缺少提交及 diff 身份；现已在干净 main 9e55e9b 重新验证并附 [A01 原生证据](decisions/evidence/a01/report.md)，据此恢复 done。

## 能力范围原文索引

以下是 M0 冻结能力文件的全部 scope/limitation 字段，按原文去重。它们同时包含已验证范围和未验证项，不全是原生缺陷。版本、规避和证据保留原文；原文未注明者不补造。来源文件：[capabilities.json](../src/ls_prepost_mcp/data/capabilities.json)。

<details>
<summary>results.history.scope</summary>

Visible 4.13.4 selected-node history -> scalar component CSVs -> relative displacement, two parameterized runs verified; original state restored/read back, selection/geometry/part visibility retained. FieldSpec included; max 100 curves, explicit units/time labels; not arbitrary gauge/stress or old ABI certification.

</details>

<details>
<summary>results.stress_tensor.gui_scope, results.native_fields.gui_scope, results.field_contracts.gui_scope</summary>

gui_session_action or GUI workflow uses current staged d3plot without path/reopen/new process. Visible 4.13.4 solid six-stress/Mises and native strain/plastic-strain exports verified; state/geometry/selection/part flags preserved. Shared parser/contracts. GUI completion uses embedded Python; streaming geometry/visibility digest plus selected-ID snapshot; per-request limits remain, no new shell/tshell certification.

</details>

<details>
<summary>results.stress_tensor.validity_scope, results.native_fields.validity_scope, results.reader_fields.validity_scope, results.reader_stress.validity_scope, results.field_contracts.validity_scope</summary>

Explicit raw/alive; LASSO MDLOPT2 positive material code=present,0=deleted. Native values remain SCL; 4.13.4 solid deletion/blank/all-deleted/replay/maximum spot verification. Other domains, media and old-build validity not certified. See docs/RESULT_VALIDITY.md.

</details>

<details>
<summary>results.stress_tensor.native_point_scope, results.native_fields.native_point_scope, results.field_contracts.native_point_scope, presentation.named_native_fringe.native_point_scope</summary>

Native solid2..8 reject before dispatch after visible4.13.4 returned point1 for point8. Native default/point1 and shell selectors remain; see docs/RESULT_VALIDITY.md. No silent reader fallback.

</details>

<details>
<summary>session.live.scope</summary>

Owned GUI, checkpoints, finite command requests; see docs/WORKFLOWS_v0.3.md

</details>

<details>
<summary>results.native_binout.scope</summary>

Single-file native SCLBinout:NODOUT components,GLSTAT energies,MATSUM energy/eroded energy/mass/momentum/rigid-body velocity. Explicit session_id reuses current GUI; workflow session routes here.11 MATSUM fields*101states at stored ID1500 match LASSO exactly in official fixture;missing ID/absent hourglass reject. ID1501 energy-overlay explicit-dependency replay passed. Same-GUI GLSTAT101/NODOUT1001 point checks passed. Source units/model correspondence not inferred;no MPP fragments or universal branch/build coverage.

</details>

<details>
<summary>automation.show_gui_session.scope, automation.list_installations.scope, automation.run_on_version.scope, automation.probe_environment.scope, automation.probe_scl.scope, automation.get_element_connectivity.scope, automation.export_keyword.scope, automation.measure_parts.scope, automation.read_job.scope, automation.list_jobs.scope, automation.inspect_binout.scope, automation.inspect_d3plot_database.scope, automation.inspect_lsreader.scope, automation.create_solid_sphere.scope, automation.rotate_mesh_nodes.scope, automation.list_gui_sessions.scope, automation.open_in_gui_session.scope, automation.gui_session_action.scope, automation.checkpoint_gui_session.scope, automation.restore_gui_checkpoint.scope, automation.recover_gui_session.scope, automation.reset_gui_session.scope, automation.close_gui_session.scope, automation.set_gui_part_visibility.scope, automation.list_installation_assets.scope, automation.describe_installed_template.scope, automation.apply_keyword_filter.scope, automation.inspect_mesh_quality.scope, automation.transform_mesh_deck.scope, automation.merge_duplicate_mesh_nodes.scope, automation.build_tensile_curves.scope, automation.combine_history_curves.scope, automation.assess_energy_balance.scope, automation.native_tensile_postprocess.scope, automation.native_energy_postprocess.scope, automation.create_workflow.scope, automation.run_workflow.scope, automation.start_session_recording.scope, automation.stop_session_recording.scope, automation.parameterize_workflow.scope</summary>

Bounded workflow; backend and validation limits in docs/WORKFLOWS_v0.3.md

</details>

<details>
<summary>automation.inspect_gui_session.scope</summary>

Metadata by default; include_models=True reads owned native Model Selection row indexes, display labels and paths. Unique-source active-row candidate only. Opens/leaves panel; verifies active counters/Part IDs/state/source. Windows x64, <=256 rows, bounded text. No general model mutation interface.

</details>

<details>
<summary>automation.checkpoint_gui_session.recovery_scope, automation.recover_gui_session.recovery_scope, gui_mesh.restart_gui_session.recovery_scope</summary>

Visible4.13.4 actual late completion, uncertain command/host validation separation, checkpoint preservation, exact owned-process termination/restart and replacement reuse verified. Saved model/source only; arbitrary GUI state and full workflow continuation remain. docs/SESSION_RECOVERY.md

</details>

<details>
<summary>automation.restore_gui_checkpoint.reset_recovery_scope, automation.reset_gui_session.reset_recovery_scope, gui_mesh.restart_gui_session.reset_recovery_scope</summary>

Visible4.13.4 reset distinguishes prior explicit-undo checkpoint from new active empty restart baseline. Zero-node material cards are saved; late-reset source setup covered; new save/open supersedes baseline. Native96-node reset/restart->0,two-material undo and later node301 recovery passed. Default trusted restore uses file-bound empty expectation;not full resident-model unload or in-flight crash certification.

</details>

<details>
<summary>automation.set_gui_display.scope</summary>

Standard view/display options plus native absolute zoom_scale/pan_xy and ordered incremental X/Y/Z view rotations. Visible4.13.4 synthetic keyword and representative d3plot checks cover pixel-exact absolute-setting repetition, inverse-rotation raster tolerance, geometry/state/part preservation and changed-zoom managed replay. Last rotation increment remains. Numeric camera matrices, managed bookmarks, arbitrary pivots and selected-only fit are not certified. See docs/GUI_CAMERA.md.

</details>

<details>
<summary>automation.control_gui_animation.scope</summary>

Command submission implemented; visual playback/end-state acceptance pending

</details>

<details>
<summary>automation.instantiate_installed_template.scope</summary>

7/7 parameter expansion/native nonempty mesh load; no per-card/SALE-generation/solver validation

</details>

<details>
<summary>automation.combine_history_curves.unit_scope</summary>

Optional per-source time/value units converted before alignment. Legacy calls explicitly mark shared units as assumed/unverified.

</details>

<details>
<summary>automation.start_session_recording.zero_entity_baseline_scope, automation.stop_session_recording.zero_entity_baseline_scope, automation.parameterize_workflow.zero_entity_baseline_scope</summary>

Native zero-node/element keyword checkpoint plus explicit initial_expected_empty recorded/preserved/replayed.4.13.4 material-only source,changed node IDs and distractor removal in active model passed;old curve-recording regression passed. Not all-model unloading,legacy recording migration certification. File-bound zero-checkpoint restart now separately verified for controlled idle-process exits.

</details>

<details>
<summary>automation.stop_session_recording.dependency_scope</summary>

Typed workflows preserve explicit result/artifact links and include file/engineering steps; reparameterized selected IDs drove fresh native curves and subtraction in visible 4.13.4. No equal-value inference or arbitrary manual/file-call capture; unresolved dependencies require review.

</details>

<details>
<summary>automation.import_command_recording.scope</summary>

13-step raw cfile to typed selection/buffer/translation/normals/shell-quality replay verified; explicit model-index mapping required; unknown commands still block

</details>

<details>
<summary>programs.prepare_native_program.scope, programs.execute_native_program.scope, programs.execute_gui_command.scope, programs.create_native_macro.scope, programs.run_native_macro.scope</summary>

Exact source preparation/native execution or macro replay; see docs/NATIVE_PROGRAMS.md for per-language version matrix and verification limits

</details>

<details>
<summary>programs.prepare_native_program.bundle_scope, programs.execute_native_program.bundle_scope, programs.create_native_macro.bundle_scope, programs.run_native_macro.bundle_scope</summary>

Explicit dependency snapshot/hashes/relative layout; native child-script references/cycles checked. Visible4.13.4 nested cfiles, SCL data, Python module refresh and frozen macro parameter replay verified. No general include/import inference, global macro-menu/shortcut certification or old/headless bundle certification. docs/PROGRAM_BUNDLES.md

</details>

<details>
<summary>programs.prepare_native_program.native_macro_scope</summary>

language=macro: selected *macro block, literal numeric defaults, &name/&{name} and n/e/p positive-user-ID bindings compile to cfile; preserves source.mac and bound.mac. Same-GUI4.13.4 node101->103 selection/geometry/source hash checks passed. No general expressions, interactive picking, pauses, native menu/shortcut installation or old/headless certification.

</details>

<details>
<summary>gui_mesh.inspect_gui_mesh.scope</summary>

Native keyword/result reference mesh. Legacy full snapshot retains20000 bound; explicit entity_type pages materialize only requested coordinates/connectivity with limit1..5000. Private solid-only model over300000elements passed first/middle/last node+solid pages in keyword and d3plot. No cross-call atomicity or large-model edit certification; see docs/MODEL_SCALE.md.

</details>

<details>
<summary>gui_mesh.inspect_gui_mesh_quality.scope</summary>

Native GUI readback + geometry math; not full native Model Checking

</details>

<details>
<summary>gui_mesh.merge_gui_duplicate_nodes.scope</summary>

Native DupNode; 5 to 4 nodes verified; broader keyword references remain separate

</details>

<details>
<summary>gui_mesh.reverse_gui_shell_normals.scope</summary>

Native standard Tri3/Quad4 all/explicit normal reversal with complete streamed cyclic-orientation, coordinate, unselected-connectivity, part-membership and visibility preservation; no global20000 snapshot.100000native-shell double/full/partial reversal and normalized save/reopen passed. Automatic seed/outward unification, thick shells, material axes and all keyword references remain outside scope.

</details>

<details>
<summary>gui_mesh.translate_gui_nodes.scope</summary>

Selected nodes moved in the SAME visible GUI, unselected coordinates checked. Complete streamed topology/unrequested-coordinate digests plus requested coordinates; no global20000 bound.100000native-shell and over300000private-solid edit/save/reopen passed. Explicit request limit10000nodes; keyword references/quality remain separate.

</details>

<details>
<summary>gui_mesh.rotate_gui_nodes.scope</summary>

Same visible GUI; global Z-axis synthetic case tested; all coordinates checked. Complete streamed topology/unrequested-coordinate digests plus requested coordinates; no global20000 bound.100000native-shell and over300000private-solid edit/save/reopen passed. Explicit request limit10000nodes; keyword references/quality remain separate.

</details>

<details>
<summary>gui_mesh.create_gui_nodes.scope</summary>

Native keyword import of explicit new nodes; existing mesh verified unchanged

</details>

<details>
<summary>gui_mesh.create_gui_elements.scope</summary>

Native quad/tri shell import retained. 4.13.4 shared-face Hex8 creation now verified: native box + four new nodes + adjacent hex, exact connectivity/part membership, geometric quality, native save/reopen; inverted hex rejected before import. No native solid Model Checking, material/contact or solver certification.

</details>

<details>
<summary>gui_mesh.restart_gui_session.scope</summary>

Exited process checkpoint recovery; no uncertain operation replay

</details>

<details>
<summary>gui_mesh.restart_gui_session.checkpoint_context_scope</summary>

File-bound native keyword inventory sidecars validate owner/hash and determine zero-entity expectation before replacement launch.4.13.4 two controlled idle owned-process exits verified:material-only checkpoint restored,unsaved8-node/1-solid mesh excluded,repeat restart reuses child,newer nonempty child checkpoint retained. No in-flight crash/full scene/all-model lifecycle certification;legacy missing-sidecar keeps nonempty rule.

</details>

<details>
<summary>gui_selection.check_gui_keywords.scope</summary>

Actual native Keyword Check with contact excluded; complete report parsing, unchanged mesh, valid and missing-material/section synthetic cases verified; not solver validation

</details>

<details>
<summary>gui_selection.check_gui_shell_quality.scope</summary>

Actual native Model Checking: 13 selectable shell criteria; quad and triangle numeric/violation cases verified. Not full Keyword/Contact Check; dialog precision retained

</details>

<details>
<summary>gui_selection.inspect_gui_menu.scope</summary>

Owned 4.13.4 native menu inventory: 448 tree records, exact paths and IDs; discovery does not certify functions

</details>

<details>
<summary>gui_selection.combine_gui_selections.scope</summary>

Explicit user-ID union/intersection/difference/xor; all four verified through visible native selection Explicit operands now use streamed geometry/selection verification without global20000 bound; native100000shell-mesh intersection passed.

</details>

<details>
<summary>gui_selection.save_gui_selection_buffer.scope</summary>

Native buffer clear/reload verification; node slot1, shell slot3, part slot10 tested; model fingerprint bound Streamed whole-geometry identity replaces full snapshot;100000shell-mesh node Buffer save/clear/load and post-edit stale rejection passed.

</details>

<details>
<summary>gui_selection.load_gui_selection_buffer.scope</summary>

Native selection replacement/readback including target switching; reject changed model signatures Streamed whole-geometry identity replaces full snapshot;100000shell-mesh node Buffer save/clear/load and post-edit stale rejection passed.

</details>

<details>
<summary>gui_selection.select_gui_nodes_by_plane.scope</summary>

Signed reference-coordinate distance, normalized normal, tolerance; band/positive/negative verified Large-model native bridge predicate with complete streamed geometry fingerprints; no global20000 model cap, at most20000 selected nodes per operation. Native100000shell fixture passed boundaries, inside/outside/empty and plane-side checks; changed-box recorded replay checked against independent exported NODE coordinates. Reference geometry only.

</details>

<details>
<summary>gui_selection.select_gui_entities.scope</summary>

Native keyword/d3plot explicit, part-filter, whole, active-part and scoped-inverse selections use complete streamed geometry fingerprints and exact native selected IDs, preserving reference geometry/state/part visibility.100000shell native whole/large hidden parts/shared active nodes/inversion/empty scope passed; private solid d3plot over300000elements passed whole node/solid, hidden-part and selected-ID/field-CSV agreement. Whole/part command plans require exact set equivalence. Bulk selected-set guard1000000; explicit arguments/nonbulk fallback20000; no global model cap. Mixed standard shell/solid/beam, Blank, hidden-part selection and explicit display-setup replay passed 4.13.4. Before/after display-active descriptors checked. With inactive elements, native whole/part selection can omit hidden members: exact-ID fallback within20000 selected IDs is required; larger hidden selections reject before dispatch. This supersedes older blanket bulk/hidden-part claims. Deformed/pixel picking and physical alive/deletion classification remain unverified.

</details>

<details>
<summary>gui_selection.select_gui_entities.set_selection_scope</summary>

set_ids selects union of current same-domain node/part/shell/solid/beam explicit lists in a keyword model. Native export resolution and selection share one request lock; full export I/O cost; union up to20000.30-step visible4.13.4 BySet-to-node-set/SPC changed-set replay,refreshed membership,dirty/checkpoint preservation,hidden entities,inversion and reopen passed. Missing/unknown variants and old bridges reject; no result association or Segment/Generate/General/Collect expansion.

</details>

<details>
<summary>gui_selection.select_gui_nodes_by_box.scope</summary>

Reference-coordinate predicate followed by native ID selection/readback; not camera-space Area picking Large-model native bridge predicate with complete streamed geometry fingerprints; no global20000 model cap, at most20000 selected nodes per operation. Native100000shell fixture passed boundaries, inside/outside/empty and plane-side checks; changed-box recorded replay checked against independent exported NODE coordinates. Reference geometry only.

</details>

<details>
<summary>gui_selection.select_gui_nodes_by_sphere.scope</summary>

Reference-coordinate distance predicate followed by native ID selection/readback; representative d3plot test at changed state passed. Not deformed coordinates or alive-only filtering. Large-model native bridge predicate with complete streamed geometry fingerprints; no global20000 model cap, at most20000 selected nodes per operation. Native100000shell fixture passed boundaries, inside/outside/empty and plane-side checks; changed-box recorded replay checked against independent exported NODE coordinates. Reference geometry only.

</details>

<details>
<summary>gui_selection.renumber_gui_entities.scope</summary>

All node/shell/part IDs via native dialog and mapping log; coordinates/connectivity/parts and node-list sets checked; not every keyword reference

</details>

<details>
<summary>workflow.quality_gates.scope</summary>

Execution/check outcomes, automatic known-check gates, declarative predicates and threshold recording/replay. File-backend cases plus visible 4.13.4 allowed/blocked native edits verified by coordinates. Other versions and full workflow recovery not certified.

</details>

<details>
<summary>results.field_contracts.scope</summary>

ResultSelection/SamplingSpec/FieldSpec metadata in native SCL and LASSO field/stress paths. No native-layer/reader-slot equivalence, dimension inference or arbitrary history meaning. Request/export/parser tests only; no added native numerical certification.

</details>

<details>
<summary>gui.transaction_scopes.scope</summary>

Native keyword/d3plot explicit, part-filter, whole, active-part and scoped-inverse selections use complete streamed geometry fingerprints and exact native selected IDs, preserving reference geometry/state/part visibility.100000shell native whole/large hidden parts/shared active nodes/inversion/empty scope passed; private solid d3plot over300000elements passed whole node/solid, hidden-part and selected-ID/field-CSV agreement. Whole/part command plans require exact set equivalence. Bulk selected-set guard1000000; explicit arguments/nonbulk fallback20000; no global model cap. Beam native acceptance, deformed/pixel picking and physical alive/deletion classification remain unverified.

</details>

<details>
<summary>gui_mesh.set_gui_node_coordinates.scope</summary>

1..100 existing keyword nodes, absolute global XYZ with null axes preserved; native grouped translations, explicit tolerance, all-coordinate/topology and part-flag checks. Quality pass/failure, recording/parameter replay, checkpoint reopen/recovery, full XYZ and hidden-part/multiple-group cases verified. No CAD projection, load/material-axis updates or full Node Editing panel. Complete streamed topology/unrequested-coordinate digests plus requested coordinates; no global20000 bound.100000native-shell and over300000private-solid edit/save/reopen passed. Explicit correction limit100nodes; keyword references/quality remain separate.

</details>

<details>
<summary>engineering.convert_history_units.scope</summary>

Declared scalar-history time/value conversion; exact rational factors, dimension checks and range/underflow guards. Synthetic truth tests; no native/solver unit inference or affine temperature conversion.

</details>

<details>
<summary>gui_quality.check_gui_solid_quality.scope</summary>

Six native Hex8 criteria and per-criterion count/percent/zero-capture evidence. Optional native failed-user-ID capture validates counts/registry, exports criterion sets and returns their distinct union; explicitly overwrites Buffer1 and clears selection, preserves other slots. Noncontiguous ID localization and changed-threshold recording replay verified in 4.13.4. All-part flags restored; no inspection k exports. Other topologies/repair/solver validity remain outside scope.

</details>

<details>
<summary>workflow.preflight.scope</summary>

Static workflow composition: routes/modules, signatures, explicit parameters, forward-reference rejection, deferred bindings. No native capability/session/model certification.

</details>

<details>
<summary>workflow.parameter_study.scope</summary>

1..20 explicit sequential cases. Fresh child jobs, explicit GUI baseline, failure stop and scalar/CSV summaries. Two synthetic visible 4.13.4 Hex8 translate/check/save/reopen cases and analytical tensile curves verified. No solver, DOE optimization, branching or crash resume.

</details>

<details>
<summary>presentation.native_movie.scope</summary>

Visible Windows4.13.4 native H264 MP4; start1/step1 only, explicit fps/resolution and <=1800-frame/resource budget. Exact native log states and independently decoded count/rate/dimensions/duration required. ffprobe/ffmpeg validators required, no transcoding. Original current state restored; animation left stopped with output bounds; current display has no inferred fringe/layer/units. 57-state and3/4-frame recorded replay passed; arbitrary ranges/GIF/older versions/headless not certified.

</details>

<details>
<summary>presentation.native_curve_png.scope</summary>

Explicit CSV XY columns -> one new native XYPlot/PNG plus per-curve float32 numeric readback. Single-curve API retained; optional additional_curves support overlays,unique ASCII legend labels and identical declared axis units. No conversion/sort/resampling; different lengths/X grids and hysteresis preserved.100000 samples/curve,500000 aggregate,10 curves,32-window resource bounds. Visible4.13.4 synthetic3-curve4/3/5-point overlay and nested-source replay4/5/5 passed; prior plot data,model inventory/state and input files preserved. No implicit solver extraction,arbitrary styling or full XYPlot management certification.

</details>

<details>
<summary>presentation.named_native_fringe.scope</summary>

Visible4.13.4 named native field raw CSV/custom source buffer and PNG; explicit state/layer/units. Plain native result captions, model title preserved, default MinMax display averaging with explicit nodal/none. Raw entity samples stay unaveraged. Native solid Mises/pressure/mean stress and node magnitude crosschecks, fixed-range replay and managed-field movie passed; over300000-solid field-only path tested. New MinMax/None combo readback and three-frame MP4 passed. LASSO header prerequisites only. Shell/tshell nontrivial layers, rigid/deleted validity and frames remain unverified.

</details>

<details>
<summary>presentation.named_native_fringe.validity_scope</summary>

Explicit raw/alive. Static4.13.4 solid SCL values + LASSO physical deletion mask: native flags/CSV population/retained extrema/recording replay checked. Fixed-presentation excluded-buffer pixel invariance passed. Shell native verification uses an original known-truth synthetic binary; use the separate explicit PNG/FFmpeg method for physical movies; no node/tshell mask or old-build certification. Existing visibility budgets apply.

</details>

<details>
<summary>dpf.probe_dpf_runtime.scope, dpf.inspect_dpf_results.scope, dpf.export_dpf_result.scope</summary>

Optional local in-process Entry DPF adapter; client0.16.1 diagnostic and synthetic field/protocol tests only. Server absent: real reader, operator licensing/version and numerical comparisons NOT certified. Explicit labels/time IDs/units; no native LS-PrePost substitution. See docs/DPF_INTEGRATION.md.

</details>

<details>
<summary>common.measure_gui_geometry.scope</summary>

Native coordinates/distance/global-axis height/3D3-node and4-node angles/3-point circle radius and logged center. Keyword truth box, independent coordinate checks, preservation, collinear precondition and parameter replay passed; private d3plot current-state coordinates/distance passed with tail IDs and family hash checks. Active model tokens avoid stale model0. Projected angles uninterpreted; complete F4/F5 controls and annotation lifecycle remain open.

</details>

<details>
<summary>common.set_gui_entity_visibility.scope</summary>

Standard shell/solid/beam/element hide/show/isolate/reverse/owned restore; exact binary display-flag and geometry/state/part checks. Native 49-operation synthetic/mixed/private-result workflow, stale-restore rejection and managed replay passed. Protocol4 uses native keyword beam endpoints after array-binding heap faults; full export cost on beam-containing structural reads. Node glyphs/special entities/physical erosion remain open. One-million readback and 20000 explicit transition guards are not size certification. See docs/GUI_VISIBILITY.md.

</details>

<details>
<summary>gui_entities.create_gui_entity_set.scope</summary>

Native controlled fragment import of node/part LIST sets from IDs or owned current-model selection jobs; create/replace members, preserve DA/solver/ITS, collision/conflict rejection, exact native saved cards and streamed mesh/scene checks. 4.13.4 mixed standard elements, parameterized replay and reopen passed. At most20000 members, ASCII names, standalone decks; no arbitrary set variants/Include/full-panel certification.

</details>

<details>
<summary>gui_entities.create_gui_entity_set.element_list_scope, gui_entities.inspect_gui_entity_sets.element_list_scope</summary>

Shell/Solid/Beam explicit-list create/query; separate native layouts and typed user-ID checks.27-step visible4.13.4,12 sparse members/domain,scene preservation,per-domain SID namespace,rejections,recorded changed-member/SID replay and native reopen passed. Element-list replace_members,Generate/General/Collect,Discrete/Seatbelt/ThickShell and solver physics remain outside this acceptance.

</details>

<details>
<summary>gui_entities.inspect_gui_entity_sets.scope</summary>

Native full keyword export with node/part LIST inventory and paged member IDs; typed card parser handles fixed10-column/CSV lists without dropping members. Display/mesh/state checked. Full-export I/O cost; unsupported variants reported, not expanded. Also native Segment inventory and paged directed connectivity, including triangle padding and two-node edges, passed.

</details>

<details>
<summary>gui_entities.create_gui_spc.scope</summary>

Native SPC_SET and per-node SPC_NODE_ID with explicit six binary DOFs; node-list constraint IDs allocated consecutively in sorted node order and returned. IDs, coordinates, targets and supported SPC overlap checked. Global coordinate native create/replay/save/reopen passed. Nonzero coordinate references have code checks but not native certification; no rigid/material/solver validity claim, no prescribed motion/pressure/nonreflecting support.

</details>

<details>
<summary>gui_entities.create_gui_spc.conflict_scope</summary>

Parsed global prescribed motions and ordinal NODE TC/RC now participate in conflicts, in addition to existing SPC checks. No complete material/rigid/CNRB compatibility certification.

</details>

<details>
<summary>gui_entities.create_gui_segment_set.scope</summary>

Selection-bound native import/readback for conforming Hex8/Tet4 exterior, shell faces and XY edges, normal filtering/reverse, global topology ownership, preserved mesh/scene, replay and reopen. Native shell example Quad4; Tri3 geometric path not separately certified. Max20000 requested cells/created segments; no nonconforming intersections or pressure/NR/solver certification.

</details>

<details>
<summary>gui_boundaries.create_gui_segment_pressure.scope</summary>

Native DEFINE_CURVE and Segment-set pressure/named-ID loads; explicit unit dimensions, monotonic time, SID/curve-table-function/load-ID checks and reference normal sign report. Native readback, changed-scale replay and reopen passed for3D faces and2D continuum edges. No inferred model units, general function pressure, complete overlap detection or solver follower-response certification.

</details>

<details>
<summary>gui_boundaries.create_gui_nonreflecting_boundary.scope</summary>

Native3D Segment and2D modern negative-SID or legacy ordered two-node-set routes; documented targetsR11..16, unique exterior ownership,2D continuum formulation/order, namespace and overlap rejection, native endpoint order and reopen. Legacy2D requires explicit allocation start and default enabled waves. LSPP ingestion evidence only; no executed LS-DYNA/absorption/material/DR/stability certification.

</details>

<details>
<summary>results.physical_validity.scope</summary>

Explicit saved element deletion only; max1m state/entity pairs; missing masks/adaptive epochs reject; see docs/RESULT_VALIDITY.md

</details>

<details>
<summary>media.physical_field_movie.scope</summary>

Requires current verified alive solid/shell fringe and explicit fixed bounds. ALL alive entities in selected parts per frame; uniform FPS, no physical-time resampling. Explicit FFmpeg encoder, not native Movie command. Shell has an explicitly synthetic known-truth native case; other builds/headless remain unverified and all-deleted frames reject.

</details>

<details>
<summary>selection.shell_topology.scope</summary>

Keyword visible shells only; 1m reference/selection resource budget is not a large-scope runtime certificate. Leaves propagation/adaptive/3dsurf off. No result/adaptive/high-order/general nonmanifold certification. docs/TOPOLOGY_SELECTION.md

</details>

<details>
<summary>mesh.node_replacement.scope</summary>

Directed existing-node replacement; native Replace + targeted fresh-copy reference patch + native reopen. Complete snapshot limit20000; requires pinned PyDYNA. Include/parameter/other element families and known unsupported direct-node references reject. Part flags preserved, selection cleared, full scene/large model/solver/other versions not certified. docs/NODE_REPLACEMENT.md

</details>

<details>
<summary>automation.activate_gui_model.scope</summary>

Activate a unique managed resident keyword/d3plot by staged source or owned file-verified checkpoint alias. Native select uses refreshed row position; keyword memory saved before/after; source/type/list checked; managed selection/field caches invalidated. No reopen/unload. Active recordings reject; no all-model scene/crash or old-version/headless certification.

</details>

<details>
<summary>automation.unload_gui_model.scope</summary>

Unload one known resident model with an explicit distinct managed survivor. Saves keyword memory during preparation, verifies unique native display number, exactly one removed list entry and survivor reactivation. Retains removed keyword checkpoint; no source files deleted. Recording/uncertainty/ambiguous ownership reject. General replace/attach, full scene/crash recovery, old versions and headless remain separate. Keyword survivor must complete a source/count/file-bound post-removal export; failure preserves the pre-removal checkpoint and verified removal fact.

</details>

<details>
<summary>automation.unload_gui_model.result_pair_scope</summary>

Result-to-result removal uses a verified resident keyword intermediary before reactivating the requested result; absent intermediary rejects before removal. Explicit replacement creates an intermediary. Part of the visible general-to-beam replacement matrix; no general native stability guarantee.

</details>

<details>
<summary>automation.unload_gui_model.known_limitations, automation.replace_gui_model.known_limitations</summary>

NATIVE-REPLACE-001 remains unresolved: native angular-shell save can exit after removal even through GUI without redundant reselection. The post-removal export gate now reports failure inside unload/replacement. No automatic retry/restart or general stability guarantee.

</details>

<details>
<summary>automation.replace_gui_model.scope</summary>

Explicit same-process keyword/result replacement: saved keyword memory, verified new input before old removal, result-mode keyword staging and cleanup, remaining-model identity checks. Four kind combinations, explicit empty and unexpected-empty rejection, independent edited keeper and checkpoint recovery passed. No association, multi-model recordings, full scene/crash recovery, old-version or headless certification. Keyword survivor must complete a source/count/file-bound post-removal export; failure preserves the pre-removal checkpoint and verified removal fact.

</details>

<details>
<summary>model.create_gui_prescribed_motion.scope</summary>

Global NODE_ID/SET_ID motion; x/y/z/rx/ry/rz, displacement/velocity/acceleration, declared units/radians, new/reused time curves, explicit shared-group append, node selection dependencies and parameter replay. SPC/motion/inline NODE TC-RC and node-set-change checks. No rigid/local/vector/adaptive/solver or general lifecycle certification.

</details>

<details>
<summary>model.create_gui_nodal_load.scope</summary>

Global nodal force/moment x/y/z/rx/ry/rz; explicit units, per_node SET linkage or total_equal frozen POINT distribution, selection dependencies, curve creation/reuse, overlap review and intentional superposition. Mesh/display/cards preserved; explicit fresh-process reopen. No follower/local/rigid/load-ID variant or solver certification.

</details>

<details>
<summary>model.create_gui_nodal_load.known_limitations</summary>

Standard ELEMENT_MASS supported for structural preservation; mass glyph display, inertia/other auxiliary families, follower/local/rigid loads remain unverified. Full display proof is null when auxiliary glyph flags are unavailable.

</details>

## 原生驱动注释核对

逐文件扫描 tools/run_* 的注释；保留涉及语义或验证前提的原文作为补充证据。

- [run_element_set_acceptance.py](../tools/run_element_set_acceptance.py)：L154 Typed recording retains the selection-result dependency.
- [run_gui_fringe_acceptance.py](../tools/run_gui_fringe_acceptance.py)：L156 Reopened recording baseline clears old coverage: build a consistent contiguous pair.
- [run_gui_post_workflow_acceptance.py](../tools/run_gui_post_workflow_acceptance.py)：L120 Independent native quantity identity: position - reference = displacement.
- [run_mesh_page_acceptance.py](../tools/run_mesh_page_acceptance.py)：L44 Fixture is solid-only. The page's domain total checks this.
- [run_model_inventory_acceptance.py](../tools/run_model_inventory_acceptance.py)：L52 This command was recorded from Model Selection/Remove. Remove only the L53 initial empty model created by this test, not arbitrary user models. L74 The same second row is selected with `model select 2`, but its L75 recorded Remove command is `model remove 3` after the initial hole. L76 These namespaces must not be collapsed into one inferred model ID.
- [run_model_replacement_acceptance.py](../tools/run_model_replacement_acceptance.py)：L85 Explicit test recovery in a fresh owned process, not automatic replay.
- [run_program_bundle_acceptance.py](../tools/run_program_bundle_acceptance.py)：L61 The macro must use its captured config, not this subsequently changed original.
- [run_public_motion_acceptance.py](../tools/run_public_motion_acceptance.py)：L112 Explicit diagnostic option: this branch has a retained native L113 failure on the public angular fixture; do not count it as passed. L125 Explicit acceptance step, never automatic application fallback.
- [run_reset_recovery_acceptance.py](../tools/run_reset_recovery_acceptance.py)：L61 Controlled native fixture setup, not a claim that the high-level raw L62 program API supports every empty-model import/context transition.
- [run_resident_activation_acceptance.py](../tools/run_resident_activation_acceptance.py)：L89 The native path now reflects A's latest saved checkpoint, not L90 its original staged input. Public activation must resolve either.
- [run_result_validity_acceptance.py](../tools/run_result_validity_acceptance.py)：L69 A present entity remains eligible even when explicitly blanked in the GUI. L104 Perturb excluded buffers only. Reapply identical averaging/range because L105 SCLFringeDCToModel itself resets presentation defaults.
- [run_scoped_mesh_acceptance.py](../tools/run_scoped_mesh_acceptance.py)：L43 Normalize to native save precision before testing a later save/reopen.
- [run_selection_scene_acceptance.py](../tools/run_selection_scene_acceptance.py)：L81 Recorded workflows reopen their keyword baseline; explicitly record L82 display setup because a keyword checkpoint does not store Blank flags.
- [run_session_recovery_acceptance.py](../tools/run_session_recovery_acceptance.py)：L36 Use a new host service object: no in-memory request handles are reused. L74 An actual native transform finishes, but its host-side comparison is L75 deliberately absent. Recovery must not certify that transaction. L112 Fault injection is restricted to the exact process created by this test.
- [run_shell_validity_acceptance.py](../tools/run_shell_validity_acceptance.py)：L53 Only deleted high-stress entities are requested in this part at state3. L59 Reopen the unchanged fixture to start the positive sequence with clean Blank.

## 已扫描源文件

下列文件已逐文件读取并参与全文/范围/注释扫描；哈希对应归档前的 UTF-8 文本（能力 JSON 为文件字节）。这份清单证明扫描范围，不能替代尚待补齐的原生复现实验。

- [docs/ARCHITECTURE.md](../docs/archive/2026-10/ARCHITECTURE.md) — `2ee376c58dd72aa2dc43c62267e0815135ed4700ea633377cc9ec8e4d89b4eba`
- [docs/BACKENDS.md](../docs/archive/2026-10/BACKENDS.md) — `d080546beac0a88794482c8bbdd0466ae6fb94b0004a4bcf431c7f0964c3b08c`
- [docs/BACKLOG_REVIEW_2026-10-01.md](../docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md) — `f6539ed88a43cf7156635154af02e5584ffb139206816d13f923fe5de434e917`
- [docs/BOUNDARY_CONDITIONS.md](../docs/archive/2026-10/BOUNDARY_CONDITIONS.md) — `dfbe275576aaa7d62fae08fb2c562e16a53f9a43ccc6c73600cfcf781c70d529`
- [docs/COMMON_OPERATIONS_COVERAGE.md](../docs/archive/2026-10/COMMON_OPERATIONS_COVERAGE.md) — `8463f3360fb8eba57b25d5746fb51739a5436ed950874264802b5f12c186658c`
- [docs/COMPATIBILITY.md](../docs/COMPATIBILITY.md) — `fad8b60f308c113280d719e41105c8731c5bbdc89baace8ba8d3a24adb78867b`
- [docs/COVERAGE.md](../docs/archive/2026-10/COVERAGE.md) — `7e6db7073ae0bbe9b86227399ac53a7497d9d2447bffecf76dfdf00a5de6ee75`
- [docs/DELIVERY_PLAN.md](../docs/archive/2026-10/DELIVERY_PLAN.md) — `873843d31b1592e05a702e4b028efa457ec4d9b921839498d7d8a1d858b98048`
- [docs/DPF_INTEGRATION.md](../docs/archive/2026-10/DPF_INTEGRATION.md) — `b41138494052711d6814d2fbb291439307c137830783e3249fdc14018248ea66`
- [docs/ENTITY_CREATION.md](../docs/archive/2026-10/ENTITY_CREATION.md) — `023d883a8d32047d86d7aec134a72553630335ece9710685dc6cbd5101966737`
- [docs/FEATURE_GAP_AUDIT_v0.2.0.md](../docs/archive/2026-10/FEATURE_GAP_AUDIT_v0.2.0.md) — `e200423a520b8afe1c538f9b997173ffecc8644de605f21b616730763145df2d`
- [docs/FIELD_MOVIES.md](../docs/archive/2026-10/FIELD_MOVIES.md) — `813a58e59c111dcd6e6b31b007c484a8fef3b69edcb3476abbbeadf196873cc2`
- [docs/GUI_CAMERA.md](../docs/archive/2026-10/GUI_CAMERA.md) — `904c3c92a8afb288df16bd8948aab518adeb0d4bb6f6075d288aa562f452a213`
- [docs/GUI_MEASUREMENTS.md](../docs/archive/2026-10/GUI_MEASUREMENTS.md) — `94032ebf5d04965db6c271a92b148eab4e56624a4129b345b12a41a50b4936cd`
- [docs/GUI_VISIBILITY.md](../docs/archive/2026-10/GUI_VISIBILITY.md) — `5de538c4aa8828e62e336156fe3ce716da2186e9d45dd14b503df68d5b9887af`
- [docs/GUI_WORKFLOWS.md](../docs/archive/2026-10/GUI_WORKFLOWS.md) — `59312a684aef6c8631454bebd31f76ad270648c73b939870d17d152a18eac1a6`
- [docs/MASS_PRESERVATION.md](../docs/archive/2026-10/MASS_PRESERVATION.md) — `b79c1de828462428ea85f1667347a352d5722f806198e7053b2fcc6d882b79ee`
- [docs/MCP_TOOL_PROFILES.md](../docs/archive/2026-10/MCP_TOOL_PROFILES.md) — `6f3f530addc9ba2054cb04f923e28c69105c7d808b27cbb519123f51c13cadd1`
- [docs/MODEL_REPLACEMENT.md](../docs/archive/2026-10/MODEL_REPLACEMENT.md) — `1154dad49ee726102f6464464da3e3e84907abf49dcc64a1688e52a62ef45e5f`
- [docs/MODEL_SCALE.md](../docs/archive/2026-10/MODEL_SCALE.md) — `8869225b1a04484d1918faa9a3e66d0c6ffe104349a1bdbe12d34694268fe6ac`
- [docs/NATIVE_KNOWN_ISSUES.md](../docs/archive/2026-10/NATIVE_KNOWN_ISSUES.md) — `2d4053965e693fc7bfb551596d95a7c069862fd4d82a90eb13f1cd27bc6f01d5`
- [docs/NATIVE_MEDIA.md](../docs/archive/2026-10/NATIVE_MEDIA.md) — `bfb3ea2152b3c5a303152fe4a17d752b0f5ef89b44a5869d6881812c9b741954`
- [docs/NATIVE_PROGRAMS.md](../docs/archive/2026-10/NATIVE_PROGRAMS.md) — `879d84fcb223ce4411239cb4f5f07edc89fd1b1f11f244d7bda2acd2492b43db`
- [docs/NODAL_LOADS.md](../docs/archive/2026-10/NODAL_LOADS.md) — `e8eb2b4f9eb1c69ae5103f2ba9763f48e77eace9c92f7131579708b4b21a4958`
- [docs/NODE_REPLACEMENT.md](../docs/archive/2026-10/NODE_REPLACEMENT.md) — `a14a8c13c796d5b98c74cef53cfea782419281b613ec7c9acf28d3d9dc7e8b40`
- [docs/POSTPROCESSING.md](../docs/archive/2026-10/POSTPROCESSING.md) — `cb55ad6c6a2a939b80103f4ad24a5d60eaaf51c5448b2c2cbf0cf23e5b157010`
- [docs/PRESCRIBED_MOTION.md](../docs/archive/2026-10/PRESCRIBED_MOTION.md) — `f8b5b78d3de2e9f4996036c9466e9d9812db3f81cf57400322c53d4d4ba8206f`
- [docs/PROGRAM_BUNDLES.md](../docs/archive/2026-10/PROGRAM_BUNDLES.md) — `b84d5f15e6f7d9fc24c9231aa291fc9dd0febfb45a1e51c53ea7500f2bd9667e`
- [docs/PROGRESS.md](../docs/archive/2026-10/PROGRESS.md) — `4e5ee6e4e48bd08bdb43e81db9603303d357554c7d0a4a0277dcf8ac21ff01d2`
- [docs/PUBLIC_TEST_CORPUS.md](../docs/archive/2026-10/PUBLIC_TEST_CORPUS.md) — `74934860ddaebd73b83beee63598699a64ce8e470edd8d1d85f9f11eec196542`
- [docs/PYDYNA_INTEGRATION.md](../docs/archive/2026-10/PYDYNA_INTEGRATION.md) — `46b8cce938225f8171f1378d1e08c7b6da487f3d93dde159ec392fbd965ab1d1`
- [docs/REQUESTS_AND_PRIORITIES.md](../docs/archive/2026-10/REQUESTS_AND_PRIORITIES.md) — `9dc9f529d412f581fc3183368fa647ec1faceecc1b55fa055615f6b5581db329`
- [docs/RESULT_CONTRACTS.md](../docs/archive/2026-10/RESULT_CONTRACTS.md) — `7db399431bb525a4d1e6d3653bc86484b5f853418358e6d0ee33bc3a7c49bcb8`
- [docs/RESULT_VALIDITY.md](../docs/archive/2026-10/RESULT_VALIDITY.md) — `369cf923ad4cbf11278441b8e7d61af41278eefd6c1a3df493b46f449ff933b7`
- [docs/REVIEW_RESPONSE_2026-10-03.md](../docs/archive/2026-10/REVIEW_RESPONSE_2026-10-03.md) — `8e16de2a66181239285b10bfbd15f60edf5be2386f9ea919264bcebc4da74782`
- [docs/ROADMAP.md](../docs/archive/2026-10/ROADMAP.md) — `c37b575a2688e7cfb6340776c6fe8817fa8b988d7838da85ea6476da3b953850`
- [docs/SEGMENT_SETS.md](../docs/archive/2026-10/SEGMENT_SETS.md) — `52d626dc44f9770e960c43218be2f8dcbe7878312adf2f7d2d94ae1d9d203a9c`
- [docs/SESSION_RECOVERY.md](../docs/archive/2026-10/SESSION_RECOVERY.md) — `058234e612770052b6fc38d986ae6c26e3644d670578558f253a615b079779f9`
- [docs/SOURCE_ADOPTION.md](../docs/archive/2026-10/SOURCE_ADOPTION.md) — `d3309c91b5379d1226bdada1417d6a0bf20eb78189318cfc17e347016bae4c73`
- [docs/SOURCES.md](../docs/archive/2026-10/SOURCES.md) — `c64cca340122ef6511553ea8e1832721d03eb35f29abea78b19eb7eaf8f233a0`
- [docs/TOPOLOGY_SELECTION.md](../docs/archive/2026-10/TOPOLOGY_SELECTION.md) — `0cc944092811a32e99f647b0145de52e237dba805eb560bc4a7a4d5eab6eb37d`
- [docs/TUTORIAL_INTEGRATION.md](../docs/archive/2026-10/TUTORIAL_INTEGRATION.md) — `4b64eb59cc2a463f76d02db8c8eb16628173399cf119797516bc1ef319617265`
- [docs/UI_AUDIT_POST_GAPS.md](../docs/archive/2026-10/UI_AUDIT_POST_GAPS.md) — `2cdf82af42ba93b8623e8926a3f4f97841156dbe332637f3d44691b08fba2b0e`
- [docs/UNIT_CONTRACTS.md](../docs/archive/2026-10/UNIT_CONTRACTS.md) — `f6d40dc3a3b9c3a6bd4cbf52fc50eecfb96b085e824a7160a11051591e272da0`
- [docs/VERIFICATION.md](../docs/archive/2026-10/VERIFICATION.md) — `fe8f095bf8be31843619b57c4367c98bbff91fd9fec885228d6d51cd051243ca`
- [docs/WORKFLOW_FRAMEWORK.md](../docs/archive/2026-10/WORKFLOW_FRAMEWORK.md) — `2153d008d8fc241ae3e891fbbd61dd6da9bc4083629ecc9ae0213a128de0dcaf`
- [docs/WORKFLOW_GATES.md](../docs/archive/2026-10/WORKFLOW_GATES.md) — `7f6bfed95e869d33e4aff2bca0d387301149134f17d2f42d1912bb3c0c0a3fc7`
- [docs/WORKFLOWS_v0.3.md](../docs/archive/2026-10/WORKFLOWS_v0.3.md) — `e71e83d13ec3c78cb69108777b486ea076bba1b9a300ac4d924e46ce5454fb60`
- [tools/run_boundary_creation_acceptance.py](../tools/run_boundary_creation_acceptance.py) — `70685dc3228340f785a9424bbba4d3744464ebfe0347cd1745a5e817c1e4900e`
- [tools/run_bulk_selection_acceptance.py](../tools/run_bulk_selection_acceptance.py) — `6c99d9515386f44e83586fddfcd02cd8336197b16a3f4e9cbfb0945e52412fad`
- [tools/run_checkpoint_context_acceptance.py](../tools/run_checkpoint_context_acceptance.py) — `6a190e6627ce6e14e08510e81d28f61fac98e12ea21fa4ad25fad4ad6f934da7`
- [tools/run_element_set_acceptance.py](../tools/run_element_set_acceptance.py) — `e3b8c8d4ff0b5d773806495f59d8105b6c7eca8d79304a7c8011cf2ba3101a57`
- [tools/run_empty_recording_acceptance.py](../tools/run_empty_recording_acceptance.py) — `c7098927f57ec08c17293a94a97c10514fbb17342da85dbaa03376f197bc2562`
- [tools/run_engineering_unit_acceptance.py](../tools/run_engineering_unit_acceptance.py) — `cb3701ab655e3ddf9a97363f82bb06b91d08b65900076aa2b61af722d29b0af6`
- [tools/run_entity_creation_acceptance.py](../tools/run_entity_creation_acceptance.py) — `90165bff5c6e3ec9a5502d12d84ef4aea629ad5e4314089629417e1dbd043d9d`
- [tools/run_fringe_presentation_acceptance.py](../tools/run_fringe_presentation_acceptance.py) — `f84523c968c5624c44908940bd4da12b8ed66b85e96f481718615a30b7526d55`
- [tools/run_gui_binout_acceptance.py](../tools/run_gui_binout_acceptance.py) — `59928f32e4ac11fdab6db35b84c8433e2042d657b81922be2ac5e8cb571b262d`
- [tools/run_gui_camera_acceptance.py](../tools/run_gui_camera_acceptance.py) — `6981c3608a6bb91e25cf02516bbb5d8acb960d758f5ef12968dc810d51b980fc`
- [tools/run_gui_coordinate_acceptance.py](../tools/run_gui_coordinate_acceptance.py) — `8e2748e239e8194845301f663c576bb2b90e6c6f81c9cf578dc947259ddbf9d5`
- [tools/run_gui_curve_acceptance.py](../tools/run_gui_curve_acceptance.py) — `12173985b8cf132b6cfd7ad28f2dab5ad92c0cd585e7fdc40f57d462c427b2c9`
- [tools/run_gui_failed_ids_acceptance.py](../tools/run_gui_failed_ids_acceptance.py) — `f11f8007b90f5071ec7bd56527a4b7b5cf4aba5cb45d2fdda3dfc8e2675a9cd2`
- [tools/run_gui_fringe_acceptance.py](../tools/run_gui_fringe_acceptance.py) — `5928ff58dd3ee4f58f157dbd6ac79008c7252f02b82890eb85913ee6cddfc3fb`
- [tools/run_gui_gate_acceptance.py](../tools/run_gui_gate_acceptance.py) — `11a9f575028dc06bab8df9fb2fe9f2b490728c98c6436bf2453d9a610faa725c`
- [tools/run_gui_hex_edit_acceptance.py](../tools/run_gui_hex_edit_acceptance.py) — `a7ac4a915297bbab802ff796c251049d66255a38a7779263444c6a2398fa2c6d`
- [tools/run_gui_measure_acceptance.py](../tools/run_gui_measure_acceptance.py) — `a7e573d3b00d52659421e424e01ecae898e42bad020443347d9b036cda1101cb`
- [tools/run_gui_movie_acceptance.py](../tools/run_gui_movie_acceptance.py) — `2a5a32f83e6027fb9ee53c0ebc9bc021119f64331f6a421327d5ec1cffdec23a`
- [tools/run_gui_post_workflow_acceptance.py](../tools/run_gui_post_workflow_acceptance.py) — `967ec8381fb21d0dacb42af5ae75d26357816dd4bcd3c34b0a0a81d000e09910`
- [tools/run_gui_solid_quality_acceptance.py](../tools/run_gui_solid_quality_acceptance.py) — `8dec0f9560b3ab2fce99079a02704a2549bfe7a29a85e09f2a59db757ea81e5a`
- [tools/run_gui_visibility_acceptance.py](../tools/run_gui_visibility_acceptance.py) — `18f8d2ca2408e323f449c5cd4e41946f5e65f438b84c37e9be9a7af71bdc9eb6`
- [tools/run_large_normals_acceptance.py](../tools/run_large_normals_acceptance.py) — `81c95da50edafdf3a823ccf5323ed2f5a09626101d6aecf32016b87124c87441`
- [tools/run_mass_preservation_acceptance.py](../tools/run_mass_preservation_acceptance.py) — `4e69506a82adecd6a7b3caf1d0c0560f4565eb18931aac8f2e77c33c06674595`
- [tools/run_mesh_page_acceptance.py](../tools/run_mesh_page_acceptance.py) — `37727efd966b2715ec0a877cab6f71849603a3f96d8e01952fa3822157d7aa98`
- [tools/run_model_inventory_acceptance.py](../tools/run_model_inventory_acceptance.py) — `53e38318619f6365fa4f0a0ece8431a565d325890c7b8781946edc32401f41b8`
- [tools/run_model_replacement_acceptance.py](../tools/run_model_replacement_acceptance.py) — `05eeaa9c0d7dd4474bb99398e9e0f2e2d3ba17a4d7c3868ca89a8822be2fece8`
- [tools/run_multicurve_acceptance.py](../tools/run_multicurve_acceptance.py) — `47bb346dc98e6ec462756fe5950aad49553cedcf3982bcae1d270cdaf0d1c5e6`
- [tools/run_native_acceptance.py](../tools/run_native_acceptance.py) — `c8c43f8e4b99db2e78feb712971c2b831f7a694151bd75b167de7c87ca150338`
- [tools/run_nodal_load_acceptance.py](../tools/run_nodal_load_acceptance.py) — `8f9db3429a554c20fd884a187ffcdf50c409ccd6d38e521568637191bb8fd3d0`
- [tools/run_node_replacement_acceptance.py](../tools/run_node_replacement_acceptance.py) — `4305fc0c4a100121c7f88e7c1f82b33074a01e8747a7a75be1b25202a1694de2`
- [tools/run_parameter_study_acceptance.py](../tools/run_parameter_study_acceptance.py) — `2fa50fe00781c82dd9a38e2dafd0ebf92287030c8a9e1ce90e2651b4fd067009`
- [tools/run_physical_movie_acceptance.py](../tools/run_physical_movie_acceptance.py) — `9d2b0f90cedfa8ffa360493c690c4247edd712fe484fc42cdd97a66a60ddd137`
- [tools/run_prescribed_motion_acceptance.py](../tools/run_prescribed_motion_acceptance.py) — `82e491ccf3430de876e63c6d4ed843560442ef2d6115dd3ee58a5af5acd5787f`
- [tools/run_program_acceptance.py](../tools/run_program_acceptance.py) — `297d130ebdcaf3000bce74a8776a0515644cf404149c9eef7e47fb2a418fa3f9`
- [tools/run_program_bundle_acceptance.py](../tools/run_program_bundle_acceptance.py) — `db784ba7c0bd8961a786075ba0d61e6e88f44326cd0b3b1223deade1cd9375c3`
- [tools/run_public_motion_acceptance.py](../tools/run_public_motion_acceptance.py) — `2d768313b1957cb1f918401f16fab23501b4c42901e33c05e0abcdda7da2d262`
- [tools/run_public_nodal_load_acceptance.py](../tools/run_public_nodal_load_acceptance.py) — `7f4f18ad3a7df6a33c1782ed7635b50f79f5a3bf0deef7e6079b908c2916783d`
- [tools/run_reset_recovery_acceptance.py](../tools/run_reset_recovery_acceptance.py) — `c3526dc04ac5764e666ede26298aed8b6ba97709b8927c82612b7a4b6ac6d520`
- [tools/run_resident_activation_acceptance.py](../tools/run_resident_activation_acceptance.py) — `3f61635979b93374dd60b4610f15035d1538fdee0df6c2ef7094a7a849875529`
- [tools/run_resident_unload_acceptance.py](../tools/run_resident_unload_acceptance.py) — `310b8f9360226e16b11b6bc14af655d900b9552704662bd8788c69eb5ef2bda1`
- [tools/run_result_bulk_selection_acceptance.py](../tools/run_result_bulk_selection_acceptance.py) — `fa3fde58b772875fa320056db32a6bc4dcc41732c80c0ff37093b0ced99c2f31`
- [tools/run_result_selection_acceptance.py](../tools/run_result_selection_acceptance.py) — `e3aeaac20625b1296e0d2011da68e7dd5cb0d82c0cc898b44b9c67eae9389eff`
- [tools/run_result_validity_acceptance.py](../tools/run_result_validity_acceptance.py) — `cf0d5554f88dbe649a7959fc554972303d5b3a75ed136c7b48c503b2e462fab0`
- [tools/run_scoped_mesh_acceptance.py](../tools/run_scoped_mesh_acceptance.py) — `e654a15a95dbe0a9b999a85a64f7f8ecfd75043f28cce86f3b88689b4a292d79`
- [tools/run_segment_creation_acceptance.py](../tools/run_segment_creation_acceptance.py) — `b6f2c15192ab365b5cb5d32c369d415a9a6d89531961c6424edef71fd05f6226`
- [tools/run_selection_scene_acceptance.py](../tools/run_selection_scene_acceptance.py) — `e3b8b25c7e547179203df7fda2c4cd22bef0101ecc0ccfcc1ae87f586cd97e1b`
- [tools/run_selection_visibility_acceptance.py](../tools/run_selection_visibility_acceptance.py) — `032943b7df999527b04b27ace66324892d41b3eb01af0b642b2198b2021635f4`
- [tools/run_session_recovery_acceptance.py](../tools/run_session_recovery_acceptance.py) — `f883be763f50f0390bc6ebf115849ccc1592d3b597f75d3e1c325f92dd0c319f`
- [tools/run_set_selection_acceptance.py](../tools/run_set_selection_acceptance.py) — `a4f508b953c3b54ecad21e52fb36de55cec99aa361173d6c25885832b366d935`
- [tools/run_shell_validity_acceptance.py](../tools/run_shell_validity_acceptance.py) — `6efdacf0216090275dd1ed82d3b3f947eca4a2d96c95b8e0643c95d0292fdf42`
- [tools/run_spatial_selection_acceptance.py](../tools/run_spatial_selection_acceptance.py) — `0d8355582a30bd937bc093f31a8ffa31a0b58b547efb31f0c9baa2b7357d0949`
- [tools/run_stale_model_regression.py](../tools/run_stale_model_regression.py) — `ea004b53b5ef80d5e2621cad7620da61a9d3ddd873eefd173e6858ee5917222a`
- [tools/run_topology_selection_acceptance.py](../tools/run_topology_selection_acceptance.py) — `f96543e992ba1bb8e2b680196b1a9277d55a2666b1a769ea5e3e58e7f8be254d`
- [tools/run_workflow_acceptance.py](../tools/run_workflow_acceptance.py) — `76d528b11e2b948c224be291c9660f53cf04cc2712c5a9f29b1f87a92bd236ba`
- [tools/run_workflow_gate_acceptance.py](../tools/run_workflow_gate_acceptance.py) — `cd6759202440b9321ea95aed7faf292b5a3a38c0183794821fba27a32325edfd`
- [src/ls_prepost_mcp/data/capabilities.json](../src/ls_prepost_mcp/data/capabilities.json) — `bb76b2e66358b4f93338c845c218f66bddbf4121567aa058128a07c7c67112aa`
