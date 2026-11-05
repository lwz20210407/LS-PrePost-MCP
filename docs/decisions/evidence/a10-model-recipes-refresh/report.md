# A10 新材料配方来源后的公开重放（L1）

当前有效重放实际源码为 clean `02b1a9d4220c1df564e813d99eb91eefab4b0490`，构建与查询源码相同。A10 保持 **partial / L1**；没有修改题目、答案、排名、词表或目标，也没有原生验证或新独立留出。逐题 top3、raw BM25、等级、稳定来源及产品/题集/构建输入 blob 见 [evidence.json](evidence.json)、[汇总](summary.md)。

此前 [a03 active 对象](../a10-replay-refresh/report.md) 的全部七文件原字节保留；[f04843a 历史](../a10-cross-language/report.md) 也没有改写。本目录是新的实际运行，不给旧结果换 revision。

| 冻结集 | prior a03 | 本次 | API 类 | 性质与有效性 |
|---|---:|---:|---:|---|
| legacy_20 | 14/20 | 14/20 | 0/4 | 历史调优；本次当前产品有效 |
| dev | 22/30 | 22/30 | 0/5 | 历史调优；本次当前产品有效 |
| holdout_24 | 15/24 | 15/24 | 0/4 | 曾暴露的历史评测；非新独立留出 |
| holdout_b | 13/24 | 13/24 | 0/4 | 调优前独立性未证；非新独立留出 |

总数为 **98 = 20+30+24+24**，不是94。四个题文件 blob 与 be324 基线逐一相同。HI02 历史目标 KI-052 已从已修问题语料移除的限制仍在；历史 B/旧24题暴露及重合限制不因这次重放消失。真实公开 Scripting API 来源为0，不能把 keyword/model recipe 当成 API 文档补足。

## 唯一索引和口径

索引 SHA256 `621db0eebcb5bdb620c45140aae8139b3f6106a951625fbf971995a5b13602f4`，110,903,296 bytes。3171/3171关键词完整枚举，生成 **66,902 descriptor records**；两条 exact duplicate 合并后，结构化 `keyword_fields` 实际入库 **66,900**。另有38个 field-less keyword，故 keyword 文档总数66,938。command1250、known_issue80、user_guide4、recipe24；其中新增 host 候选9，明确 keyword/L1/原生未验并带内容版本 pin，余下为原有配方来源。

没有本地私有手册、local-book、external/private sources；提供者是锁定 ansys-dyna-core 0.12.1 的公开 metadata。构建 report 登记提供者包 metadata hash、输入文件版本与 Git/LF SHA、文档/稳定位置/文本清单摘要。新 provider、manifest、参数/单位验证及核心材料契约都纳入产品漂移门禁。

Root 对**同一份** SQLite 独立重查98题每条 ranks/scores/refs/provenance，全部与本次记录一致，重查前后完整索引 SHA 不变，没有新建第二库。该内部核对不证明历史题独立，也不证明答案忠实或工程物理正确性。

## 可复跑

使用项目锁定环境，`PYTHONPATH` 显式绑定当次 worktree 的 src/root。以下位置是调用者选择的仓库外目录，不是本机路径；禁用私有手册环境，不提供 external source。

```powershell
$env:PYTHONPATH="$PWD\src;$PWD"
Remove-Item Env:LSPP_MANUAL_INDEX -ErrorAction SilentlyContinue
python -B tools/build_knowledge_index.py --all-keywords --output <public-index.sqlite>
python -B tools/refresh_knowledge_evidence.py --index <public-index.sqlite> --index-build-report <build-report.json> --output-dir <fresh-output>
```

本次实际建库由任务外 runner 调用同一 `repository_documents/keyword_fields/fieldless/build_index` 库接口，额外断言 public-only 并记录实际 clean HEAD/前后 source snapshot；CLI 是等价步骤，不冒称机器上当时执行的原文。build-report 必需 `actual_git_revision`、`working_tree_dirty`、`index_sha256`、`document_text_manifest_sha256`、`keyword_coverage`；其中 manifest 按工具现有SQL顺序登记来源/位置/版本/许可/文本hash。实际重放命令就是 `refresh_knowledge_evidence.py`。

前三引用及 score 保留原记录，不把内容派生 doc ID 变化全部归因某个排名提交。与 f048 的稳定位置无法恢复者仍 unknown。单独追加新源后的无变化命中总数，也不代表每条名次/分数不变；逐题内容以本次原始表为准。
