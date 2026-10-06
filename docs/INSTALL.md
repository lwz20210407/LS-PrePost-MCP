# 安装与配置

仓库当前为 Private，需要仓库访问权限。

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

Windows 的无图形批处理如需使用中文工作目录，可显式设置 `LSPP_NATIVE_ALIAS_ROOT`，指向一个已经存在、完整路径仅含 ASCII 字符的本地目录。该目录还须位于作业目录之外，且必须位于支持目录联接的本地 NTFS 卷；不要使用网络盘或 UNC 根目录。每个进程创建独占临时别名，指向原作业目录；产物仍写在 `LSPP_WORKSPACE`，不会另复制模型。进程结束后只清理本次别名，别名身份改变时拒绝清理。配置、日志和实际执行路径会记入作业证据。

服务被强杀后，别名根目录可能残留 `lspp-*` 目录联接。直接删除联接项只会删除别名，不会删除它指向的作业目录；本机已验证 PowerShell 5.1 `Remove-Item -Recurse`、`cmd rd /s` 和 Python `shutil.rmtree` 的这一行为。清理前先核实它确实是目录联接及其目标，保留仍被运行中作业使用的别名。

该选项只作用于无图形 BatchEngine；可见图形进程与 SessionEngine 保持原路径。未设置时保持原行为，中文路径限制见 [KI-049](KNOWN_ISSUES.md#ki-049-含空格中文工作目录的原生配置解析)。4.8、原生宏、远程及图形流程仍需各自的原生证据。

可选多版本配置：

```powershell
$env:LSPP_EXECUTABLES = '{"4.8":"C:/path/4.8/lsprepost.exe","4.10":"C:/path/4.10/lsprepost.exe","4.13":"C:/path/4.13/lsprepost.exe"}'
```

MCP 客户端使用本项目虚拟环境里的 `ls-prepost-mcp` 可执行入口，或以该环境的 Python 启动 `-m ls_prepost_mcp.server`，并传入上述环境变量。服务使用 stdio；不要将调试打印写到协议 stdout。


## MCP 客户端

通用 stdio 配置：

```json
{"mcpServers":{"ls-prepost":{"command":"uv","args":["--directory","C:/path/LS-PrePost-MCP","run","ls-prepost-mcp"],"env":{"LSPP_EXECUTABLE":"C:/path/lsprepost4.13.exe","LSPP_WORKSPACE":"D:/lspp-jobs","LSPP_ALLOWED_ROOTS":"D:/models;D:/results"}}}}
```

将仓库 skills/ls-prepost 复制到 Agent 的技能目录。客户端具体配置入口按其版本文档操作。

`LSPP_TOOL_PROFILE=full` 暴露当前完整工具集；`compact` 暴露 lspp_find_operations / lspp_describe_operation / lspp_run_operation 三个入口。精简模式按需查询参数，实际操作与 full 共用实现。

可选后端：results 安装 LASSO；pydyna 安装 PyDYNA。LS-Reader 使用 LSPP_LSREADER_PYTHON 指定匹配 ABI 的独立解释器。DPF 是未完成原生数据验收的可选适配，不作为默认路径。

安装后运行 `uv run lspp probe_environment` 和 `uv run lspp capabilities`。应用内 Python 必须与具体 LSPP 构建匹配；探测不会修改安装、UAC 或全局配置。
