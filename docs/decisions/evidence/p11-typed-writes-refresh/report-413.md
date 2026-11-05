# P11 typed writes：4.13 新不可变配置输入

actual source `1289eb4edadb77b71d3ee90928d3fec0716e8465`，dirty=false/empty diff，source snapshot `611d3bbb306a082a370743dfe5e722ab0e847dc450d3a8185c7343216c3af2a8`。
新输入source_kind为`immutable_private_snapshot`：每个真实job的configuration.source已逐一解析为正确版本的只读私有snapshot，并匹配完整SHA；不是live global。

| 口径 | 实际结果 |
|---|---|
| pytest assertions |12 passed / 0 failed / 0 skipped|
| 外层业务 |10 succeeded / 1 partial / 1 expected failed|
| 真实native job |23，全部PID>0、rc0、noGraphics、无超时|
| 输入/程序/原树 |两私有input完整bytes/stat、exes、source/public保持；无残留|

预期failed已做一次before-save检查，不是启动前拒绝；partial仍不算完整成功。before_save沿既有规范化观察，after_reopen仍在保存根目录按相对文件名读取实际树。
两个live global profile只被动观察，可能变化，不是这轮配置输入；source_modified=false只说明实际私有source检查范围，不声称全APPDATA隔离。
执行资源profile完整保留；4.10仍fixed4.9/string4.10冲突，未据此变成无歧义。

| 用例 | 业务 | 真实进程 | 原始另存树重开 |
|---|---|---|---|
|edited|succeeded|2|True|
|edited-search|succeeded|2|True|
|empty|succeeded|2|True|
|include|succeeded|2|True|
|mismatch|failed|1|None|
|placeholder|partial|2|True|
|public-edited|succeeded|2|True|
|public-include|succeeded|2|True|
|relative-search|succeeded|2|True|
|search|succeeded|2|True|
|standalone|succeeded|2|True|
|unused-search|succeeded|2|True|

原P11十四source路径与两测试文件按actual1289绑定；Source40整批上下文只作来源审计，不代表所有模块功能覆盖。旧run、旧失败/恢复和live输入结论不重写。GUI/4.8/更多Include/完整物理检查仍gap。
