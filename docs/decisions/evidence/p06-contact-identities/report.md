# P06：接触目标身份补修（L1，partial）

现有创建入口会把`part=True/1.5`经int截断成Part1。本轮仅修改plural `contacts.py`，复用shared exact_integer规范化A/B各类目标ID、parts/nodes成员、exterior/select.parts和CID；整数值1.0、已有整数文本、正常list/tuple/一维数组及合法Mapping过滤器保持。标量文本/bytes/mapping不能冒充ID序列。身份规范化先于依赖分配；不宣称所有形状、引用或物理失败都已事务化。

没有重做五类创建，不改singular contact.py、geometry、operations或model_target_tools；不新增T1/签名、不改物理参数/default、零CID卡片表示或P06原验收/版本/partial。没有native/R11/GUI或全文索引。[完整来源与结果](evidence.json)只归档合成主机证据，不含本机路径/原始日志。

| 上下文 | 实际结果 | 有效性 |
|---|---|---|
| main51c5，新增测试WIP | 28 failed / 14合法控制通过；公共API错误成功选择现有ID，另有分配前规范化回归 | 历史，已修 |
| 51c5精确Git对象进程内overlay | parts文本/mapping/bytes三个公共调用均错误成功，真实3 failed / 58 deselected；不冒称clean checkout | 历史，已修 |
| 首次green-target迭代 | 18失败来自测试误用JobResult没有暴露的data.written；改为实际失败/无artifact/无.k验收 | 测试断言作废，不是第二代码缺陷 |
| clean bcfa | 83通过，但peer另发现nested UserDict可绕过dict判断；两新用例在bcfa真实失败 | 原capture保留，当前来源已取代 |
| clean85c707合main1735后 | 87/87通过，source before/after保持；65专属与既有22相关回归同一次运行 | 当前登记产品来源有效 |
| 精确85内部终验 | 4控制通过：两旧UserDict布尔漏口在provider/分配前拒，两个合法UserDict保持caller与既有heading/changes | 内部Codex复核，非独立外部done审阅 |
| SDK缺席 | 进程内阻可选provider，11通过/54按依赖跳过 | 不更改共享环境 |

5.8KB golden在未改51c5上由合法输入生成，仅证明五配方输出字节保持；另独立核对提供的FS/FD、single-surface厚度/比例参数不变，不把golden称为求解器物理oracle。原dict不变、B身份或CID错误时A不分配、scalar整数文本和1.0、正常序列、合法Mapping均有控制。

依赖口径：P12旧PRODUCT31/总scope40，合171后PRODUCT32/scope41；P05自身PRODUCT34/scope41。这些当前清单均不含contacts；模块仍被operations导入，变动体只在`op=add_contact`调用，不能仅凭列表宣称全程序无依赖。P03原JC故事用forbidden contact tripwire真实1通过/50 deselect，仅限该故事；当前P03/P05/P12三项来源门禁另真通过，无native重跑。34项产品身份也不代表各模块全部功能都测过。

几何host check_contacts接线、原生Contact Check、接触物理选项与更多版本仍属于后续P06范围，本轮不升级done。

2026-11-07 恢复收尾时只读核对了原始 87 项 JUnit、执行前后源码清单、12 个原始日志/回执哈希及 4 项内部复核，均与登记一致；没有替换旧执行 revision。证据测试同时绑定当前 34 个产品文件和 4 个测试/fixture Git blob，并核对本报告的 LF 规范化哈希。后续任何登记文件变动都需新的实际执行记录，不能把本次历史记录改绑到新 revision。
