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
前述236212a记录属于L1/共享读取后端对照，不是独立物理验证。

新增有限原生参考：干净43360dc3a228c78bf98f7ccf559e311820ef097e上，
版本化test_beam_axial_native及独立DataCenter脚本完成4.13两例headless，2 passed/0 skipped，
共26条state/用户ID记录，三条曲线时间与轴力最大差均0。原/暂存整族、源目录和字节、配置、程序五守卫均通过。
沿具名axial_force/Type.BEAM/显式ist读取，使用state_times且向量立即复制；默认ipt语义仍标未知。
这是两份登记输入的有限L2参考，不代表通用层映射、原生内部实现或其它版本；产品native_check依旧明确拒绝。
实际revision、空diff哈希、完整误差/来源及9个源码blob见evidence.json。

复跑：python -B -m pytest tests/test_beam_axial_native.py --run-native --native-strict --native-executable "<4.13>" --native-output "<全新外部目录>"；使用已有LSPP_CORPUS_DIR。
Q05保持partial：其他梁量、更广层/版本与beam原生对照仍缺。没有复制公共语料或提交私人路径/原生日志。
