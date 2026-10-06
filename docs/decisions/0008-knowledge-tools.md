# A10：面向 Agent 的参考检索

search_docs 查询六类资料；keyword_fields 保留字段的卡片、option、列位、说明、
引用、手册定位和验证归属；command_help 查询命令语法/源码示例。
三者通过 LSPP_KNOWLEDGE_INDEX 使用仓库外 schema-v2 索引。私有记录默认隐藏，
须显式 include_private。字段信息沿用 Claude provider，不另写解析器。

每条结果带来源、版本、内容身份与 evidence_level：documented、source_example、
native_verified。字段的 native_verified 是 provider 报告的关键字/卡片级求解
接受范围，响应明确写出归属和限制；不据此宣称每个字段效果都已验证。
查询文本和命中文本都是数据，不作为执行指令。

查询原文直接交给索引，query_expansion 为空；已删除与旧题面一一对应的
九条扩展。代码标识符支持前缀检索，摘要优先围绕命中词。旧命令表缺失的保存/PNG 示例由现有纯命令
构建器生成，按源码示例标记并保存构建器文件 SHA256，不冒充手册或原生运行。

[固定二十题评测](evidence/a10/report.md) 的 18/20→20/20 受到题面专用词表
和来源补齐影响，作为调优集历史记录保留，不再作为 A10 done 的依据。
A10 保持 partial；新增六类 24 题留出集，冻结后不按结果调整词表或排序。
只导出文档 ID/来源/版本等元数据，私有正文与本机路径不入库。
I05 仍保留 M3 provider 集成和完整字段覆盖的 gap。

配方证据从索引中的 versions_verified、各执行模式 by_version 和 L2 用例
提取，只对列出的版本与模式标记 native_verified，并注明来自配方的声明。
未验证、失败模式及旧 JSON 模板仍按源码实例处理；检索结果不是当前执行回执。
