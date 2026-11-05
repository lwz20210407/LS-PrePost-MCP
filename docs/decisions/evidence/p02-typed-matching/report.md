# P02/I07：按声明类型匹配关键字字段

本次修复既有关键字AST `FieldInfo.kind`的find/compare消费者，不是core FieldSpec类型转换完成，也不改变P02/P11/I07验收或状态。
实际产品与有限peer为干净`be3244df3073c6e9b99ac052c093015bbf0419e5`；产品/测试blob及原红见[evidence](evidence.json)。

int字段共享exact_integer，邻近大ID、bool及有损小数不能误绑；float字段即使文本写成整数仍保持原容差。find保留strip/忽略大小写及原混合字符串规则，compare保留strip/区分大小写；None不补0。
比较使用private类型旁路，public JSON仍六个原顶层字段，COLLECT/重复卡完整块、成员整数、参数I/R与mesh连接保持声明类型。Node坐标仍独立位移阈值，curve/DA等连续量保留原容差；P04图、range/ADD定义不覆盖。

| 检查 | 真实结果 | 有效性 |
|---|---|---|
| clean main49外部探针 |12 failed / 6 control|历史真实产品红，外部新测试|
| closed dc63合法比较夹具 |4 failed / 6 control，unchecked两侧空|历史有效红，源compare blob等于main49；不是clean历史测试checkout|
| 最终clean be324内部peer |123 passed|当前有限实现复核，含独立15控制，不是外审|
| 完整模型相关 |546 passed / 1 skipped|a84+WIP提交前执行，源码字节与be324一致；不改写为clean be324运行|
| 禁provider子集 |53 passed / 13 skipped|提交前WIP、最后AST mesh用例之前的子集；不是正式minimal CI|
| 公共标题oracle |3 capture / 15 tests passed|be324 clean、8个来源；不是native|
| 两版P11 r2 |每版12 assertions / 23真实进程|见[原范围新捕获](../p11-typed-matching-refresh/report.md)|

各命令重叠不能相加。首轮ELEMENT超列宽夹具失败已明确作废，后续有效4红重放使用合法布局并确认unchecked为空，不把误夹具算发现。
原P11 r1虽每版12断言通过，但source410配置hash真实变化、整体guard=false，永久保留失败；writer未归属。r2按新输入配置完整保存字节/stat实测通过，不能推断全局写保护已证明。
Q01 active保留全部旧对象并追加a20历史后登记be324新3capture；P11只切active指针到新目录，不回写旧family/raw run对象。

集成阶段单独合并完整有限模型与active来源门禁，一次命令556 passed / 1 skipped，另七项仓库检查通过；运行时HEAD仍be324、仅授权文档WIP，src/tests与捕获源码不变。556/1已含10个active门禁，不与546/1或peer123相加；正式五CI仍须对推送头实际通过。
