# LS-PrePost-MCP

面向自然语言的 LS-PrePost 前后处理自动化：MCP 工具、原生命令/SCL/Python 接口、结果读取与可追溯工作流。

**状态：早期开发版。目标版本为 4.8、4.10、4.13。目标覆盖常用功能，不代表当前已覆盖。**

产品与工程主线见 [顶层设计](docs/ARCHITECTURE.md)：以 **常用网格编辑与检查、明确语义的工程后处理、录制与参数化复用** 三条完整流程作为版本验收目标。统一语义/执行/质量合同后按依赖扩展模块，当前设计不代表已完成架构迁移。[资料转化状态](docs/SOURCE_ADOPTION.md)与[待开发清单](docs/BACKLOG_REVIEW_2026-10-01.md)分别说明输入依据和缺口。

首批架构落地：[统一工作流结果与质量门槛](docs/WORKFLOW_GATES.md)。已加入检查不合格时停止后续步骤、参数化阈值和失败证据，并提供可复用配方及文件后端合成验收。

当前按[交付批次](docs/DELIVERY_PLAN.md)优先推进前处理、后处理和自动参数化。[工作流框架](docs/WORKFLOW_FRAMEWORK.md)已统一操作路由和整条流程预检，支持 1–20 组显式参数独立执行及结果汇总；合成网格变换→原生质量→保存重开已在可见 4.13.4 验证。[原生输出](docs/NATIVE_MEDIA.md)现包含带标签单曲线 PNG、数值读回及从 state1 连续导出的 MP4，均已接入录制参数回放。多曲线/完整云图及任意范围/格式动画仍需补齐，现有子集不代表全部完成。

本项目独立实现任务与执行核心，吸收公开项目、官方文档和本地案例的接口经验；可复用数据与依赖按各自许可证接入。来源、已实现能力、实机验证和待开发功能分别登记，详见 [来源与复用](docs/SOURCES.md)、[兼容性](docs/COMPATIBILITY.md)、[开发路线](docs/ROADMAP.md)。

**资料尚未全部转化为可执行功能。** 按实际工作任务列出的实现与缺口见[覆盖矩阵](docs/COVERAGE.md)，不以命令目录或工具数量代替覆盖程度。

按前处理、后处理、参数化、命令/Python/宏、顶部菜单、右侧与底部工具栏逐项展开的现状见 [v0.2.0 界面与能力缺口审计](docs/FEATURE_GAP_AUDIT_v0.2.0.md)。

**v0.3.0 增量**：41 个安装过滤器与 7 个模板的接入，持久 GUI/检查点/托管录制和参数回放，网格变换/重复节点合并/质量检查，以及原生曲线到工程曲线和能量筛查。各项实机范围、后端区别和未完成项见 [v0.3 工作流与验证](docs/WORKFLOWS_v0.3.md)。

全部用户要求的持续开发清单见 [需求总清单与优先级](docs/REQUESTS_AND_PRIORITIES.md)。仓库现已提供 [原始 command / cfile / SCL / Python / 参数宏](docs/NATIVE_PROGRAMS.md) 的正式执行工具，逐通道记录实机范围；原始脚本入口不等于所有软件功能都已完成工程封装。

最新进展：[同一可见 GUI 的网格编辑工作流](docs/GUI_WORKFLOWS.md)，包括原生合并、法向、原位变换、新增节点/单元与质量读回；[图文/代码/视频转化记录](docs/TUTORIAL_INTEGRATION.md)标注实际阅读、观看与复现进度。

**2026-10-01 进展**：[结果合同与可见后处理流程](docs/RESULT_CONTRACTS.md)现包含 keyword/d3plot 选择、部件显隐保留、原生节点历史到相对位移三步模板及原时刻恢复。自动质量门槛、原生壳质量、Keyword Check、缓存、重编号和录制回放已有明确范围的验证。[待开发清单](docs/BACKLOG_REVIEW_2026-10-01.md)仍保留大模型、失效/层/历史语义、更多网格编辑、曲线窗口和菜单覆盖等缺口。

