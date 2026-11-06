# P04 当前13来源有限成员复验（L2，partial）

实际 clean revision `342b07c4410130f1e67352f4ee0a9bf22dd870a3`，完整捕获 inventory663 / snapshot `836cfc612e6aec5b40710a70f7849bcfcf5852688e37733d85291bf153441904`。仅追加本次4.13的一个真实 headless job，未重跑旧 Native24、host60/87/90或 wheel；原 b757 记录不重绑。

原比较 SHA256 `f68b391a96ba9da177d2a1301a76c74c8c9d206544e10a2496e13c3b6f313a28`，完整 lease proof SHA256 `3eaabc623db7ce63f3c0abc74e19c02bdb48a28070d0cf014263f23d373e3c83`，实际 manifest SHA256 `00f048f45c84e811208a375cd4174f6213644eab9d1fbda18c15572fd7f92604`。13项选定产品来源逐项记录当时完整 source_files 的 raw SHA 与 Git blob；producer/test 同样绑定实际 revision。

PROGRAM SHA256 `5967ca69432f5ef27d4df254fcd3f30b2db766859c4ba6b8609c810e0cd90ce1`、SOURCE SHA256 `ce74672180f3ba250663dd788aef88da74a85c15aafa7df5657ff6caf2a90cd0`，与890版本相同；手写oracle、validate和native动作调用未修改。原先遗漏的 model_target_tools / contact_report / contact 现在明确准入，不把 helper(None) 执行路径忽略。

四个UID11/37/89/121的完整 registry、0基 named internal_id/user_id 回环成立；LIST101、GENERATE202、ADD303三类 membership 均相同。definition_order_equal 分别 true/true/**false**；ADD不承诺定义顺序，有限一基set slot解释仍以完整独立registry/rank/回环为前提，不外推为通用节点集读取器。

job UUID `ef3ca4bdeb85477d91be381c897b998e`，manifest PID51528、rc0、nographics、graphics=false和windows_job记录成立，六项producer守卫及完整lease源/公开目录/双exe/两份readonly私有cfg byte/stat守卫通过，结束时无残留。controller/child OS创建时间均未观测；manifest host起止时间不冒充OS时间，JobObject关联按manifest/engine证据表述，不声称重新连续观察内核绑定。

逐job大exe manifest的sha256=null，仅path/stat与>64MiB hash_note；完整ce76 SHA来自外层执行前后链，不冒充逐job字节完整SHA或进程内连续监控。每job私有cfg source_sha256为完整值。全局配置仅被动观察，不是输入，不能据此声称隔离已证明；没有新4.10 native执行。

旧p04-typed-writes-refresh及01a/950/d139原记录、失败/回放/REA有限依据保持原值，另见历史context引用；没有新反编译、供应商源码公开或广泛真实模型验收。当前任务保持partial，原版本/验收不变。
