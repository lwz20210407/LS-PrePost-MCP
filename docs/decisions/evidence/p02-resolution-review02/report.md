# Review02 P1-1: Include relocation uses the winning rule

An Include is external only when its actual resolution is absolute, or when it was resolved through an absolute search directory already active at that card. Resolution records both the winning search directory and its index in the active list. An unused or later absolute path card cannot turn a local reference into an external dependency.

A source referenced both locally and externally retains its external reference AND gets the unchanged local copy required by the relative spelling. This also applies to relative descendants of a dual-referenced parent. Editing a genuinely external dependency is still refused before writing, preventing a disconnected edited copy; this limitation is unchanged.

| Regression | Baseline 0563045 | Fixed | 当前有效 / 已被取代 |
|---|---|---|---|
| Later absolute path, untouched child | Missing saved child | passed | Recorded product blobs |
| Later absolute path, edited child | Misleading absolute-dependency refusal | passed | Recorded product blobs |
| lib/x.k and absolute search x.k | Dangling lib/x.k | passed | Recorded product blobs |
| Winning search-directory provenance | Attribute absent | passed | Recorded product blobs |
| Dual parent with relative leaf | Dangling local subtree | passed | Recorded product blobs |

Actual clean execution: `a03515f724e9820e02d27a10beae790cdc6c9787`; [evidence.json](evidence.json) binds three product blobs and the test blob. Five new regressions fail on the old main, all five pass after the fix, and the related save/access/preflight/model-tool suite is 82 passed. Source bytes remain unchanged in the regression fixtures. No LS-PrePost or solver execution is claimed; P11's raw native-reopen issue is tracked separately under review02 P1-3. P02 remains partial.

```text
python -m pytest tests/test_save_include_resolution_review02.py tests/test_keyword_absolute_save.py tests/test_save_search_paths.py tests/test_model_tools_include_confinement.py tests/test_keyword_engine_preflight.py tests/test_keyword_engine_preflight_limit.py tests/test_model_target_tools.py -q
```

Use the locked shared full environment, PYTHONPATH=src plus repository root and PYTHONDONTWRITEBYTECODE=1; test output is confined to an owned temporary directory.