## 已实现的能力

规模边界按工具区分：[大模型支持说明](docs/MODEL_SCALE.md)。20,000 是旧整模快照工具的实现限制，不是 LS-PrePost 软件上限。分页网格读取与命名字段云图已有超过30万单元的私有原生验收；大模型编辑仍在开发。

- 标准 MCP stdio 服务及同源 CLI。
- 每任务独立目录、命令文件、输入身份、结构化结果、超时处理和日志。
- 应用内 Python 探测、模型计数、节点/部件查询、单元连通性。
- 原生壳板网格创建、保存副本、重新读取、PNG 导出。
- 原生六面体方块网格、单个平面壳部件拉伸、选定节点平移、单元转移部件，核对数量/坐标/归属并输出 k 文件。
- 原生 SCL 探测，不依赖应用内 Python。
- 节点向量和时程接口；4.13已作读取器对照，4.10旧ABI的原生向量路径主动拒绝，见矩阵。
- 可选 LASSO d3plot/binout 数值读取后端，明确返回 `backend=lasso`。
- LS-Reader独立进程适配、PyDYNA Deck清单与弹性材料创建/修改/重读核对，见[后端合同](docs/BACKENDS.md)。
- 原生 SCL 应力/应变/节点字段、六分量应力与原生 Mises 一致性检查、三轴度和明确定义的 Lode 参数。
- 原生 ASCII/XYPlot 曲线、原生 SCLBinout 曲线，以及逐组后处理验收、全时程极值和实体 ID、结果图。详见[后处理合同](docs/POSTPROCESSING.md)。
- 可选读取器的显式场分量/历史槽位导出、binout 多变量表、数值 ASCII 曲线、非均匀时间微分与积分。
- [显式单位转换](docs/UNIT_CONTRACTS.md)、不同输入时间/数值单位统一后对齐，以及力/相对位移到工程应力应变和功的可复用配方；单位制不自动猜测。
- 按坐标范围创建节点集合、限定范围的模型引用检查，以及原生网格配合 PyDYNA 的位移加载壳板生成与原生重开检查。
- PyDYNA 实际关键字类/字段检索、结构化 Deck 组合、唯一匹配的标量卡与表格行编辑，拒绝未知字段并重读核验。六个文档板块的解析及迁移边界见[PyDYNA 集成](docs/PYDYNA_INTEGRATION.md)。
- 多安装版本配置和按版本调用，避免全局切换实例。
- 持久 Windows GUI 会话、显示/部件可见性、模型检查点及恢复、迟到响应协调。协议 3 已在同一可见 GUI 原位平移/旋转；旧协议保留检查点作业后重开路径。
- 4.13.4 可见 GUI 的选择/布尔/原生缓存、全体/局部壳法向、节点/壳/部件重编号、原生壳质量 13 项可选指标及 Keyword Check 报告；均明确限定范围并保留失败案例。
- 安装模板参数表达式安全求值、模板实例化、关键字过滤器应用；网格质量、合并与文件变换走明确标注的 PyDYNA/几何后端。
- 托管操作录制、显式参数绑定、顺序工作流；原生命令录制的受限编译，未知命令阻止回放。
- 原生 ASCII 提取后构建相对位移、力—位移、工程应力—应变；原生 SCLBinout 能量提取及筛查。
- 命令目录、官方教程验收案例、来源索引和配套 [Skill](skills/ls-prepost/SKILL.md)。

![Native LS-PrePost shell plate](docs/images/native-shell-plate.png)

上图来自初始实机测试生成的 5×5 壳网格。未使用真实工程模型作为公开演示。

## 安装

外部 MCP 环境使用 Python 3.11+。LS-PrePost 自身的嵌入式解释器独立管理，不能把外部环境直接强塞进去。

```shell
git clone https://github.com/lwz20210407/LS-PrePost-MCP.git
cd LS-PrePost-MCP
uv sync --extra dev --extra results --extra pydyna
```

