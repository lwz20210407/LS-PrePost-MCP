# I03：SCL 路径字面量与公开 Binout 对照

第五轮遗留的 JSON Unicode 转义已集中为 native.commands.scl_string（ensure_ascii=False）。
原生 API 的路径语法有所不同：SCLBinoutOpen 保留 native 反斜杠，输出文件使用正斜杠。
首轮统一正斜杠复现 KI-017，ASCII 对照失败；保留反斜杠后 4.13.4 对照通过。
公开语料 binout_forces 的 MAT_SUM 内能 101 个时间点与 LASSO 交叉核对，输入 SHA256 不变。

中文 job 目录仍因 KI-049 无法定位 binout.scl，严格 xfail；未把它登记为通过。
实际运行 revision 均为 d7deaa16c660ac6bcb7952ccbc04bb75e9270847，工作树有修改。
[证据](evidence.json)包含每轮 diff SHA256、完整 diff 命令、源码指纹和未跟踪测试清单。
补丁包含当时全部已跟踪修改，不含未跟踪的新测试；原始 patch 与报告在外部运行目录保留。
第二轮 1 passed / 1 xfailed；首轮 1 failed / 1 xfailed 的记录保留。
本轮不涉及 GUI、求解器或 Claude 负责的 domain/model、domain/results 实现。
