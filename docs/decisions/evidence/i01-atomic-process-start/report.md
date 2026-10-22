# I01：Windows 进程创建与 Job 归属原子化

2026-10-07。本次仅关闭创建进程与 Job 归属之间的宿主强杀窗口；I01 保持 partial/L1。
测试使用受控 Python 子进程，没有运行 LS-PrePost、可见 GUI 或 UU，也不扩大历史原生证据。
任务来源：[派发 PR #83](https://github.com/lwz20210407/LS-PrePost-MCP/pull/83)。

## 失败基线与修复

在 main `e41cf65551274c496f0bb1802f952d1a30e024b2` 的实现上，新回归在系统创建进程后、
Popen 返回前暂停宿主，再从外部终止该宿主。未绑定 Job 的暂停子进程仍存活，回归失败；
测试 finally 只回收其捕获身份的受控子进程。

修复以 STARTUPINFOEX 的 JOB_LIST 调用 CreateProcessW，由系统在创建时建立 Job 归属。
Job 保持匿名、不可继承和 kill-on-close；只允许标准 IO 句柄继承，Job 句柄不传给子进程。
Windows 10 / Server 2016 起支持此属性。属性配置或进程创建失败直接抛出错误，不降级为
先创建再绑定。系统限制或嵌套 Job 不兼容也按同一路径失败，不尝试脱离宿主 Job。

CPython 3.11/3.12 的普通 STARTUPINFO 属性字典不能传递 JOB_LIST，因此用私有 JobPopen
替换 Windows 创建步骤，继续使用 Popen 的流、communicate、wait 和 timeout 行为。
引擎只使用 shell=False、close_fds=True、无自定义 startupinfo；不支持的组合明确拒绝。
POSIX 仍使用独立进程组。没有修改配置、会话、服务层或结果计算共享实现。

## 验证范围

Windows Python 3.11 与 3.12 分别运行：

```text
python -m pytest tests/test_process_lifetime.py tests/test_native_log_encoding.py tests/test_engines.py -q -p no:cacheprovider --basetemp=<本次独立目录> --junitxml=<本次报告>
```

覆盖创建返回前强杀、正常退出、超时、KeyboardInterrupt、SystemExit、宿主退出后树回收、
无关进程保留、精确 Job 归属、无关可继承句柄隔离、中文/空格/引号参数、环境与 cwd、
stdin/stdout/stderr、日志解码，以及不存在的程序/cwd、无效 Job 和属性不支持的拒绝路径。
逐次结果、报告 SHA256、实际 revision/dirty 状态、diff 与源文件身份见 [evidence.json](evidence.json)。
3.11/3.12 全依赖环境和最小依赖环境的上述回归各 56 passed；3.11 全量 `python -m pytest -q`
得到 1732 passed、255 skipped。三项文件验收（engineering_unit、workflow_gate、
parameter_study_acceptance.file）3 passed；不涉及 LS-PrePost 进程。
Ruff、import-linter、任务/生成文档/迁移/语料登记/链接校验和 diff 检查均通过。
初次全量运行因 basetemp 在仓库内且路径过长而失败，移到仓库外短路径后全量通过；
保留初次失败计数，不修改这些无关模块。
原始 JUnit、日志与补丁仅保留在仓库外任务临时目录，避免发布本机路径。

系统依据：[Microsoft UpdateProcThreadAttribute](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)。
