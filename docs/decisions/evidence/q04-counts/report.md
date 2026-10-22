# Q04 存活计数与有限值计数（2026-10-23）

修复审阅 P2：`extract_field.data.active_count` 原先来自 extrema.count，
实际统计参与极值计算的有限值行数。仍存活但应力三轴度/Lode 无定义的单元因此被漏计。

- 保留 active_count 字段，改为**返回行中存储的 alive 标志为真的数量**。
- 新增 finite_count：**返回行中参与极值的有限标量值数量**，与 extrema.count 一致。
- 源文件没有删除记录时，active_count=null，不把默认的导出占位标志当作存活证据。
- count_policy 逐项记录口径。element_count 是所选部件内掩码前的单元数，
  row_count 是掩码后的返回行数；计算值、CSV/NPZ 数值及原有掩码行为不改变。

## 回归

实体和壳各四个单元：两个有效应力状态的存活单元、一个纯剪切删除单元、
一个静水/零应力存活单元。最后一类的三轴度无定义，但其存活标志仍为真。

| 掩码 | 返回行数 | active_count | finite_count |
|---|---:|---:|---:|
| alive | 3 | 3 | 2 |
| all | 4 | 3 | 3 |
| deleted | 1 | 0 | 1 |
| 无删除记录，all | 4 | null | 3 |

七个反例在 main `435120b4aaa40423bbd0f2aa912627a18a5e9606` 上全部失败，修复后通过。
相关回归：

```text
python -m pytest tests/test_field_metrics.py tests/test_results_invariants.py tests/test_results_export.py -q
50 passed, 2 skipped
```

公开靶板读测也改为严格断言存活数等于存储 alive 标志之和，有限值数量独立验证。
本次没有调用 LS-PrePost，不新增原生通过声明，不改变 Q04 的任务范围与原验收。

在已合入 Q01 修复的干净提交 `fc10e50057fdfb244274c9f09ca58e801066b059` 上，
公开靶板和壳模型回归 **2 passed**，见 [公开读取日志](public-report.txt) 与
[evidence.json](evidence.json)。测试源记录 git blob ID，日志哈希按 UTF-8/LF 规范化，
不把这些 LASSO 读测标成原生 LS-PrePost 通过。
