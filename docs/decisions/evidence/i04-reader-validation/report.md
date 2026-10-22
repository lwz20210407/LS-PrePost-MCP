# I04：异常 d3plot 时间轴准入（2026-10-18）

公开例 `extra-result-03` 曾被 LASSO 2.0.4 计为 11 状态，第 3 个时间是
结束标记 `-999999`。原生历史记录为 2 状态，详见
[原始诊断](../i04-diagnostics/report.md)。本次修复是共享读取准入，不是新的二进制解析器。

## 行为

- 共享校验应用于完整数组读取、旧清点入口、节点 CSV 导出和 state_filter 的完整元数据预检。
- 拒绝 EOF 标记充当时间、非有限时间、非一维时间轴，以及有歧义的时间倒退。
- 合法负起始时间、重复时间和几何清点的空时间数组原样保留。
- 报错给出 1-based 异常状态；不截断、不排序、不删状态，不输出异常节点 CSV。
- 即使请求的是第 1 状态，也先检查整个时间轴，避免 state_filter 掩盖后面的异常。

## 验证

新用例在父版本 `154a01784069f24f2d31ee11d0cee476348da679` 上为 **37 failed / 3 passed**；
相同 40 项在修复后通过。相关五个测试文件合计 **72 passed / 2 skipped**：

```text
python -m pytest tests/test_d3plot_time_validation.py tests/test_results_lasso.py tests/test_public_corpus_diagnostics.py tests/test_public_corpus_review.py tests/test_post_tools.py -q -p no:cacheprovider
```

原创真实 d3plot 夹具仍证明上游返回 `[0, -999999, 1]`；在不替换读取器的情况下，
三条公开读取路径均拒绝同一损坏文件，前后整个输入族的字节指纹不变。
公开语料复测同样在清点、完整读取和第 1 状态选择前拒绝第 3 状态 EOF，输入文件及目录清单不变，
见 [去路径记录](evidence.json)。仅使用既有 LASSO 2.0.4 与项目源代码，不启动 LS-PrePost 或求解器。

## 剩余验收

这是 L1/读取器实测，不能替代 L2 原生回归；I04 保持 partial。
没有自动修复上游 EOF 边界解析。若尾数据形成有限且非递减的时间，时间轴校验无法证明其结构有效；
结构级检测和正确恢复实际状态数仍是 gap。历史原生结果没有被改写成本次通过。
