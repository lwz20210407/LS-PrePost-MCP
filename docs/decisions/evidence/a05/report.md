# A05 字符串参数回归（2026-10-07）

状态仍为 partial。此次补齐宏编译器和公开准备入口的字符串参数接线，
不把 cfile 展开执行算作原生 Macro/Exec 通过。

参数可为有限数值或最长 4096 字符的字符串；默认字符串使用双引号。
字符串只允许出现在命令参数位置：独立参数自动加引号，源文件引号内的
引用保留单层引号。拒绝引号、反斜杠、分号、控制字符、再次参数引用及
花括号；路径使用正斜杠。不求值表达式，不支持交互暂停，不默默删行。
拾取域仍限正整数用户 ID，不等同 Selector 结果或实体存在性验证。

`programs.py` 是实际宏接线位置；派发单所列 `program_bundle.py` 没有宏
专属分支。调度在 #83 确认只调整前者的宏参数校验与说明；其他语言仍
调用原 numeric_parameters。共享模型、结果实现与看板没有修改。

## 离线验证

新增首轮测试在 main e41cf655 的未修改实现上为 14 failed / 30 passed。
相关回归命令（缓存禁用、basetemp 指向本任务仓库外新目录）：

```text
python -m pytest tests/test_native_macro_parameters.py tests/test_native_macros.py tests/test_native_macro_parameters_native.py tests/test_native_macro_transport.py tests/test_program_bundle.py tests/test_programs.py tests/test_program_context.py tests/test_recipes.py -q -p no:cacheprovider --basetemp <fresh-task-output>
```

结果 137 passed / 2 skipped；跳过的两项需要显式原生 opt-in。
测试覆盖公开接口字符串可达、数字类型、两种引用和多宏默认值隔离、
原始行号、注入与类型拒绝、依赖声明和篡改、执行源身份校验。
本机复用现有 Python 3.11.15 环境并将 PYTHONPATH 指向本任务源码；
全量与最小依赖检查交由本 PR 的托管 CI，不并发重建本地环境。
本机缺少 import-linter，未修改共享环境，其门禁由托管 CI 执行。

## 验收边界

获准的一轮 headless 回归：4.13 与 4.10 各 1 passed，串行执行。
命令为 `python -m pytest tests/test_native_macro_parameters_native.py -q
-p no:cacheprovider --run-native --native-strict --native-executable <version-executable>
--native-fixture <original-fixture> --native-output <fresh-external-output>
--basetemp <fresh-external-basetemp>`。两版均读回 8 节点、3 单元，选中节点为
用户 ID 79；默认与覆盖后的空格文件名输出都包含 NODE/ELEMENT_SHELL/END，
未选宏的文件没有生成，源文件哈希不变，运行结束无遗留原生进程。

原生测试仅用本项目原创 M0 八节点 fixture，无私有教材输入。
本轮证据摘要见 [evidence.json](evidence.json)，原生日志、补丁及路径留在仓库外。
未安排 GUI/session、G03 Selector 绑定或五个教程宏的执行。
已读统一语料说明并只读检索公开 keyword 目录：未找到 `.mac`，现有一份
postprocess.cfile 不能充当五个教程宏。未读取或发布 local-book 内容/派生数据。
这些验收仍然开放，未改变 tasks.yaml 的 acceptance、owner 或 release。
