# Review02 P1-5: shared expression format (not yet accepted)

The code uses one typed-name separator rule for PARAMETER_EXPRESSION: function-argument commas remain in the expression suffix. Named prmr/expression row fields preserve that whole suffix; expression edits use the same whitelisted evaluator and type checks before mutation. Model checks use the same format rule, avoiding a false free_format_item_too_long defect. Ordinary data-card comma semantics remain unchanged. Long/i10 forms are not newly certified.

| Check | Result | 当前有效 / 已被取代 |
|---|---|---|
| Baseline 0563045 functional regressions | 5 failed / 1 passed control | Retained failure; no native startup issue counted as a code failure |
| Related evaluation/layout/format/model-operation tests | 124 passed | Recorded product blobs |
| R11 fixed/free solver attempts | 2 failed: both startup timeouts | Does not establish expression acceptance or rejection |
| Bare input/no expression/no Job Object/hidden console controls | Startup timeouts, no result files | Environment startup not resolved |

Clean code revision `f932d27abfbd8cac0dbd25ae8cf56d6970d33a91`; [evidence.json](evidence.json) retains the two real failed solver attempts and bounded controls. Each solver process used LSTC_LICENSE=ANSYS, ncpu=1, memory=20m and was reaped after timeout. A zero exit code resulting from Windows termination is NOT accepted as solver success. The startup banner alone is not solver-side semantic evidence.

The user requested other review issues first, so solver investigation is deferred. P1-5 is not closed. This branch is Draft and must refresh the independent title oracle and active raw-save evidence for changed shared modules before Ready/CI integration. No task acceptance or release requirement was relaxed, and no raw solver log/host path/configuration is published.

```text
python -m pytest tests/test_expression_format_review02.py tests/test_parameter_expression_commas.py tests/test_keyword_engine_solver_rules.py tests/test_keyword_engine_parameters.py tests/test_keyword_engine.py tests/test_keyword_engine_tables.py tests/test_keyword_engine_formats.py tests/test_keyword_engine_long.py tests/test_keyword_engine_operations.py -q
```

The opt-in solver test additionally requires LSPP_SOLVER_EXECUTABLE. Do not repeat it while startup is unresolved; --run-native is mandatory. Current production main does not include this Draft's format change.
