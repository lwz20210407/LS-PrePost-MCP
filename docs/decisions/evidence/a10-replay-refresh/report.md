# A10 公开索引与四套历史冻结题重放（2026-11-05）

A10 保持 **partial / L1**。本轮没有修改排名、领域词表、检索实现或任何题面/答案；没有运行 LS-PrePost，也没有做独立外部审阅。
实际逐题结果、首个正确名次、前三条公共引用、原始 BM25 分数、来源版本和证据等级见 [evidence.json](evidence.json)；计数汇总见 [summary.md](summary.md)。

## 结果与题集性质

| 冻结题集 | f04843a 历史公开结果 | 本轮公开结果 | API 类 | 有效性 |
|---|---:|---:|---:|---|
| legacy-20 | 14/20 | 14/20 | 0/4 | 历史调优集，本轮登记修订/索引有效 |
| 开发集 | 22/30 | 22/30 | 0/5 | 历史调优集，本轮登记修订/索引有效 |
| 旧 24 题 | 16/24 | 15/24 | 0/4 | 曾公开/暴露的历史评测集，本轮登记修订/索引有效 |
| holdout B | 13/24 | 13/24 | 0/4 | 调优前独立性未证的历史集，本轮登记修订/索引有效 |

这不是四套新的独立留出集。旧 24 题此前公布过成绩，其中 HC01–HC03 曾在调优前暴露；B 的调优前冻结未获证明，且有六个答案目标与开发集重合。此次完全保留这些限制，所有问题和答案文件的 Git blob/LF SHA256 均已登记。
四套逐题表：[legacy-20](legacy_20-top3.md)、[开发集](dev-top3.md)、[旧 24 题](holdout_24-top3.md)、[B](holdout_b-top3.md)。

唯一命中变化是 **HI02**：题目“临时 JSON 文件路径太长”仍预期命中 KI-052，但当前 `docs/KNOWN_ISSUES.md` 已删除该已修历史条目。当前索引已知问题片段从历史 87 条变为 79 条，KI-052 不在当前输入中。旧命中、原题和分母保留，不通过改答案或补题面对应词条恢复分数；这属于已确认的目标语料缺失，不能据此断言为排名算法回归。

前三条使用 `(category, source_id, locator, title)` 比较，内容派生文档 ID 变化另列。历史返回没有保存 locator/title，只在旧 ID 与当前公开文档 ID 完全相同的情况下恢复位置；无法解析者明确记为 unknown，不凭预期答案猜位置，也不宣称全部变化都来自某个排序提交。历史没有 BM25 分数，分数差异记为 unknown。本轮 score 是底层 BM25 的原始值，不是正确性概率；最终顺序还受已有关键词/概念等优先级影响。

| 题集 | 稳定前三条确认不变 | 确认变化 | 历史位置不足，未知 | 有效性 |
|---|---:|---:|---:|---|
| legacy-20 | 15 | 3 | 2 | 历史→本轮对比 |
| 开发集 | 22 | 3 | 5 | 历史→本轮对比 |
| 旧 24 题 | 18 | 2 | 4 | 历史→本轮对比 |
| B | 19 | 1 | 4 | 历史→本轮对比 |

## 来源与执行身份

索引在干净 `a4ba417c7bf4870c2ef9f46112b4c0fca563fbc0` 上构建，使用公开仓库来源与 `ansys-dyna-core 0.12.1` 的集成 keyword_docs 提供者。关闭私有 manual/native-input 环境配置，没有 external-sources、local-book 或私有索引。
只构建一份仓库外索引：68,286 个公开文档；命令 1,250、关键字 66,938（字段 66,900 + 无字段关键字 38）、已知问题 79、配方 15、指南 4、API **0**。提供者目录完成 3,171/3,171，原始字段记录 66,902，按已有去重规则存储 66,900。
API 原始来源仍缺失，不能用命令/配方证据冒充 API 文档；0/4（开发集 0/5）留在总分母中。一般性领域词表不覆盖的概念及指南公开来源不足也未解决。

最终重放来自 JSON 中 `actual_git_revision` 登记的干净提交。`working_tree_dirty=false`，空 diff 的 SHA256 为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；diff 范围是全部 tracked staged/unstaged 相对 HEAD，untracked 不在 diff 中。报告文件在执行结束后写入，未冒充执行时已经存在。

