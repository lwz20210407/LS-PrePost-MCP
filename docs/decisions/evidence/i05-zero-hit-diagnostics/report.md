# I05：零命中仍保留索引诊断

旧 schema-v2 索引缺当前 API 标识符分词标记时，重建提示原先仅在命中行和日志里。
零命中因此使 MCP 调用方无法区分旧索引召回边界与确实没有参考。本次保持 `result=[]`，
另以 `diagnostics` 传递 schema、分词版本、重建提示和概念预算，不制造假命中。

Python 的 search_index/search_docs/search_knowledge 继续 list 兼容；普通 JSON 编码仍是数组。
MCP full/compact 在协议边界返回标准 CallToolResult，保留非空命中文本和 result 数组；
零命中文本明确标为 diagnostics。未执行的纯符号查询不声称已检查索引。
元数据和结果来自同一个 mode=ro/BEGIN SQLite 快照，当前索引不误报重建，私有内容仍须显式授权。

基线 main `9c3c614` 上首批7项失败；实现提交 `0394c48b0a3c422dea69625e030419820feb1f7f`
已完成103项相关测试，包含真实 full/compact stdio、隐私过滤与输出schema。
本轮根复核与复跑记录见 [evidence.json](evidence.json)。这是L1/协议集成，不是LSPP原生L2。

| 内容 | 范围 | 有效性 |
|---|---|---|
| 索引诊断 | 旧/当前格式，空/非空命中，未实际检索 | 当前有效（登记范围） |
| 协议适配 | full/compact真实stdio，输出schema与私有过滤 | 当前有效（登记范围） |

I05保持partial：真实私有Scripting API/用户指南复验、空字段布局以及A10新独立留出证据仍未完成。
未改任务acceptance或发布范围；没有提交私有索引/资料、本机路径或原生日志。
