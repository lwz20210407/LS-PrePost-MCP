# A10 review02: bounded distinct concepts

The planner limits distinct Chinese concepts to 32 AFTER deduplication. Repetition does not consume the budget. Hits explicitly include concepts_truncated, concepts_total, concepts_used and concept_limit; expansion/snippet highlights describe only retained concepts. Latin requirements and explicit keyword ordering remain intact. Empty searches remain empty lists, not invented reference rows.

Coverage membership uses FTS integer rowids instead of SHA256 text document IDs, keeping temporary membership sets compact. This changes neither returned document identity nor the per-concept coverage definition on valid indexes. References remain read-only and unverified; private visibility and SQL parameters are unchanged.

| Check | Baseline 0563045 | Fixed | 当前有效 / 已被取代 |
|---|---|---|---|
| Plan/returned truncation/duplicate reporting | missing/unbounded | passed | Recorded product blobs |
| 2k-doc SQL work budget | interrupted before completion | completes below 3M VM instructions | Recorded product blobs |
| Related index/language/publication/tool suites | historical regression baseline | 57 passed | Recorded product blobs |
| 30k-doc, 200-concept/603-char query | interrupted at 60M instructions, 31.744 s; NOT completed | 19.47M instructions; 8.454 s and 3.174 s in two clean runs | Recorded product blobs |

Actual integrated clean revision: `ed0765b6aa668639d0009aac655c32170f5af9b6`; an earlier clean run is `16b00dd`. [evidence.json](evidence.json) binds planner/glossary product blobs and the regression test blob. All benchmark runs use the SAME synthetic 30k-document SQLite file (13,697,024 bytes, SHA256 recorded), without private text or corpus data. Current two-concept queries measured 3.918/1.214 s; baseline two-concept query 1.777 s. Wall time varies with host load; the unit guard uses a deterministic instruction budget, not a fragile elapsed-time assertion. The baseline long-query completion time is unknown because the deliberate work limit aborted it.

Four regressions fail on old main: excessive unique concepts, missing result truncation flags, repeated-concept metadata, and a real SQLite instruction-budget abort. The fix is not tuned on A10's evaluation questions; a synthetic glossary is injected only in isolated tests/benchmark. It does not change the committed general glossary or indexed content. No native run is involved.

```text
python -m pytest tests/test_knowledge_concept_budget_review02.py tests/test_knowledge_cross_language.py tests/test_knowledge_index.py tests/test_knowledge_query_publication.py tests/test_knowledge_tools.py -q
```

Use the shared locked environment, PYTHONPATH=src plus repository root, PYTHONDONTWRITEBYTECODE=1 and OPENBLAS_NUM_THREADS=1. Benchmark SQLite/output/temp files stay outside the repository. The benchmark schema/document generator and operation limit are retained in the external task directory; identity/timing metadata only is published.

A10 remains partial. Old f04843a evaluation results are explicitly historical; their fresh ranking replay and I05 query-side identifier tokenization are separate review items. This performance guard is not a held-out retrieval-quality or Agent answer-faithfulness score.
