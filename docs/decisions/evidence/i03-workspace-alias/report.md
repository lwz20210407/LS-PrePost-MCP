# I03：中文作业目录的显式 ASCII 执行别名

在干净提交 `20735b6fed46e9295cc806dc59e47fc0a48eafab` 上，4.10 和 4.13 各 **7 passed / 1 skipped**。两次工作树均无修改，diff SHA256 为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；实际命令、报告哈希、Git blob/LF 源码身份和逐例状态见 [evidence.json](evidence.json)。原始报告和日志留在仓库外。

覆盖 ASCII、空格、中文目录的 cfile 执行、PNG、keyword 保存与原生重开，以及中文目录中的 Service 内置 Python、SCL 结果清点、原生字段提取、programs 四个入口。源模型与配置哈希保持，产物位于原作业目录；每次执行结束，独占临时联接已经清理。单元回归另外验证异常退出和联接被替换时保留原文件。

设置 `LSPP_NATIVE_ALIAS_ROOT` 才启用：它须指向已存在的本地 ASCII 目录。原生进程通过指向同一作业的 NTFS 联接读取私有配置和命令文件，没有另复制模型。仅无图形 BatchEngine 使用此路线；图形进程和 SessionEngine 保留原路径。

完整 native_postprocess_case 含图形回调。此前扩大测试曾在该回调失败；本提交保留其原图形路径并在没有授权窗口时明确跳过，不能算该完整流程通过。4.8、原生宏、远程和未启用别名的中文路径仍保留 gap。I03 状态不变。
