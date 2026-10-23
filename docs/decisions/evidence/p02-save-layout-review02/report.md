# Review02 P02/P11 save layout and template warnings 

Source paths inside a relative save layout are checked for symlink/junction/reparse points before resolving physical layout and before writing the output tree. This avoids copying lib/x.k under real_lib while leaving a raw lib/x.k reference, and rejects the link before physical commonpath can fail across volumes. A common directory alias outside the relative layout is not recreated as an internal link. No link is removed or materialized and source bytes are unchanged.

Input preflight warnings now survive save_model. A comment-form unresolved template such as ${GEOMETRY} keeps its actual lexer meaning (an empty INCLUDE), but a count-preserving save returns partial with template_inputs_resolved=missing rather than a clean pass. Ordinary explicitly disabled INCLUDE comments remain allowed with a visible warning. Saved-tree reload errors still fail as before. No parallel INCLUDE parser was added.

| Evidence | Result | 当前有效 / 已被取代 |
|---|---|---|
| Baseline 0563045 linked layout cases | 4 failed | 历史真实失败；物理解析顺序用受控探针覆盖 |
| Baseline 0563045 lost template warning | 1 failed | 历史真实失败 |
| Clean 208c7e4 related unit tests | 84 passed | 仅当前 L1 |
| Fresh 4.13/4.10 raw-tree reopen | 12 passed each | 对登记产品 blob 有效 |

[evidence.json](evidence.json) binds clean unit revision 208c7e4/product blobs and baseline stdout hashes. Fresh clean native execution e3b42fb has 12 passed on each version, including an expected partial template result. [Reports and product blobs](../p11-raw-review02/report.md) replace the prior evidence as the active source-bound records; all previous failures and captures remain. P11 is partial/L2 only for this registered subset; link materialization, GUI/4.8 and solver physics remain unverified.

Reproduce unit regressions with python -m pytest tests/test_save_link_layout_review02.py tests/test_save_preflight_warnings_review02.py tests/test_save_include_resolution_review02.py tests/test_save_search_paths.py tests/test_keyword_absolute_save.py tests/test_save_model.py tests/test_keyword_engine.py -q. Use the shared locked environment and dated external basetemp/cache. Native follow-up: python -m pytest tests/test_save_model_native.py tests/test_save_search_paths_native.py -m native --run-native --native-strict --native-executable <version-executable> --native-output <fresh-external-directory> -q.

