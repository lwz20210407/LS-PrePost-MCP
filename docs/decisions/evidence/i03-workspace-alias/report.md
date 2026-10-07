# I03：中文作业目录的显式 ASCII 执行别名

在干净提交 `20735b6fed46e9295cc806dc59e47fc0a48eafab` 上，4.10 和 4.13 各 **7 passed / 1 skipped**。两次工作树均无修改，diff SHA256 为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；实际命令、报告哈希、Git blob/LF 源码身份和逐例状态见 [evidence.json](evidence.json)。原始报告和日志留在仓库外。

覆盖 ASCII、空格、中文目录的 cfile 执行、PNG、keyword 保存与原生重开，以及中文目录中的 Service 内置 Python、SCL 结果清点、原生字段提取、programs 四个入口。源模型与配置哈希保持，产物位于原作业目录；每次执行结束，独占临时联接已经清理。单元回归另外验证异常退出和联接被替换时保留原文件。

设置 `LSPP_NATIVE_ALIAS_ROOT` 才启用：它须指向已存在的本地 ASCII 目录。原生进程通过指向同一作业的 NTFS 联接读取私有配置和命令文件，没有另复制模型。仅无图形 BatchEngine 使用此路线；图形进程和 SessionEngine 保留原路径。

完整 native_postprocess_case 含图形回调。此前扩大测试曾在该回调失败；本提交保留其原图形路径并在没有授权窗口时明确跳过，不能算该完整流程通过。4.8、原生宏、远程和未启用别名的中文路径仍保留 gap。I03 状态不变。

## 第九轮复验

合入 main `9a1c07c` 的干净合并提交 `e4676a9fdca5f8551aad51e7b20d0a2e180f95d3` 已包含 #38 的原始日志/解码和 #39 的版本资源识别。4.10、4.13 各 **7 passed / 1 skipped**；两条新 run 已追加，原 `20735b6` 的记录保留。每个版本检查 10 个原生作业的 log_decoding、stdout.log.raw、stderr.log.raw；其中 6 个中文目录作业均有 workspace_alias 且 cwd 为 ASCII。图形回调依旧跳过。

另外保留四次 dirty 探索运行的报告哈希、次数和原因：4.10 首轮 3 passed / 5 failed（fixture 路径）；第二轮 7 passed / 1 failed（图形回调）；4.13 为 7 passed / 1 skipped；4.10 产品入口探针 3 passed。它们不替代上述干净运行，逐项见 evidence.json 的 historical_dirty_runs。

随后单独修复 CreateJunction 失败留下的空目录：只移除本次独占目录内的空普通目录，遇重解析点或非空替换项保留。ce24 的 UNC 情形 I 复验后别名根目录为空，A–H、J 的保护行为不变；新增三个模拟失败用例由修复前失败转为通过。此异常清理修复不改成功作业路线，新增原生记录绑定的是前述纯合并提交。


## 2026-10-07：4.13 恢复权限后的无图形复跑

在干净 main `0d7a6d718647fac50e487af101eb18fe58571037` 上运行 `tests/test_native_workspace_alias_native.py`，结果为 **7 passed / 1 skipped**，未再出现 WinError 740。实际执行包含此前 #38/#39 和 #70；空 diff 指纹与源码快照记录在 evidence.json 的 `ci-restored-413-batch`，旧记录原样保留。

10 个原生进程作业均保留 stdout/stderr 原始日志和 log_decoding；6 个中文目录作业均使用 ASCII cwd 别名。逐项核对报告哈希、源码快照、Git blob、状态与日志字段，0 项不一致。原始报告仍在仓库外，未公开安装路径或原生日志。

跳过的 native_batch 需要图形回调；本轮没有可见 GUI、UU 断开或其它版本运行。用户已移除可执行文件的管理员兼容性标记，此记录验证当前 4.13 无图形路径，未改变任务验收或扩大已验证范围。
