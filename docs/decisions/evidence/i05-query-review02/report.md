# Review02 I05 query identifier boundaries

Queries now share API index boundaries: split underscores first, preserve acronyms including plural IDs, then split camel case. Each original identifier is matched as `(original OR (all split words))`; separate query identifiers remain mandatory. Source text, source hashes and references are never rewritten. FTS punctuation is tokenized/quoted as data rather than executed as query operators. New indexes record identifier-parts-v2; old schema-v2 indexes stay read-only and return index_tokenization plus rebuild warnings on hits. With zero hits, the list contract remains empty and the rebuild diagnostic is logged.

On baseline 0563045 the new tests had 8 failures / 5 safety controls passed: all five partial/spaced API queries missed, underscore/acronym boundaries were wrong, split-only text did not match, and the old index gave no metadata/rebuild warning. Corrected related coverage: 90 passed. Regression names and source identities are in [evidence.json](evidence.json).

Clean execution revision: 5b2a055978e1f84dc87a0145f92ca7d6a3d5afce. Built a fresh public-only external index: 68,309 documents, 66,900 keyword field rows, 3,171/3,171 keyword catalog entries processed; API category absent. The binary index is not committed and will be removed after verification; its hash and byte count are recorded. No private manuals, local-book contents, API excerpts or private derived text are published.

| Unmodified replay set | top-3 hits | 当前有效 / 已被取代 |
|---|---:|---|
| Existing development set | 14/20 | 对登记代码与公开索引有效 |
| Existing holdout A | 16/24 | 对登记代码与公开索引有效；属于复跑，不是新盲测 |
| Existing holdout B | 13/24 | 对登记代码与公开索引有效；属于复跑，不是新盲测 |
| Old A10 ranking evidence | historical | 已被本次复跑取代，旧记录保留 |

These are actual overall denominators, including unavailable API/manual questions. They do not establish mature retrieval quality or real API recall. Remaining misses include absent API/guide sources, keyword aliases and command/recipe retrieval. No glossary or test questions were tuned to improve these numbers. I05 and A10 remain partial; new independent held-out review and authorized API sources remain gaps.

Reproduce with PYTHONPATH=src plus repository root, the locked full environment, PYTHONUTF8=1, PYTHONDONTWRITEBYTECODE=1, OPENBLAS_NUM_THREADS=1 and SQLite temp output in the dated scratch directory:

```text
python -m pytest tests/test_query_identifiers_review02.py tests/test_api_identifier_indexing.py tests/test_knowledge_index.py tests/test_knowledge_cross_language.py tests/test_knowledge_query_publication.py tests/test_knowledge_tools.py tests/test_keyword_field_lookup.py tests/test_knowledge_concept_budget_review02.py -q
python tools/build_knowledge_index.py --all-keywords --output <fresh-external-index.sqlite>
```

Set LSPP_KNOWLEDGE_INDEX to that index; run the following once per existing cases file listed in the table (knowledge_queries.json, knowledge_holdout_queries.json, knowledge_holdout_b_queries.json). Use a fresh output path and do not pass --include-private:

```text
python tools/evaluate_knowledge.py --cases tests/data/<cases-file> --output <fresh-external-replay.json>
```
