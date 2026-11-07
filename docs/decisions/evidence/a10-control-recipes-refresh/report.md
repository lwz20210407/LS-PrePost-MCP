# A10：控制配方登记后的搜索投影回归

任务保持 partial / L1；四套题都已暴露，不称为独立留出集，仍缺真实 API 来源及独立质量验收。

| 上下文 | 实际 Git revision | 20 / 30 / 24 / 24 题 Top-3 命中 | 有效性 |
|---|---|---|---|
| 新控制配方初次建库 | 0162fdc1da3d132d32b8aa8fda309b5a26742ba5 | 14 / 22 / 14 / 13 | 已被取代，失败事实保留 |
| 通用功能字段投影修复 | 80e122e2d493c16aaacd56c45b2045315e03f1ee | 14 / 22 / 15 / 13 | 当前关键产品来源有效 |

首轮 HR04 的截图目标被三个控制配方挤出前三。实际原因是 `field_provider_snapshot` 和 `field_schema_snapshot_version` 等来源字段的 `snapshot` 被计为功能词；小型独立合成反例在旧 main 21978f8 上真实失败。修复只将模型配方的 id、标题、描述、标签、keyword 和完整参数 schema 放进 FTS 搜索词，保留 documents 中的完整 JSON、ID、SHA、固定引用及来源。畸形注册表 JSON 拒绝建库，不静默回退到元数据搜索。查询、排序算法、词表和四套题均未改。

两轮公开文档正文与来源清单 SHA256 都为 `b292760c77f31ebee8356efb3c8cddfca708b7cc606bb73ee01794b8f52b9108`。两次分别来自不同干净提交，各实际建库一次；首轮不是成功结果，也没有覆盖。3171/3171 个关键字、66902 个描述记录、66900 个去重字段和 38 个关键字级文档保留；16 个配方文档的当前引用一致，原九个固定旧引用在编辑前明确拒绝过期。

实际通过既有库调用 `repository_documents / keyword_fields / build_index` 建一个公开索引，再用 `refresh_knowledge_evidence` 在同库回放四套共 98 题。等价 CLI 为 `python -B tools/build_knowledge_index.py --all-keywords --output <external-index>`，以及 `python -B tools/refresh_knowledge_evidence.py --index <same-index> --index-build-report <build-report> --output-dir <fresh-directory>`。未加载私有手册、未运行 Native、未安装环境。旧 v2 索引仍可只读使用；此功能字段投影只在重建索引后生效。

完整逐题结果见 [summary](summary.md)，首轮回归与前后 SHA 见 [first-regression.json](first-regression.json)。未改变早期 a10-model-recipes-refresh、a10-cross-language 或任何旧证据。
