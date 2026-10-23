# Review02 I06 current issues and historical reference separation

KNOWN_ISSUES now lists current limits/native boundaries with task references; the raw capability dump, driver scan/hash lists and resolved journal records are retained in a historical snapshot with original revision/blob/LF-hash provenance. Relative links were rebased; important earlier failure records were not discarded. Current guidance corrects the v1 tokenizer statement, previous path refusals, source-guard wording and the 11 product Include variants mislabeled as input restrictions. The focused native rerun is still in progress; its final report will update I04 separately.

Baseline 0563045: three regressions failed (capability dump duplicated; current tokenizer missing; issue sections lacked task IDs). Corrected documentation and knowledge-related tests: 30 passed; all local links and Ruff passed. Existing tests for early path failures now inspect the historical snapshot, while current tests check the remaining unsupported paths instead of preserving an obsolete refusal as current behavior.

| Replay on the rebuilt public index | top-3 | 当前有效 / 已被取代 |
|---|---:|---|
| Existing development set | 14/20 | 对登记来源有效 |
| Existing holdout A | 15/24 | 当前来源复跑；HI02 的已修 KI-052 已移出当前目录 |
| Existing holdout B | 13/24 | 对登记来源有效 |
| Previous active-issue index | 102 known-issue records | 已被78条当前条目的索引取代；旧证据保留 |

The rebuilt external public index has 68,285 documents, 66,900 keyword fields and no private API sources. The 15/24 denominator includes the resolved historical question; the questions/glossary were not changed or tuned. The missing archived question is disclosed, not silently removed from evaluation. No claim of improved blind quality is made. Index and source hashes/revisions are in [evidence.json](evidence.json); the external index is disposable after CI and replay verification.

Initial execution revision b4bbad0e0a617db22193aea4c2a209101133bf88; final clarified KI-049 source was rebuilt and replayed cleanly on d01d61b50b16c1a38f854d1dfa71ccb7cc239f6b with the same denominators/results. Previous capture is retained in evidence.json. No native/solver test ran for this documentation change. Rebuild user-managed indexes explicitly when deploying updated documentation sources; this PR does not rewrite any private external index. Multi-AI AGENTS history is unchanged.
