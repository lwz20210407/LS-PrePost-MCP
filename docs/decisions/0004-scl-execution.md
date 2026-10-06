# A03：SCL 数组与编译诊断

2026-10-05，归属 A03。`run_script(language="scl")` 共用已验证的批处理/
会话执行器，原样执行 SCL，不套用 cfile 的参数替换语法。

第三轮审阅后 A03 改为 partial：以下历史原生记录缺少实际 Git revision
和运行时未提交 diff SHA256，不能作为当前提交的完成证据。需重新取证，
并将去路径的 report.md、evidence.json 入库；不补造历史运行身份。
会话使用原生 Windows 路径调用 runscript；不创建另一个后台进程。
编译失败返回 LSPP 错误原文及其声明的源行号，缺失行号的附加错误保留为空。

`tests/test_script_scl_native.py` 实测读取八个非连续用户 ID 及 XYZ 数组，
分配并写入新的合计数组，然后输出 CSV。独立核对固定合成模型的全部值；
4.13 同时运行等价 DataCenter Python 程序并逐行交叉检查。
第 4 行故意放置编译错误，要求 JobResult failed 且诊断包含 line=4。

- 4.13.4：batch 和 queue session 正反例均通过。
- 4.10、4.8：batch 正反例均通过。
- 以上不改变旧版内置 Python 向量 ABI 的既有使用限制。
- I02 合同字段不变；本机日志和私有安装路径保留在外部原生证据目录。
