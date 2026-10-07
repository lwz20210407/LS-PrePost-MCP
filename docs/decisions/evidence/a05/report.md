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

提交 `9e84e08` 的 45 个参数用例在 main `c5a43e8` 的两个宏实现文件上
实测为 **15 failed / 30 passed**（2026-10-08 复核）。这两个实现文件在
main 与 e41cf655 中相同。原先记录 14 failed / 30 passed 是未提交的
首轮 44 用例结果，不能代表最终测试文件，现已更正。
以下回归从 Git 读取准确的测试与实现 blob，在临时包中运行完整 45 例，
核对收集数、失败数、通过数与证据字段；不覆盖当前工作树源码：

```text
python -m pytest tests/test_native_macro_review.py -q -p no:cacheprovider -k p1_88a --basetemp <fresh-task-output>
```

该命令本身通过时，内部 main 基线须为 `15 failed, 30 passed`。
测试/实现的 revision、blob ID 和 LF SHA256 均见 evidence.json 的
local_tests.baseline。原 45 用例文件没有改写。
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

**历史运行，不认证本轮修正后的 PR 头。** 2026-10-07 获准的一轮
headless 回归：4.13 与 4.10 各 1 passed，串行执行；本轮没有重跑原生。
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

## P1-88b：原生磁盘字节与 Git 内容身份

原始证据中的 SHA256 是运行时磁盘字节哈希。复核时仍保留的两个文件
分别有 183 行/104 个 CRLF（native_macros.py）和 518 行/516 个 CRLF
（programs.py）；其余换行为 LF。因此既不是全 LF，也不是全 CRLF。
把 CRLF 规范化为 LF 后，文件内容与 `9e84e08` 的 Git blob **逐字节相等**，
未发现运行后修改实现逻辑的证据。不能只凭原始哈希不等推断代码改动。

| 文件 | 原始磁盘 SHA256 前缀 | Git LF SHA256 前缀 |
|---|---|---|
| native_macros.py | 8cfcc4138c9b | 6543cca93167 |
| programs.py | bca1e155f987 | 3c1474b352c9 |

evidence.json 的 native_source_provenance 保存完整 SHA256、Git blob ID、
行数及保留 LF 的行号。`test_p1_88b_historical_disk_bytes_are_reconstructible_from_committed_blobs`
从提交的 blob 重建混合换行字节，重新计算并逐项对照两次原生记录，
同时验证规范化后没有内容差异。原始 source_files 哈希不被覆盖。
这补全了历史运行的可追溯性；合并最新 main 后没有新的原生执行，
所以两个 native 条目均显式标为 historical_only / certifies_current_head=false。

## P2-88c–f：明确的编译层边界

- **88c：输出路径不是沙箱。** `save keyword &file` 的普通字符串参数可为
  相对上级路径、绝对路径或 UNC 路径，与用户直接写入 cfile 字面量的权限相同。
  输出路径不受参数约束，以审阅后的渲染源码和执行 SHA256 为准。
  openc/runscript 等脚本加载仍受依赖登记和 relative_name 约束。测试只准备
  程序，不访问合成 UNC 地址、不启动原生、不创建目标输出。
- **88d：引号检查是一项兼容性变化。** 非注释命令行的双引号个数为奇数时，
  即便没有字符串引用或只含数值引用，也会在准备阶段带行号拒绝。
  例如 `title "unterminated` 在 main 原实现被接受，本 PR 显式报错。
  本轮保留此行为并加回归，不再把它表述为纯数值宏行为完全不变。
- **88e：中文、4096 字符边界及引号内的 `$` / `#` 仅做编译层验证。**
  原生仅用 ASCII 空格文件名；这些值的原生分词/路径行为仍未核实，
  不能由编译成功推导原生可用，亦不绕过 KI-049 和已知非 ASCII 路径问题。
  补测 U+2029、Cf 字符和孤立代理项均在创建作业前拒绝。
- **88f：bound.mac 与 cfile 不保证原生等价。** bound.mac 保留 `&name`
  引用，原生 Macro/Exec 替换字符串时是否加引号尚未核实；cfile 已在
  编译时把独立字符串参数加引号。不能把两者的输出形式或 Python
  再编译一致当成原生执行等价的证据。

上述边界回归集中在 tests/test_native_macro_review.py。
新增 17 例在 main 实现与修正前证据组合上为 12 failed / 5 passed；
在修正前 PR 实现与证据上为 2 failed / 15 passed（两项 P1 证据缺陷）。
修正后新增 17 例全部通过；将本文件加入上面的 8 个相关测试文件后，
实测 154 passed / 2 skipped / 2 warnings。两条 warning 是安装配方来源
未配置提示。测试进程设 OPENBLAS_NUM_THREADS=1、OMP_NUM_THREADS=1；
此前本机曾因线程内存不足和 WinError 1450/1455 中断，失败尝试未计通过。
