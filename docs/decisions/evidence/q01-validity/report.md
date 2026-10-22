# Q01 观察值与部件标题有效性（2026-10-22）

修复 result_info 的合同错误和共享 overview 的部件标题关联。Q01 保持 partial，
原生 L2 身份复跑与大于 2000 状态的完整时间列表仍是原有缺口。

## 原生回执

原生 inspect_model 的执行成功不保证回执的数值有效。状态数不是非负整数、
时间列表缺失/畸形/含非数值或 NaN/Inf 时，保留原生 job ID 与执行状态，
将无效字段置为 null，并记录 observation_errors。公共结果返回 partial，
保留有效 LASSO 概览、error 和非通过的 backends_agree，不让二次 ValidationError 逃逸。

两套有限时间相减仍可能溢出。此时最大时间差留空，difference_overflow=true，
backends_agree=failed；不把 Inf 写入 JobResult。有限但不一致的原生观察仍按比较失败报告，
不误标为执行器崩溃。

## 部件标题

通过 part_titles_ids 与 part_ids 连接标题，不把标题数组序号当作 Part ID 的位置。
缺少某个部件的标题记录时保留 null；完全没有标题 ID 时所有标题留空并把 warning
透传到公共结果。重复 ID、非正整数 ID、ID 与标题长度不符均明确拒绝，避免错误标签。

## 回归

最初 21 项反例在 main `4e3a9a84bffc5443a463911ffe9eca2c012dbff1` 上全部失败，
修复后通过；随后补充巨大整数时间和标题 warning 透传两项。

```text
python -m pytest tests/test_result_overview_validity.py tests/test_result_overview.py tests/test_results_lasso.py tests/test_result_validity.py -q
56 passed, 1 skipped
```

测试覆盖 NaN 的不同位置、正负 Inf、嵌套/字符串/布尔时间、坏状态数、有限差值溢出、
标题 ID 顺序不同及缺失/冲突。公共结果可严格 JSON 编码并符合 JobResult；
job.json 的状态与返回值一致。修复没有启动 LS-PrePost，没有新增原生通过声明。

完整依赖回归（Python 3.11）：**2407 passed / 294 skipped**。
Ruff、import-linter（三个合同）、任务/文档/迁移/语料登记/链接检查通过；
后续同步 main 后的精确头仍需正式五项 CI 验证。

## 已登记公开输入读测

在干净提交 `a3388131380f403674e1a82439a641826ae7a41b` 上直接读取：

| 输入 | 状态数 | 部件数 | 存储 ID 与标题关联 |
|---|---:|---:|---|
| d3plot_projectile | 16 | 2 | 一致 |
| shell_d3plot | 7 | 4 | 一致 |
| Bolt_B_Explicit | 102 | 7 | 一致 |

三例均 succeeded；原始 d3plot 全族 SHA256 与目录清单均未改变，
见 [evidence.json](evidence.json)。未复制语料，未调用 LS-PrePost。
这些读测已加入 test_result_overview_validity.py 的可选回归；
未设置 LSPP_CORPUS_DIR 时跳过。