不使用 uv 时：

```shell
python -m venv .venv
python -m pip install -e ".[dev,results,pydyna]"
```

上述 pip 命令应在已激活的 `.venv` 中执行，或使用该环境的 Python 绝对路径。

## 本机配置

设置以下环境变量。示例路径需替换为自己的安装和任务目录：

```powershell
$env:LSPP_EXECUTABLE = 'C:\path\to\lsprepost.exe'
$env:LSPP_WORKSPACE = 'C:\path\to\lspp-jobs'
$env:LSPP_ALLOWED_ROOTS = 'C:\path\to\models;C:\path\to\results'
$env:LSPP_TIMEOUT = '120'
```

`LSPP_WORKSPACE` 是唯一产物入口；已有输入文件不会被覆盖。输入可以位于该目录或允许的根目录。Linux 的根目录列表使用 `:` 分隔。

可选多版本配置：

```powershell
$env:LSPP_EXECUTABLES = '{"4.8":"C:/path/4.8/lsprepost.exe","4.10":"C:/path/4.10/lsprepost.exe","4.13":"C:/path/4.13/lsprepost.exe"}'
```

MCP 客户端使用本项目虚拟环境里的 `ls-prepost-mcp` 可执行入口，或以该环境的 Python 启动 `-m ls_prepost_mcp.server`，并传入上述环境变量。服务使用 stdio；不要将调试打印写到协议 stdout。

## CLI 与自然语言示例

```shell
uv run lspp capabilities
uv run lspp probe_environment
uv run lspp create_shell_plate --json '{"nx":5,"ny":5,"size":[10,10],"units":"mm-ms-g"}'
```

JSON 的引号规则随 shell 而异；也可以通过 MCP 直接传结构化参数。

可让代理执行：

- “用指定版本建立 10×10 的板，划分成 5×5 壳单元，保存后重开检查，再导出等轴测图。”
- “列出这个模型前一百个节点，保留真实节点ID和原始坐标。”
- “用 LS-PrePost 原生接口提取指定实体单元的六分量应力，检查 Mises，再输出三轴度及两种 Lode 参数，并说明积分点和参数定义。”
- “用原生 ASCII 功能读取 NODOUT 的指定节点 Z 位移；保留单位、时间、命令和验证记录。”
- “用 LASSO 提取指定节点在第1、2状态的位移向量，单位保持模型原单位。”
- “检索 Shell Drag 的官方步骤和验收条件，区分文档支持与已自动化功能。”

每次原生调用返回 job ID、状态、日志和产物；`failed` 不应被代理总结为成功。CLI 在任务失败时返回非零退出码。`search_commands` 的命中只代表参考资料，不能直接当成已验证可执行命令。

## 测试

```shell
uv run pytest
```

CI 测试不启动商业软件。实机冒烟需要合法安装，并在用户指定目录内运行生成案例或授权样例。结果见 [兼容性记录](docs/COMPATIBILITY.md)。

## 已知边界

- 目前没有任意 Python/shell 执行工具，也没有接管既有 GUI 会话。
- 文件范围检查属于应用层边界，不是操作系统沙箱。
- 暂仅支持普通 `*INCLUDE`；复杂 include path/参数变换规则会明确拒绝。
- 原生保存和材料修改暂要求无include的独立deck；MPP binout多分片会明确拒绝，避免只读一片返回不完整结果。
- 原生渲染依赖图形环境，`-nographics` 不等于真正无图形；未把 `runc=` 推广到旧版本。
- 输入单位由调用者声明，不进行隐式推断或材料参数补全。
- 当前没有求解器启动工具。参数化位移加载壳板只是限定的分析设置；复杂网格、更多材料/边界/接触、碎片等仍在建设。

本项目代码使用 MIT。命令目录来自 Apache-2.0 项目，独立条款见 [NOTICE](NOTICE.md)。LS-PrePost/LS-DYNA、官方手册及其他第三方组件保留各自权利；本仓库不分发厂商软件、手册全文或私有模型。
