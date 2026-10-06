# A05：原生宏触发实验，验收尚未完成

2026-10-05，归属 A05。保留原验收标准，状态仍为 partial。

4.13.4 最小实验：内置 LsPrePost/DataCenter 模块没有名称包含 macro 的
公开对象。m= 加载含原生 *macro begin/end 的合成文件后，正常退出但未
产生仅由宏体生成的文件。macro、macro1、macrocfile 的候选命令被原生拒绝；
winmacro exec 与 openc macro 也没有执行回执。这些结果只排除已测路径。

`tests/test_native_macro_transport.py` 把“m= 加载成功不代表宏已运行”固化为
原生负向回归。BatchJob 仅新增 job 内宏文件的 m= 加载选项，结果仍 unverified，
不新增或宣传已验证的宏运行工具。旧 JSON 模板和展开成 cfile 的工具不会
计入 A05 原生宏通过证据。

M0 已验证 Macro 面板选择 + Exec，可见 GUI 后续用例合入同一外部待测清单。
课程归档中已定位两个 .mac 及四个 toolbar macro cfile；其原文、模型和派生
数据保持私有。真实宏的两个上下文、字符串参数和五个样例仍待完成。
等待 GUI 取证期间继续 A08/A10；不修改 A05 范围或验收。

2026-10-06 补充：宏准备阶段对不支持的语法给出原始文件行号，包含多宏块、
注释行、表达式默认值、interactive、重复默认值、分号多命令、无效拾取后缀
和缺失参数；不删除源行或把错误块当作部分成功。该修复由
[宏源文件回归](../../tests/test_native_macros.py) 验证，不扩展上述原生执行声明。

宏探针准备修复：结果模型在启动 cfile 中打开，完成输入回读后再触发
Macro/Exec；不再由 MP4 探针在宏执行回调中嵌套打开 d3plot。非 MP4
用例可显式指定 keyword 或 d3plot，证据记录实际输入类型；其它类型
在写文件、启动进程前拒绝。离线回归见
[宏探针回归](../../tests/test_macro_probe.py)。本次提交没有重新运行 GUI，
也没有补齐 batch 原生宏执行或完整的 A05 语义对照验收。

第三轮补修：BatchJob 的 m= 宏文件路径先经 quoted_path 校验，拒绝引号、
分号和控制字符；传给 subprocess 的 argv 保持原始路径，由操作系统
参数序列化处理空格，不把命令栏用的字面引号混入 m= 参数值。
