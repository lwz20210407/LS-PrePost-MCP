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
这是两份登记输入的有限L2参考，不代表通用层映射、原生内部实现或其它版本；该历史提交产品native_check尚不支持，当前有限接入见下节。
实际revision、空diff哈希、完整误差/来源及9个源码blob见evidence.json。

复跑：python -B -m pytest tests/test_beam_axial_native.py --run-native --native-strict --native-executable "<4.13>" --native-output "<全新外部目录>"；使用已有LSPP_CORPUS_DIR。
Q05保持partial：其他梁量、更广层/版本原生对照仍缺。没有复制公共语料或提交私人路径/原生日志。

## 产品 native_check 接入

新生产调用限定：4.13且文件资源身份无冲突，`domain=beam, quantity=axial_force, native_check=true, native_sampling=default`。
默认`mid`沿旧域合同不变，梁须显式选default；不接受stored_point，不把绑定默认ipt解释成中层/积分点。量与坐标仍是as stored，未知物理单位保持caller-declared，绝不自动换算。
复用finish_native/stage/run_batch/BatchEngine，未新增第二套执行引擎；在力矩阵和哈希/暂存前检查最多1000状态、1000文件/2GiB；单请求最多100实体。
LASSO 2.0.4文件发现将basename作正则，本新入口因此在重IO前明确拒绝正则元字符basename，避免额外未登记读取。7条d2旧头红例修后通过，另4个literal名称控制通过；共享非原生入口的完整族防护另由I01接续。

| 检查 | 范围 | 结果 | 有效性 |
|---|---|---|---|
| 产品4.13 headless | beamip两帧ID1，Ansys十二帧ID2312/1769 | 2通过/26条，力与时间最大差0 | 当前有效（干净0a9d741产品blob） |
| 原/暂存整族与目录/字节 | 五个native身份检查及独立配置/程序/目录检查 | 全通过 | 当前有效（登记输入） |
| 负例与旧域兼容 | profile/参数/预算/CSV/marker/改动源/借用缓冲区与旧node/shell | 152相关通过/2默认原生跳过 | 当前有效（登记范围） |

原始引擎回执仍是unverified；上层在完整marker、CSV逐状态/用户ID及固定时间/数值容差、全族身份守卫通过后才报告本次有限比较成功，未将raw引擎状态改写为succeeded。
实际revision、空diff、13个源/测试blob、每例来源/程序/配置与报告SHA都见evidence.json。历史43360dc实验记录保留，旧实验测试的元数据改称this_test_uses_product_native_check=false，只描述它不走产品比较的路线，不作为当前支持状态。

```shell
python -B -m pytest tests/test_beam_native_check_native.py --run-native --native-strict --native-executable "<4.13>" --native-output "<全新外部目录>"
```

使用已有LSPP_CORPUS_DIR；无GUI、UU或求解器。Q05维持partial，未扩大到4.10/4.8或其他梁量，默认ipt的几何/力学含义尚未独立确认。


CI后续：510b91a的架构测试指出版本比较散落于功能模块。b024cdc将同一准入策略移回统一versions能力表，不放宽检查，原架构回归及相关共171通过。干净b024cdc4c75e0bf32bc599c8af56cccb2b7096fa再次真实运行两例产品原生比较，2通过/26条、全部数值与时间差0、身份守卫通过。0a9d741和43360dc原始run完整保留；当前策略及其native_beam_history/versions等13项blob由最后一条run绑定。未把旧记录重绑为新头。


I01共享结果族防护后复跑：干净e5c3e26750a98ed97690efcdd1ad42c3f8b58056在4.13再次通过两份登记beam的产品native_check，26条力/时间差0，5项内部与4项外部身份守卫通过。引擎raw状态unverified保持，实际数据验证通过；e5源身份绑定新增family及真实调用链。旧433/0a9/b024记录完整保留。f31仅补证据测试仪表，src产品blob与e5相同；未冒充另一次原生。