索引 SHA256 为 `17e57f79a18d0a7d2da4261f0817cf69db604ac1dde51c0ebb4b3d3da6f2e7fb`，大小 110,776,320 bytes。证据同时记录：产品/执行工具/测试的 Git blob 与 LF SHA256；构建输入的 revision、Git blob/LF SHA256；提供者版本和 package metadata SHA256；所有文档的稳定位置+文本哈希清单摘要，以及包含来源版本/许可的清单摘要。实际查询源位于构建 revision，工具源位于执行 revision，二者均明确登记。未保存正文、私有路径或索引文件到仓库。

## 可复跑步骤

使用同一锁定依赖集，`PYTHONPATH` 指向当前 worktree 的 `src` 和根目录。下列 `<...>` 是调用者选择的仓库外位置，不是机器路径。全量目录只需建一份索引。

```powershell
$env:PYTHONPATH="$PWD\src;$PWD"
Remove-Item Env:LSPP_MANUAL_INDEX -ErrorAction SilentlyContinue
Remove-Item Env:LSPP_NATIVE_INPUTS -ErrorAction SilentlyContinue
python -B tools/build_knowledge_index.py --all-keywords --output <public-index.sqlite>
$env:LSPP_KNOWLEDGE_INDEX='<public-index.sqlite>'
python -B tools/evaluate_knowledge.py --cases tests/data/knowledge_queries.json --output <legacy.json> --markdown <legacy.md>
python -B tools/evaluate_knowledge.py --cases tests/data/knowledge_queries.json --check-report <legacy.json> --markdown <legacy.md>
```

其余三个题集将 `--cases` 分别替换为 `knowledge_dev_queries.json`、`knowledge_holdout_queries.json`、`knowledge_holdout_b_queries.json`。`--check-report` 重新运行检索，不以汇总数字相同替代逐条引用/分数/等级校验。

本次建索引用同一库的 `repository_documents`、`keyword_fields`、`fieldless`、`build_index` 直接调用，并额外断言 public-only；上方 CLI 是等价命令，不声称为本机当时执行的原文。构建记录 JSON 使用如下字段，可在仓库外生成；`document_text_manifest_sha256` 是按 SQL `ORDER BY source_id,locator,id` 对 `[source_id,category,locator,title,version,license,sha256]` 每行紧凑 JSON + LF 累积 SHA256，名称沿用本次本地构建日志，不是单纯正文哈希。

```text
actual_git_revision, working_tree_dirty, index_sha256,
document_text_manifest_sha256,
keyword_coverage.{requested_keywords,completed_keywords,field_records,without_fields}
```

干净且已有这些构建记录时，套件工具可一次生成所有结果、来源身份和历史比较：

```powershell
python -B tools/refresh_knowledge_evidence.py --index <public-index.sqlite> --index-build-report <build-report.json> --output-dir <fresh-output-dir>
python -B -m pytest tests/test_a10_current_replay_evidence.py tests/test_knowledge_evaluation_artifacts.py tests/test_knowledge_regular_word_families.py
```

## 回归与未完成项

新增产物回归对“命中总数不变但前三条/分数/证据等级已变”、损坏的匹配标记、报告和 JSON 不一致做直接反例；在当前基线 `a4ba417` 的原评测工具上为 **8 failed / 1 control passed**，错误包括未导出 `score`/稳定引用，以及没有 `check_replay` 等检查接口。原匹配规则控制用例通过。新通用词形测试独立于 LS-PrePost 题面，覆盖 10 对规则词形双向检索及 4 个标识符负例；没有改产品实现来追分。

该测试和内部核对只验证重放记录与当前程序一致，不证明题集独立、答案忠实、原生执行或工程结果正确。缺真实来源、中文语义覆盖和新独立留出集的问题继续保留；旧报告及其首次结果仍在 [历史记录](../a10-cross-language/report.md) 中，不删失败或重写旧成绩。

当前有效的产品绑定除校验历史 blob，还检查当前工作树 LF SHA256 与 HEAD blob；未来改动检索产品代码而未重放时，校验会失败。独立小 fixture 在保存的历史身份仍自洽时修改产品文本，断言该漂移被拒绝，不伪造重绑。
