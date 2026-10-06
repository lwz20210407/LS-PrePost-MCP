# I01：日志编码和诊断识别

2026-10-06。基线将日志一律按 UTF-8 replacement 解码：UTF-8 BOM 会遮住首行错误，
UTF-16 BOM 错误未被识别，GBK 中文路径丢失。修复后 26 项编码/引擎测试通过，覆盖
UTF-8/16/32 BOM、系统 ANSI 回退、显式编码、会话增量、原始字节、错误配置和有损解码。
其中批处理诊断使用真实 Python 子进程输出合成编码字节；会话回执为离线夹具，未运行 GUI。

LS-PrePost 4.13 / 4.10 各 6 项实际后台回归通过。这证明现有五入口和负例未回归，
不宣称两版软件原生输出了所有测试编码。

实际 revision `2924649eb38b9f716dcd707a8db23b39a0fafb6a`，运行含未提交修改；
diff SHA256 `288f5805a97a088545694d3947c8a241c749c4611d430f9d5f8a87b4d849ea49`。
[证据 JSON](evidence.json) 保留基线、逐项测试、JUnit 和原生报告指纹。

规则依次为 BOM、显式参数/`LSPP_NATIVE_LOG_ENCODING`、严格 UTF-8、系统本地编码。
Windows 本地编码用 [locale.getencoding](https://docs.python.org/3/library/locale.html#locale.getencoding)，
避免 Python UTF-8 模式掩盖系统 ANSI 代码页。没有 BOM 的非 UTF-8日志若与系统编码不同，需显式指定。
这不是通用编码检测器，不能从任意字节唯一推断编码。

批处理保留 stdout.log.raw / stderr.log.raw，记录选用编码和 lossy 标志；
需要 replacement 时返回 failed，不继续领域验证。会话保留原始增量及编码元数据，
解码不可靠时返回 unverified，不重放。UTF-16/32 增量借用原文件 BOM，不把旧错误重复计入。
无损解码只是诊断读取前提，不替代产物和数值校验。I01 保持 partial，GUI/UU 状态不变。
