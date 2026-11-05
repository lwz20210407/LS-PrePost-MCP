# A10 当前公开索引重放（L1）

题集原样保留；这不是新独立留出集，也不是原生或工程正确性验证。

| 题集 | 性质 | f04843a 历史命中 | 本次命中 | API 命中 | 有效性 |
|---|---|---:|---:|---:|---|
| legacy_20 | historical_tuning | 14/20 | 14/20 | 0/4 | 登记修订/索引有效 |
| dev | historical_tuning | 22/30 | 22/30 | 0/5 | 登记修订/索引有效 |
| holdout_24 | previously_exposed_historical_evaluation | 16/24 | 15/24 | 0/4 | 登记修订/索引有效 |
| holdout_b | independence_unproven_historical_evaluation | 13/24 | 13/24 | 0/4 | 登记修订/索引有效 |

## 评分变化

| 题集/题号 | 历史命中→当前命中 | 首个正确名次变化 | 稳定引用比较 | 有效性 |
|---|---|---|---|---|
| dev/DK11 | True→True | 1→2 | True | 历史对比 |
| dev/DI26 | True→True | 2→1 | 历史位置缺失，无法断言 | 历史对比 |
| dev/DI27 | True→True | 2→1 | 历史位置缺失，无法断言 | 历史对比 |
| holdout_24/HI02 | True→False | 1→None | 历史位置缺失，无法断言 | 历史对比 |
| holdout_24/HI04 | True→True | 2→1 | 历史位置缺失，无法断言 | 历史对比 |
