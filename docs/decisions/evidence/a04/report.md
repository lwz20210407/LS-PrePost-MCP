# A04 当前版本原生回归

DataCenter/LsPrePost、JSON 参数、多文件依赖、百万行 NPZ 与完整异常栈；4.10 使用规定子集。

| 版本 | 上下文 | 结果 | 实际 Git revision |
|---|---|---|---|
| 4.13 | batch | passed | `9e55e9b04920932d647de219a819b01355747f29` |
| 4.10 | batch | passed | `9e55e9b04920932d647de219a819b01355747f29` |
| 4.13 | session | passed | `9e55e9b04920932d647de219a819b01355747f29` |

各次执行工作树均干净；空 diff 的 SHA256、测试源码/输入语料/报告哈希见 [evidence.json](evidence.json)。
原始日志和模型只存仓库外。会话仅操作测试创建的进程，结束后已关闭；未执行 UU 断开验证。
本证据覆盖上述通道用例，不证明任意用户脚本的工程有效性或铰链/运动副建模已经实现。

## 第六轮：合并后 LF 批处理补验

历史 revision 9e55e9b 早于 main 3ce20a3。#18 将 program.scl、complete.scl、selection.scl
改为 write_scl 的 UTF-8/LF 写入；4.13/4.10 的批处理 LF 已有 I03 证据。
本轮在干净 d7deaa16c660ac6bcb7952ccbc04bb75e9270847 上补跑以下 batch 用例：

- 413 batch：passed，working_tree_dirty=false。
- 410 batch：passed，working_tree_dirty=false。

新记录追加到 evidence.json 的 runs，历史运行的结果与 revision 保留；旧报告路径补上原 run_id
以区别 batch/session，legacy_report 保留原值。源码指纹改为 Git blob 的 LF 规范化 SHA256，
每轮附 blob ID 与口径；原 CRLF checkout 哈希保存在 legacy_checkout_test_source_sha256。
A03 4.13 session 在 LF 写入下尚未补跑；A02/A03 4.8 batch 本轮已补跑通过。
