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
