# A10：面向 Agent 的参考检索

search_docs 查询六类资料；keyword_fields 保留字段的卡片、option、列位、说明、
引用、手册定位和验证归属；command_help 查询命令语法/源码示例。
三者通过 LSPP_KNOWLEDGE_INDEX 使用仓库外 schema-v2 索引。私有记录默认隐藏，
须显式 include_private。字段信息沿用 Claude provider，不另写解析器。

每条结果带来源、版本、内容身份与 evidence_level：documented、source_example、
native_verified。字段的 native_verified 是 provider 报告的关键字/卡片级求解
接受范围，响应明确写出归属和限制；不据此宣称每个字段效果都已验证。
查询文本和命中文本都是数据，不作为执行指令。

少量中文工程术语扩展为检索词，并在 query_expansion 返回；代码标识符支持
前缀检索，摘要优先围绕命中词。旧命令表缺失的保存/PNG 示例由现有纯命令
构建器生成，按源码示例标记并保存构建器文件 SHA256，不冒充手册或原生运行。

[固定二十题评测](evidence/a10/report.md) 首轮 18/20、补齐来源后 20/20。
题目和判断条件未改变，失败首轮一起保留；只导出文档 ID/来源/版本等元数据，
私有正文与本机路径不入库。I05 仍保留 M3 provider 集成和完整字段覆盖的 gap。
