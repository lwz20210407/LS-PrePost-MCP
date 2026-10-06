# 架构

本页定义 v0.5 的目标架构，迁移顺序和验收标准以 [tasks.yaml](../tasks.yaml) 为准。M0 保留当前实现；core、engine 与领域层在 M1 起渐进迁移。

## 产品职责与能力层

MCP 提供执行、观察、验证、知识检索和工程计算。Agent 负责理解意图和组合任务。

| 层 | 交付形态 | 使用方式 |
|---|---|---|
| T1 | 高频、语义风险高的类型化任务，名称由 target_tools 规定 | 严格参数与结果合同；相近操作使用 action 判别联合 |
| T2 | recipe.yaml、cfile/.mac/py/scl 模板、输出检查、一个 L2 用例 | find_recipe / run_recipe |
| T3 | Agent 查知识库后编写的自由脚本 | run_script 后检查产物 |

反复成功的 T3 可提升为 T2；高频、高风险 T2 可提升为 T1。长尾功能通过脚本与知识检索支持，不按按钮扩张工具数。

## 执行

`Engine.run(job) -> JobResult` 统一执行。BatchEngine 默认每个 job 一个进程，使用配方实测可用的 `runc=` 或 `c= -nographics`；输入副本、命令、日志、产物归属 job。SessionEngine 用于大模型多步处理和观察，可见窗口是选项。会话请求不隐式切换后台实例。

现有会话链路是 cfile + 应用内 bridge + complete.json；Win32 当前只承担触发。是否可改为桥接端自行轮询由 I10 的 E1–E5 决定，见 [传输实验](decisions/0001-session-transport.md)。共享配置隔离、增量日志读取、请求关联和产物身份检查在引擎层收敛。

I01 已将五个批处理调用方收敛到 `runner.execute → BatchEngine.run(BatchJob)`，旧 process 字典仅作为兼容投影；无领域验证的零退出码返回 unverified，原有计数、数值、产物和源文件身份检查继续决定工具结果。`Sessions.dispatch → SessionEngine.run(SessionJob)` 统一提交、超时、回执关联与 JobResult，保留迟到回执供恢复，禁止自动重放。

两条引擎共用 `engine/environment.py` 的独立配置副本和 TEMP/TMP，用户配置原文不改；日志统一由 `core/native_log.py` 读取请求后缀并拒绝截断/丢失。`gui_session_action` 通过每个 Service 的 ContextVar 显式绑定会话执行器，退出或异常后复位；不再创建临时 Service、替换 `_native` 或用后台进程替代旧会话变换。

`Sessions.start(transport="queue")` 是 I01 内部非交互入口：loopback 接收线程只收带会话凭据的请求 ID，应用主线程执行，回执仍为 complete.json。重复通知和已执行请求不会重放，关闭信号在当前请求结束后退出。4.13 已验证同 PID 连续读取、保存和重开；4.10 的批处理子集通过，队列模型来源检查受 KI-048 限制。公开 `start_gui_session` 继续使用 Win32 观察通道；五通道统一的公开入口属于 A01–A05。

Command、cfile、SCL、应用内 Python、原生宏是五个一等通道，统一接口 `run_script(language, context=batch|session)`。宏支持 `*macro begin/end`、parameter、`&name`/`&{name}` 和 `(n/e/p)` 拾取域，拾取值由 Selector 绑定。现有 create_native_macro/run_native_macro 是 JSON 模板，将并入 A08 配方库并保留旧别名至 v0.6。执行通道不是不可信代码沙箱。

## 合同与领域操作

I01 经审阅改为 partial/L1：历史批处理和队列六例不覆盖公开 Win32 传输。
缺配置拒绝与对外诊断透传已补回归；公开 Win32 打开、读取、检查点保存重开及同 PID 复用已通过 4.13 原生测试，见[补测报告](decisions/evidence/i01-followup/report.md)。其余 GUI 修改路径统一仍是 tasks.yaml 中的明确缺口。
[历史原生报告](decisions/evidence/i01/report.md) 保留已执行范围，不作为 I01 全部完成依据。

`core/contracts.py` 使用 pydantic 定义：

| 对象 | 语义 |
|---|---|
| ModelRef | 文件族、输入身份、模型类型、单位、Include 树 |
| Selector | 实体域、真实 ID/Part/集合/几何谓词、坐标状态、有效性 |
| FieldSpec | 量、分量、单位、层/积分点、坐标系、平均、失效掩码 |
| CurveSpec | 来源、实体、分量、时间轴、单位、符号、滤波与对齐 |
| JobResult | succeeded / failed / partial / unverified；检查项、证据、警告 |
| Artifact | 路径、哈希、类型、语义元数据 |

