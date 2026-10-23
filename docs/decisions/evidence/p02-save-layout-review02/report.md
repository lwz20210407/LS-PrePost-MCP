# Review02 P02/P11 save layout and template warnings (pending native rerun)

Source paths inside a relative save layout are checked for symlink/junction/reparse points before resolving physical layout and before writing the output tree. This avoids copying lib/x.k under real_lib while leaving a raw lib/x.k reference, and rejects the link before physical commonpath can fail across volumes. A common directory alias outside the relative layout is not recreated as an internal link. No link is removed or materialized and source bytes are unchanged.

Input preflight warnings now survive save_model. A comment-form unresolved template such as ${GEOMETRY} keeps its actual lexer meaning (an empty INCLUDE), but a count-preserving save returns partial with template_inputs_resolved=missing rather than a clean pass. Ordinary explicitly disabled INCLUDE comments remain allowed with a visible warning. Saved-tree reload errors still fail as before. No parallel INCLUDE parser was added.

| Evidence | Result | 当前有效 / 已被取代 |
|---|---|---|
| Baseline 0563045 linked layout cases | 4 failed | 历史真实失败；物理解析顺序用受控探针覆盖 |
| Baseline 0563045 lost template warning | 1 failed | 历史真实失败 |
| Clean 208c7e4 related unit tests | 84 passed | 仅当前 L1 |
| Fresh 4.13/4.10 raw-tree reopen | pending | 未运行，不宣称通过 |

[evidence.json](evidence.json) binds unit revision/product blobs and baseline output hashes. The old native evidence remains scoped to its old product blobs; the strict evidence guard is intentionally not bypassed. Both versions now have a prepared additional native placeholder case (12 tests per version, including search-path cases). Run these serially after the ongoing I04 lease is released, then append new reports/proofs before Ready/CI integration. P11 is temporarily L1 for this changed implementation; no acceptance is removed.

Reproduce unit regressions with python -m pytest tests/test_save_link_layout_review02.py tests/test_save_preflight_warnings_review02.py tests/test_save_include_resolution_review02.py tests/test_save_search_paths.py tests/test_keyword_absolute_save.py tests/test_save_model.py tests/test_keyword_engine.py -q. Use the shared locked environment and dated external basetemp/cache. Native follow-up: python -m pytest tests/test_save_model_native.py tests/test_save_search_paths_native.py -m native --run-native --native-strict --native-executable <version-executable> --native-output <fresh-external-directory> -q.
