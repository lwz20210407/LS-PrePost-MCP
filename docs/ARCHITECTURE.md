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

Command、cfile、SCL、应用内 Python、原生宏是五个一等通道，统一接口 `run_script(language, context=batch|session)`。宏支持 `*macro begin/end`、parameter、`&name`/`&{name}` 和 `(n/e/p)` 拾取域，拾取值由 Selector 绑定。现有 create_native_macro/run_native_macro 是 JSON 模板，将并入 A08 配方库并保留旧别名至 v0.6。执行通道不是不可信代码沙箱。

## 合同与领域操作

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

## 前处理

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

## 版本、证据与发布

4.13 全量、4.10 子集、4.8 尽力，排除 4.11。L1 是逻辑测试，L2 是固定语料原生回归，L3 是 Agent 场景评测。每个里程碑按 tasks.yaml 退出标准开 PR，审查后由用户决定合并。保持 Private，M4 达标后由用户决定公开。设计决定见 [ADR 0000](decisions/0000-review-decisions-2026-10-05.md)。