工作流门槛只读 JobResult，执行完成与工程检查通过分别表达。API 使用用户 ID 和 1-based 状态；单位由调用者声明，阈值由调用者给定。保留结果数学与独立逻辑测试。

I02 的六个 pydantic 合同已在 [core/contracts.py](../src/ls_prepost_mcp/core/contracts.py) 实现，core 仅依赖标准库与 pydantic。选择条件、采样和过滤参数使用判别联合；字符串/布尔值不会转成实体 ID，显式 ID 列表不能为空，空选择使用 `kind="none"`，参考/变形坐标及 1-based 状态分别校验。ModelRef 的 Include 条目只是文件身份和父子关系元数据，I07 负责解析与编辑。

旧操作返回值在 outcomes.normalize_outcome 中一次转换为 JobResult；prepared 只在明确的准备动作上对应 succeeded + preparation 阶段，未知状态转为 unverified。workflow_checks.evaluate_gate 仅接收并重新校验 JobResult，执行状态和自动质量结论不再从原字典判断。comparison_data 仅用于兼容旧工作流中用户指定的 JSON 路径断言；旧步骤结果、门槛报告和 outcomes.json 投影保留。类型化结果带 `contract: JobResult/v1` 标识，JSON 持久化或录制后仍按同一合同恢复，保留检查结论与准备阶段。

合同实例构建不访问文件、不执行原生动作；产物真实身份、数值正确性和后端/版本能力仍由运行器及检查器验证。缺少 SHA256 的旧产物不会被升级为完整身份已验证。领域工具输入的逐项迁移继续按所属任务执行。

### FieldSpec 迁移约定（I02 → M2）

`core.contracts.FieldSpec` 是新的领域请求：量、分量、Selector、时间选择及采样均显式输入。
仍在使用的 `field_contracts.FieldSpec` 是旧结果请求/出处描述，包含已展开的 fields、
ResultSelection、SamplingSpec 和 transformations。两者没有类型或语义等价关系，不能
仅改 import 或直接把旧字典传入新类。当前 I02 不宣称这七个旧调用方已迁移。

M2 按所属结果任务迁移：先解析 Selector 为用户 ID 和 1-based 状态，再由后端适配器
映射 quantity/components 到旧字段名称。native layer/积分点与 reader stored point 不
自动互换；DPF location、transformations 等新合同尚未覆盖的语义须显式保留或拒绝。
迁移时需补采样、坐标系、平均和失效语义的等价回归；完成前使用完整模块名区分二者。

JobResult 的 failed 必须带非空 error；partial 必须说明 error/warnings，且有 data 或
artifact。检查聚合忽略 not_applicable；只有全体均不适用时才返回 not_applicable。

## 原生命令与版本能力

`native/commands.py` 集中生成选择、传播、缓冲区、动画、状态、云图和色标范围命令。构建器拒绝布尔/字符串 ID、越界槽位与可注入命令的参数；节点/单元使用真实用户 ID，状态从 1 开始，原生缓冲区从 0 开始。命令文本和分号格式由黄金输出测试固定，实际选择、状态与图像另外走原生回归。录制器保留命令解析语法，不承担命令生成。

宿主与应用内 bridge 使用同一份构建器。批处理和会话在自有目录暂存 bridge.py、native_commands.py、native_versions.py；支持模块仅依赖标准库，保持 Python 3.6 语法兼容，按自身文件路径加载，不依赖应用内 Python 安装宿主 MCP 包。

路径命令通过 quoted_path、open_model、print_png、movie、run_script、save_keyword 构建；
生成的 cfile 使用同一个 UTF-8/LF 写入入口。保留 POSIX 与原生 Windows 两种经调用方明确
指定的路径形式，统一字符校验。黄金测试覆盖空格、中文以及分号/引号拒绝；它不替代
原生工作目录兼容性验证。KI-049 和 GUI/Movie 的未测部分使 I03 继续保持 partial。

`native/versions.py` 是版本能力判断入口：4.13 主力、4.10 回归子集、4.8 尽力、4.11 排除。4.10 队列来源身份限制在进程启动前拒绝；未知安装也不能默认使用已验证队列能力。路径或配置版本仅是提示，能力报告明确标为未完成运行时验证，成功仍需实际回执与产物检查。旧 Python 向量 ABI 以及 LASSO/DPF 依赖版本的既有拒绝策略集中维护，不放宽数值验证要求。

## 运行时注册与兼容别名

`data/operations.json` 是运行时操作元数据，包含稳定内部 operation_id 所需的域/名称、上下文路由、工作流可用性及兼容期。`operation_registry.py` 派生 MCP 名称、会话路由与工作流白名单；旧名作为同一类型化函数的兼容别名保留到 v0.6，compact 接口同时接受稳定 operation_id。目标 T1/配方归属是迁移元数据，不据此声称尚未实现的任务已完成。

