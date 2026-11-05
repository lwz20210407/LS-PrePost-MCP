# P12 Joint 单文件回读：两版同源与不可变历史

P12 保持 `partial`；本次仅完成自有单文件定义回读的有限原生范围，不等于 typed Joint 查询、Include 路径解析或运动学验证。数据及活动选择见 [evidence.json](evidence.json)，原 [P12/R11 历史](../p12/report.md) 未改绑。

## 当前活动记录

顶层 `active_run_ids` 选择六个原始 run，`active_source_checkpoint` 选择真实 be0 的40项来源。每个 run 永久保留原 actual revision/dirty/diff/source snapshot/GitBlob/工作树字节哈希；换源码时追加 run 与 checkpoint、切换指针，不重写旧对象。

| Profile /fixture | 实际提交与上下文 | Joint /节点/实体 | 严格原差 /格式记录 /语义差 | 当前有效性 |
|---|---|---|---|---|
|4.13 /pilot|`be0cd4d` 原批次|1 /20 /2|0 /0 /0|活动：已通过|
|4.13 /nine_types|`be0cd4d` 原批次|11 /193 /18|2 /2 /0|活动：已通过；R1原差保留|
|4.13 /body_modes|`be0cd4d` fresh续跑|4 /80 /8|0 /0 /0|活动：已通过|
|4.10 /pilot|`be0cd4d` fresh续跑|1 /20 /2|0 /0 /0|活动：已通过|
|4.10 /nine_types|`be0cd4d` fresh续跑|11 /193 /18|2 /2 /0|活动：已通过；R1原差保留|
|4.10 /body_modes|`be0cd4d` fresh续跑|4 /80 /8|0 /0 /0|活动：已通过|

每组均经现有 create/check→save_model 实际另存树重开→独立 export_keyword，3个headless进程均exit0；共18个已知真实PID。所有节点/实体连接/Part归属/Joint节点、参数、集合及曲线按手工预置值核对；两向已有CNRB和新节点刚体也包含在body_modes。六项身份守卫通过；两份用户配置完整字节、SHA、size、mtime在组边界及末尾均不变，私有before完整快照留在仓库外。

4.10通过既有中央批处理策略：file/product4.10.0.1、fixed4.9.0.1，`resource_conflict=true` 原样报告。字符串/标签冲突、排除版本、未识别资源来源仍拒绝，未改能力表。来源绑定31个关键产品路径加9个producer/fixture/test/lock，共40项；这是provenance，不是全模块功能覆盖。

## 控制中断与恢复

原批次已完成4.13前两组6进程，随后只读 WMI 库存子命令12秒超时；其controller-error原样保留。该时刻 body_modes 目录和job尚未创建/派发、4.10未启动，不能把控制器失败写成领域失败。恢复前重新确认同一be0/40来源、完整snapshot及两配置仍与旧before完全一致；在新目录只跑剩余4.13body3+4.10三组9，未重放已通过前两组，也未重放旧job。Get-Process命令的成功返回码、timeout、可解析空JSON数组均留私有回执；失败/未知从不当空池。

用户明确报告此前13:24:59未手工改配置。Root随后找到另一并发渲染任务与该时刻相符的所有权/版本/最近文件旁证，级别仅为`corroborated inference`，不是内核WriteFile归因，也无证据归因本MCP4.13。外项目路径、模型与日志不公开。当前活动批次两配置没有漂移。

## 严格字段与 native-only R1 分类

手写fixture仍为R1空白/None，默认离线compare严格不变。R11 Vol I PDF735（印刷10-57）只说明R1用于gear/pulley半径，不证明motor空白等于零；锁定SDK0.12.1把两种motor该槽标为不应定义，真实导出补成0.0。三来源页码/文件SHA/类SHA/旧失败报告SHA独立记录，厂商原文和图片不入库。

仅native-export路线、两种确切普通MOTOR_ID、expected/actual TYPE均精确int0、R1存在且实际值为精确数值零时单列格式记录；原`strict_card_differences`保留，`semantic_differences`分开。非零（含极小非零）、bool、NaN/Inf、字符串、缺槽、其他关键字/选项和其他参数仍失败。未放宽物理容差；逐字节相同仅指saved与staged，不宣称native导出全部字段/字节不变。

## 历史与回归

|记录|旧实际源|结果|当前有效性|
|---|---|---|---|
|4.13探索|`80a9963`|1 Joint通过；早于完整字段修复|历史，未重绑|
|正式尝试|`1b7fc60`|pilot通过、nine_types严格R1失败|原失败永久保留|
|失败输出只读分类|`e8239c0`分析`1b7fc60`|严格2/格式2/剩余语义0|仅analysis-only，非新原生|
|单版三组|`28a3494`|4.13三组9进程通过|历史；早于4.10入口修正|
|同源两版六组|`be0cd4d`|18进程，零语义差|由active指针选中|

身份截断旧基线19 failed/1 passed；CNRB大PID3 failed/1合法控制passed；合并MOTOR_ID 1 failed/3控制passed；完整字段10 failed、motor保留字段另2 failed/2控制passed；native-only R1旧严格路径6 failed/22拒绝控制passed。四份有效输入LF golden与旧产品一致，不替代solver证据。历史旧红例缺统一runner回执处保留null和限制；Git对象baseline不冒称完整旧checkout。

4.10入口修正的旧28两条误拒红例，以及pytest显式batch委托边界红例均保留；之后针对性51 passed/3默认native skipped。完整PR CI另行执行，内部peer不替代任务改done前的用户独立审阅。

`captured_file_sha256`是原机工作树原始字节（可含CRLF），CI不拿它等同Linux LF；portable身份使用记录的GitBlob。raw报告SHA不等于本sanitized摘要SHA。没有把后验Git LF归档哈希冒充新测。
