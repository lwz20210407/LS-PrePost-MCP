# Q05：梁轴力存储标量时程

extract_history 支持 d3plot 的 beam / axial_force，读取锁定LASSO2.0.4的
`element_beam_axial_force`，不把它当应力、壳层或全局X方向量。
使用存储的beam用户ID，按请求顺序选择列后才扩为float64；原始alive、删除首次状态、
unknown及数值保留，不填活跃、不删除样本。矩阵/ID错误明确拒绝。

units/time_units仍由调用者声明，不换算。已知单位检查力/时间维度，未知模型标签保留但标unverified。
stored_point对该标量不适用；native_check在参数、路径守卫校验后预检拒绝，不读整族、不建job、不换binout。

```json
{"path":"<d3plot>","domain":"beam","quantity":"axial_force","entity_ids":[71,19],"units":"N","time_units":"s"}
```

原基线9c3c614新增测试8失败/6通过；性能与拒绝时机的两项回归在62bc452失败。
修复后相关94通过（含专属37，不相加），Ruff/imports通过。
干净提交236212aa1f8780710e86fcef6e4eeb9a31cb44c8真实重跑的读测见[evidence.json](evidence.json)。

| 公共来源ID | 原存储形状 | 请求ID | CSV与原列 | 有效性 |
|---|---|---|---|---|
| result.ansys__example-data.result_files.d3plot_beam | 12×544 | 2312,1769 | 误差0，时间/alive一致，整族哈希不变 | 当前有效（登记范围） |
| result.open-lasso-python__lasso-python.test.test_data.d3plot_beamip | 2×1 | 1 | 误差0，时间/alive一致，整族哈希不变 | 当前有效（登记范围） |

这些数据存在非零轴力；物理单位未知，只测试caller-declared口径。旧62bc记录留本机作历史，未修改其revision。
本证据属于L1/共享读取后端的实际数据对照，未运行LSPP，不是独立物理或原生L2。
Q05保持partial：其他梁量、更广层/版本与beam原生对照仍缺。没有复制公共语料或提交私人路径/原生日志。
