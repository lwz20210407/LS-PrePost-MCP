# Q06：ASCII GLSTAT 全局标量曲线

extract_database 增加ASCII GLSTAT的 kinetic_energy/internal_energy/total_energy/hourglass_energy/time_step，
源标签精确对应，time与time_step、total与ratio分开。global scalar没有实体ID；不标成binout变量，不推断或换算单位。
首版支持完整dotted-label时间块，要求核心能量、time_step与time-per-zone-cycle结尾；不排序、不插值、不填零。
重复/倒序、缺项、截断、非有限数和float64下溢明确失败，错误数据不作为已验证CSV返回。

解析前/后以有界SHA256绑定源文件并记录inputs，执行期间变更会失败；预检失败backend也标为ASCII。
预检/哈希/读取阶段均有输入大小上限。raw源族、输出CSV与原始标签分别可核查。

基线main9c3c614首批28失败/1通过；88a340e的六个审阅回归失败，修复后相关115通过/43跳过，
跳过格按具体pytest原因保留，跳过不算通过。公共6份输入28曲线12123值逐值相同，未复制原文进Git。

| 检查 | 范围 | 结果 | 有效性 |
|---|---|---|---|
| 公共ASCII读测 | 6输入/28曲线/12123值 | 数值一致，源SHA不变 | 当前有效（登记范围） |
| 4.13 headless原生 | 已登记Steel_Explicit/glstat的kinetic/internal各101帧 | 2通过，全记录固定容差 | 当前有效（登记范围） |

正式原生提交be51589e25b4a718e67ad57428dff7594cbd94d9工作树干净。
时间rtol=1e-6/atol=0；值rtol=2e-5、atol=1e-6*maxabs；未裁点或调宽。
最大时间差1.775e-9；kinetic/internal最大值差4.155e-10/3.027e-5。
源族/目录、配置与程序身份前后相同，实际进程PID和-nographics均核对，未用GUI或求解器。
具名分量仅在此源/此4.13程序上对应所登记的1/2，未外推通用UI映射，也未启用产品native_check。
独立测试不依赖可选LASSO/PyDYNA；输入通过CORPUS_ID、LSPP_CORPUS_DIR和catalog SHA定位。

```shell
python -B -m pytest tests/test_ascii_glstat_native.py --run-native --native-strict --native-executable "<4.13>" --native-output "<全新仓库外目录>"
```

使用已有公共corpus并设置LSPP_CORPUS_DIR。实际revision、固定diff范围、程序/配置/输入哈希与源码blob见[evidence.json](evidence.json)。
原探测88a340e记录留本机为历史，正式记录不改写其revision。

Q06保持partial：其余ASCII库、更多GLSTAT布局/分量/版本、完整binout原生与真实MPP/SMP配对仍待补。
现严格GLSTAT适配与Q12 nullable能量读取合同不同，共享低层scanner及wall后缀等特例留单独后续PR，不能把缺项null硬改成严格拒绝。
