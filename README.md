# LS-PrePost-MCP

让支持 MCP 的 AI Agent 通过自然语言操作 LS-PrePost，完成 LS-DYNA 模型检查、有限范围的编辑、结果提取和出图，并返回可核查的产物与日志。

**当前为 Private 开发仓库，版本 v0.4；v0.5 尚未完成。** 主要原生证据来自 Windows LS-PrePost 4.13.4；4.10/4.8 的已验证子集见 [兼容性](docs/COMPATIBILITY.md)。

## 能做什么

现有入口可处理独立 keyword 模型、集合和部分载荷、网格编辑、节点/实体结果、曲线及图像。带 Include 的保真编辑、接触定义、RCFORC/SECFORC 完整流程仍是缺口。下表按完整任务验收记录状态；“部分实现”应先核对 [任务目录](docs/TASKS.md) 中的限制。

<!-- tasks:begin -->
| 类别 | 任务 | 当前状态 | 目标版本 |
|---|---|---|---|
| 前处理 | P01 模型检视 | 部分实现 | v0.5 |
| 前处理 | P02 关键字卡片读改增删（Include 保真） | 待实现 | v0.5 |
| 前处理 | P03 材料 / 截面 / Part 创建与关联 | 部分实现 | v0.5 |
| 前处理 | P04 集合创建 | 部分实现 | v0.5 |
| 前处理 | P05 边界条件与载荷 | 部分实现 | v0.5 |
| 前处理 | P06 接触定义与初始穿透检查 | 待实现 | v0.5 |
| 前处理 | P07 规则网格生成 | 部分实现 | v0.6 |
| 前处理 | P08 网格编辑 | 部分实现 | v0.5 |
| 前处理 | P09 模型检查 | 部分实现 | v0.5 |
| 前处理 | P10 控制与输出卡 | 待实现 | v0.5 |
| 前处理 | P11 保存并原生重开验证 | 部分实现 | v0.5 |
| 后处理 | Q01 结果概览 | 部分实现 | v0.5 |
| 后处理 | Q02 云图出图 | 部分实现 | v0.5 |
| 后处理 | Q03 场数据提取 | 部分实现 | v0.5 |
| 后处理 | Q04 工程量与失效掩码 | 部分实现 | v0.5 |
| 后处理 | Q05 时程曲线（History） | 部分实现 | v0.5 |
| 后处理 | Q06 binout / ASCII 全库曲线 | 部分实现 | v0.5 |
| 后处理 | Q07 曲线运算 | 部分实现 | v0.5 |
| 后处理 | Q08 XYPlot 出图 | 部分实现 | v0.5 |
| 后处理 | Q09 动画导出 | 部分实现 | v0.5 |
| 后处理 | Q10 截面力与剖切面 | 待实现 | v0.6 |
| 后处理 | Q11 测量 | 部分实现 | v0.6 |
| 后处理 | Q12 能量检查 | 部分实现 | v0.5 |
| 自动化 | A01 命令栏 Command（单条原生命令） | 部分实现 | v0.5 |
| 自动化 | A02 cfile 命令流 | 部分实现 | v0.5 |
| 自动化 | A03 SCL 脚本 | 部分实现 | v0.5 |
| 自动化 | A04 应用内 Python 脚本 | 部分实现 | v0.5 |
| 自动化 | A05 原生宏执行 | 部分实现 | v0.5 |
| 自动化 | A06 宏安装与快捷键管理 | 待实现 | v0.6 |
| 自动化 | A07 命令录制转配方 | 部分实现 | v0.5 |
| 自动化 | A08 配方库 | 部分实现 | v0.5 |
| 自动化 | A09 参数化批量 | 部分实现 | v0.5 |
| 自动化 | A10 知识检索 | 部分实现 | v0.5 |
| 通用 | G01 视图控制 | 部分实现 | v0.5 |
| 通用 | G02 显示控制 | 部分实现 | v0.6 |
| 通用 | G03 统一选择器 | 部分实现 | v0.5 |
| 通用 | G04 实体识别 Identify | 部分实现 | v0.5 |
<!-- tasks:end -->

## 工作原理

自然语言 → AI Agent → MCP → 原生命令、cfile、SCL、应用内 Python 或读取器 → LS-PrePost 模型与结果。

工具提供执行、观察、验证、知识检索和工程计算。每次作业保留输入身份、命令、日志和产物检查；数值结果标明实际后端。v0.5 将统一为批处理默认、常驻会话可选的执行引擎，当前仍使用各工具既有的执行方式。

## 快速开始

需要仓库访问权限、Python 3.11+、uv，以及合法安装的 LS-PrePost。Windows 4.13 是当前主要验收环境。

```shell
git clone https://github.com/lwz20210407/LS-PrePost-MCP.git
cd LS-PrePost-MCP
uv sync --extra results --extra pydyna
```

配置安装、输入和产物目录：

```powershell
$env:LSPP_EXECUTABLE = 'C:\path\to\lsprepost.exe'
$env:LSPP_WORKSPACE = 'D:\lspp-jobs'
$env:LSPP_ALLOWED_ROOTS = 'D:\models;D:\results'
uv run lspp probe_environment
```

在 Agent 中添加 stdio MCP 服务 `uv --directory C:/path/LS-PrePost-MCP run ls-prepost-mcp`，传入上述环境变量；安装配套 [Skill](skills/ls-prepost/SKILL.md)。完整配置、多版本与精简工具模式见 [安装指南](docs/INSTALL.md)。

## 示例

- “建立 10×10 mm 的板，划分为 5×5 壳单元，单位 mm-ms-g，保存并重开核对。”
- “列出这个模型前一百个节点，保留真实节点 ID 和原始坐标。”
- “用 LASSO 提取指定节点在第 1、2 状态的位移，保留模型单位，并注明读取后端。”
- “查找 Shell Drag 的官方命令和前置条件。”

可复用输入示例见 [examples](examples/)。执行前应确认模型类型、单位、实体、状态以及工具已验证范围。返回 `failed` 时查看作业日志和检查结果。

## 文档

- [任务与验收](docs/TASKS.md) · [当前工具与参数](docs/TOOLS.md)
- [安装](docs/INSTALL.md) · [兼容性](docs/COMPATIBILITY.md) · [已知问题](docs/KNOWN_ISSUES.md)
- [架构](docs/ARCHITECTURE.md) · [路线图](docs/ROADMAP.md) · [开发指南](docs/DEVELOPMENT.md)
- [变更记录](CHANGELOG.md) · [待评估需求](backlog.md)

## 测试

```shell
uv run pytest
uv run --extra dev --extra results --extra pydyna pytest
```

第一条在未装可选后端时跳过相关测试；第二条覆盖这些后端。以上为逻辑测试，原生验证需要 LS-PrePost 安装与专门语料。

## 使用边界与许可

脚本通道会执行指定代码，**不是沙箱**；应用层文件范围检查不隔离任意 Python/SCL 的副作用。单位和工程阈值由调用者声明。项目不包含求解器提交，不分发厂商软件、手册和私有模型。

项目代码采用 MIT；第三方命令目录及其条款见 [NOTICE](NOTICE.md)。LS-PrePost / LS-DYNA 及相关文档权利归各自所有者。
