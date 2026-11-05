# P12 Joint 单文件回读：真实历史与待验证范围

本记录保持 P12 `partial`，没有把历史探索、失败后的离线分类或内部复核算成完整原生验收。逐条实际身份、来源 blob、安装/配置哈希和报告摘要见 [evidence.json](evidence.json)。原 [P12 R11 历史](../p12/report.md) 未改、未重绑；全部本机原始日志及厂商手册留在仓库外。

| 记录 | 实际提交 | 结果 | 当前有效性 |
|---|---|---|---|
| 4.13 单铰链探索 | `80a9963` | 3 headless 进程，1 Joint /20 节点/2 实体，通过 | 历史探索；早于完整字段校验修复，已被后续检查取代 |
| 4.13 正式批次：pilot | `1b7fc60` | 3 headless 进程，单文件创建→实际另存树重开→导出通过 | 历史尝试；不是 e823 仪表后的验证 |
| 同批：nine_types | `1b7fc60` | 3 进程返回0；严格核对失败：908/909 的 R1 从空白写成0.0；六守卫均真 | 原失败保留；没有回写成通过 |
| body_modes /4.10 | — | 首败停止，均未启动 | 尚待实测；不建立虚构 run |
| 原失败输出的只读分类 | `e8239c0` 分析旧 `1b7fc60` 输出 | 严格原差2条、可解释表示变化2条、剩余语义差0条 | 仅离线分析；不是新原生执行，旧失败结论不变 |

每条实际原生记录保留自己的 actual revision、dirty/diff、完整 source snapshot 摘要与关键产品/producer/fixture blob、executable/config SHA、三个进程回执、原始报告 SHA 和输入/另存/暂存/导出文件哈希。原生比较只证实自有单文件的定义保留，不能证明 typed Joint 识别或运动物理。

## 修复与回归

| 问题 | 旧产品基线 | 旧代码结果 | 修复 |
|---|---|---|---|
| 小数/布尔身份截断，非法请求留下改动 | `2e70697` | 19 failed /1 passed | `deb709d` |
| CNRB 邻近大 PID 近似误绑定 | `deb709d` | 3 failed /1合法控制passed | `39a861a` |
| 同块 MOTOR_ID 的 PARM 卡计数 | 旧 `joint_checks` | 1 failed /3控制passed | `424764f` |
| LOCAL/FAILURE、缺失/未知字段、标题被忽略 | `80a9963` | 10 failed | `e8f12e6` |
| 电机 PARM/R1 值变更被忽略 | `80a9963` Git对象 | 2 failed /2合并控制passed | `e8f12e6` |
| native-only R1 表示变化缺少独立审计 | `1b7fc60` 严格路径 | 6 failed /22拒绝控制passed | `e8239c0` |

旧红例中采用模块 Git 对象加载的记录只绑定相应产品代码，不冒称完整旧 checkout 或原生运行。历史 pytest 日志没有统一 runner 身份回执，JSON 明确保留该限制。四种有效整数输入的 LF 输出 SHA 与旧基线一致，证明兼容性，不替代物理证据。

精确干净 `e8239c0` 的新收据：相关测试 **180 passed /3 默认原生 skipped**，源码前后不变；内部有限 peer **46 passed**。SDK 缺失边界另有38 passed /1 skipped的模拟检查，不冒称完整最小依赖门禁。完整 PR CI 和后续原生证据仍需分别完成。

## R1 仪表规则与边界

R11 Vol I PDF 第735页（印刷10-57）说明 R1 用于 gear/pulley 半径；它没有给出 motor 空白等于零的默认语义。锁定 SDK 0.12.1 对两种 motor 的该槽标为不应定义、schema 默认 None；实际4.13写出将这两个不适用槽补成0.0。手册页码/文件 SHA、SDK 类 SHA、真实旧失败报告 SHA 分开登记，原文和图片不入仓库。

因此保留手写 `expected.r1=None` 和默认/离线严格比较。只有 native-export 路线、两种确切普通 `*_MOTOR_ID`、两侧 TYPE 均为精确整数0、R1 字段存在且实际值为精确数值零时，才单列 `format_normalizations`；原 `strict_card_differences` 不删除。非零（含极小非零）、bool、NaN/Inf、字符串、缺槽、其他关键字/选项及其他参数仍失败。没有调整物理量容差，也不声称导出卡字节或全部字段完全不变。

下一步等 I02 合入后同步 main，补 `deck/matching/_identity` 来源存在性门禁，再在实际新头上分批申请4.13三用例及4.10验证。Include、typed Joint、运动学、R11 及独立审阅要求继续保留。
