# Q01 状态清点与原生对照（2026-10-23）

结果概览现在保留完整状态时间数组，移除了 2000 状态截断。状态、变量、
部件/标题 ID、单元族、可读 HSV/头字段、删除数及同目录 binout/ASCII 清点沿用共享读取层。
本记录范围是结果清点与状态时间对照。

## 实际运行

所有原生作业均串行、`-nographics`；每次从干净提交启动，tracked diff 为空。
记录完整执行文件 SHA256、版本资源、配置 SHA256、输入 d3plot 全族 SHA256、
result_info/native 两级 job ID、状态数和全部时间数组的比较。
源文件、源目录清单和使用的源配置在运行前后保持不变。

| 运行 | 实际提交 | 案例 | 结果 |
|---|---|---|---|
| r413a | 465c129 | 4.13：公开 projectile、shell、Bolt | 3 passed；首次历史读测，尚未去除 2000 状态截断 |
| r413b | 55581be | 4.13：上述三例，加生成的 2001 状态实体 | 4 passed |
| r410a | 55581be | 4.10：公开 projectile、2001 状态实体 | 2 passed |
| r48a | 55581be | 4.8：公开 projectile，原配置 | 1 failed；JobResult=partial，Python-home 无效 |
| r48b | f9b980f | 4.8：公开 projectile，隔离配置尝试 | 1 failed；JobResult=partial，进程退出 0xC0000409，无回执，原因未定 |

4.8 按既定 D3 尽力范围处理，当前本机原生路径未认证。
隔离尝试只在测试配置副本中复用一个已用于 4.10 的 Python-home 设置；没有安装包，
原用户 4.8 配置哈希保持不变。不把返回码 0 或缺少回执当成通过。

完整提交号、每例数值/容差/身份和两次 4.8 失败均保存在 [evidence.json](evidence.json)。
每次运行另有精简报告：[4.13 首轮](r413a-report.md)、[4.13 当前](r413b-report.md)、
[4.10 子集](r410a-report.md)、[4.8 原配置](r48a-report.md)、[4.8 隔离尝试](r48b-report.md)。
报告 SHA256 按 UTF-8/LF 口径计算；测试源码用 Git blob ID，可跨平台重算。

## 对应验收

1. L1 与公开输入读测核对完整清点，见 [Q01 有效性回归](../q01-validity/report.md)
   与 tests/test_result_overview.py；缺删除标志仍为 null，头附加值不冒充可读 HSV 数量。
2. Bolt 的四个 MPP 分片和同目录 GLSTAT 等清点通过公开语料回归；仍由共享 catalogue 提供。
3. 当前 4.13 四例、4.10 两例的状态数及时间数组一致。
   时间容差为 `1e-6 * max(abs(reader_times))`，逐值比较，不插值、不调整时钟。
   2001 状态例在两版都实际通过，三个 L1 截断反例在修复前全部失败。

```text
python -m pytest tests/test_result_overview_native.py -m native --run-native --native-strict --native-executable <installation> --native-output <fresh-external-directory> -q
```

需要已初始化配置和 LSPP_CORPUS_DIR。4.10 子集加 `-k "projectile or long_state"`，
4.8 尽力尝试只选 projectile。没有 --run-native 时四个用例跳过，不启动进程。
普通相关回归为 46 passed / 8 skipped；最终主干集成仍以精确 PR 头的五项 CI 为门禁。

仓库只保留脱敏身份与摘要，不提交原始语料、原生日志、私有路径、配置内容或可执行文件。

最终普通/公开输入/任务文档相关回归：**58 passed / 4 skipped**；跳过项为未授权启动的原生四例，真实原生运行另按上表记录。