运行时不再读取 development_plan.json 或 tasks.yaml；TOOLS 与 tool_migration_map.yaml 由实际 registry 生成并在 CI 核对。共用参数检查已移到 core/validation.py，Service 保留旧导出；原生批处理的渲染阶段显式接收回调，不向上构造 Service。import-linter 禁止下层导入编排层、禁止 core 依赖 engine/native，并限制只有 CLI/server 可直接导入 Service。没有忽略规则绕过这些约束。

## 前处理

I07 由 Claude 在 `claude/keyword-engine` 开发，M3 经 PR 合入。代码在 `src/ls_prepost_mcp/domain/model/`（关键字引擎与前处理操作）和 `domain/results/`（LASSO 读取、曲线运算、应力不变量、MPP 分片 binout、场导出）。M3 目标工具 model_info、edit_keywords、create_entities、mesh_ops、check_model 在 `model_target_tools.py`，直接返回 JobResult/v1（材料、EOS、截面、沙漏和控制卡的引擎配方是 edit_keywords 的操作；run_recipe 是 A08 的配方入口）：输入文件不改，编辑结果写入作业目录，产物带 SHA256。编辑和目标里的选择可直接给 `core.contracts.Selector`，由 `domain/model/selectors.py` 解析为用户 ID（只支持参考构型）。运动副（P12）：`domain/model/joints.py` 新建九类 *CONSTRAINED_JOINT（create_entities 的 add_joint），`joint_checks.py` 检查刚体归属、节点对重合和过约束（check_model）。归属与集成约束以 tasks.yaml 为准。

raw-preserving 关键字引擎按关键字块解析，保留原始字节、来源与行号，构建 INCLUDE / INCLUDE_PATH / PARAMETER 树。仅结构化目标块，字段宽度来自 PyDYNA 定义；新卡片由 PyDYNA 生成。修改定位到原文件中的原块，未修改内容逐字节不变；保存用户输入的输出副本并保持 Include 结构。最后原生重开核对计数、引用和编辑差异。解析、参数作用域与字节往返可在 CI 完整测试。原生网格修改如何回写 Include 文件需另作最小实验。

## 后处理

数值通道使用 LASSO / LS-Reader，覆盖 binout 分支与 MPP 合并；渲染、原生派生量使用 LSPP。每类量在固定语料上交叉核对，结果始终标注后端、状态、单位、层与掩码。读取警告、缺量和删除标志缺失不能解释为真实零。

## 目标包结构与依赖

```text
core/        contracts, validation, errors, units, jobs, artifacts, native_log
engine/      batch, session, bridge, transport_win32, install, capabilities
native/      commands.py, versions, recipes/, embedded/ handlers
domain/      model, mesh, select, entity, check, results, curves, media
automation/  recording, sweeps, workflows
knowledge/   index, search
mcp/         thin tools, profiles
```

MCP/automation 调用 domain，domain 依赖 core/engine/native；下层不导入 service 或 MCP。I03 集中命令生成与版本差异，I04 收编原生验收脚本，import-linter 在 M1 强制依赖方向。迁移为别名后删除重复实现，不同时维护多套路由。

## 知识检索边界

I05 使用本地 SQLite/FTS 索引，支持代码标识符与中文词片段检索。源类别、版本、定位、行号和内容身份与文本一起保存，查询以参数绑定构造，不执行文档中的内容。公开命令表和仓库自有资料可随项目使用；外部 API/用户指南/课程资料默认私有，其索引与派生物只能在仓库外。私有命中需明确 include_private，参考记录始终带 reference_unverified 标记。

schema_version=2 用独立 keyword_fields 表保存字段粒度数据，来源为 Claude 的 keyword_docs；
I05 不再维护自己的 PyDYNA AST 解析。search_knowledge 通过 LSPP_KNOWLEDGE_INDEX 接入索引，
包内 provider 集成仍随 M3 完成，因此 I05 保持 partial。连接显式关闭，未完成索引只写
唯一临时文件，完整事务提交后原子发布；不会因旧半成品阻止重建。

## 版本、证据与发布

4.13 全量、4.10 子集、4.8 尽力，排除 4.11。L1 是逻辑测试，L2 是固定语料原生回归，L3 是 Agent 场景评测。每个里程碑按 tasks.yaml 退出标准开 PR，审查后由用户决定合并。保持 Private，M4 达标后由用户决定公开。设计决定见 [ADR 0000](decisions/0000-review-decisions-2026-10-05.md)。
