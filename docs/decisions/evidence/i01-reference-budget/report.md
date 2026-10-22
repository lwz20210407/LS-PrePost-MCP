# I01 原生 INCLUDE 引用预算接入（L1）

派发：[PR #80](https://github.com/lwz20210407/LS-PrePost-MCP/pull/80)。
基线：`e41cf65551274c496f0bb1802f952d1a30e024b2`，基线托管 CI 已通过。
本次只填补原生引用预算 gap，I01 的状态与全项验收保持不变。

## 回归与行为

- 在未改 config.py 的基线上运行专属测试：14 failed / 2 passed。
  默认预算负例到达被禁止的 jobs.create，证明旧实现没有在启动前拒绝重复树。
- 14 层本地合成重复树只有 15 个唯一文件，但展开为 32766 次引用；
  默认 20000 预算现在在作业创建及原生启动前拒绝。
- 3 层重复树共 14 次引用：预算 13 拒绝，14/15 通过；预算 0 接受无 INCLUDE 输入，
  第一个引用在解析名称前拒绝。非法预算在输入文件访问前拒绝。
- files/candidates 的允许目录检查仍优先于 reference_limit 诊断，缺失与越界输入仍拒绝；
  向共享预检仅传 max_references，不传 allow_network。
- 专属测试与已有诊断、边界、共享预算测试合计 69 passed；Ruff 通过。

## 复现命令

使用锁定的 dev/results/pydyna 依赖环境，缓存及 pytest basetemp 放独立的忽略目录。

```shell
python -m pytest tests/test_native_include_budget.py tests/test_include_diagnostics.py tests/test_boundaries.py tests/test_keyword_engine_preflight_limit.py -q
ruff check src tests --no-cache
```

生产代码仅修改 config.py；test_boundaries.py 的预检替身增加关键字参数接收，保留原断言。
共享 domain/model、service.py 和 #72 的 UNC 入口补丁未改动。
本次没有启动 LS-PrePost、可见 GUI 或访问真实网络测试主机。合成输入和测试日志只留本地。
此证据为 L1，不宣称原生 L2、UU 远程条件或 I01 全项完成。

## 完整门禁与来源身份

全依赖（dev/results/pydyna）：1403 passed, 348 skipped in 110.31s (0:01:50)。

最小依赖（dev）：1386 passed, 358 skipped in 103.21s (0:01:43)。

两种环境均运行 `python -m pytest -q --tb=short`，实际命令显式指定独立 cache_dir 和仓库外 basetemp。
首轮全依赖 37 failed, 1366 passed, 348 skipped in 251.09s (0:04:11)；最小依赖 37 failed, 1349 passed, 358 skipped in 228.78s (0:03:48)。
首轮失败由仓库内输出位置与 Windows 深路径导致，改用新的外部短路径后重跑，不修改无关模块。
Ruff、import-linter 及任务、生成文档、迁移、语料登记、文档链接校验全部通过。
修复前后测试结果、真实基线 revision、限定文件 diff SHA256 和规范化源码哈希见 [evidence.json](evidence.json)。
