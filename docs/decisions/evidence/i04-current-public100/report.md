# I04: current canonical-save public-100 run

Actual Git revision: `c46bb9d41ecdad2d055638c93d70a5d1d5d84bbe`; working tree clean. LS-PrePost 4.13, serial headless batch.

45 passed / 5 failed / 50 input restrictions (evidence_only). All 100 registered input trees and
source-directory name inventories were unchanged. No GUI or remote-disconnection test was run.

The previous clean 53f6072 run had 16 passed / 45 failed / 39 input restrictions.
Per-case transitions: 16 retained passes, 29 failures now passed, 5 retained failures,
39 retained input restrictions, and 11 former failures now explicitly classified as input restrictions.
Reclassification is not a functional fix; the checks also changed to canonical save_model and full node comparison.

Remaining executed failures: three large search-path models rejected at save admission (025/063/082),
unresolved saved-tree parameter warnings (010), and invalid reader EOF time (result-03).
The search-path repair and its small native fixtures are separate evidence; this historical run is not rewritten.

Keyword scope: native read, raw-preserving tree save/reopen, counts/Part IDs and all returned node IDs/coordinates.
Result scope varies by case: native/reader count/time/displacement checks, or existing database extraction checks.
This is not certification of every keyword card or result quantity. Raw reports/logs/decks stay outside Git.

| Case | Previous | Current | Limitation / failure |
|---|---|---|---|
| extra-keyword-001 | evidence_only | evidence_only | 输入限制：input_unreadable |
| extra-keyword-002 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-003 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-004 | failed | passed |  |
| extra-keyword-005 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-006 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-007 | failed | passed |  |
| extra-keyword-008 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-009 | failed | passed |  |
| extra-keyword-010 | failed | failed | unresolved_parameter_warnings_on_saved_reload |
| extra-keyword-011 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-012 | failed | passed |  |
| extra-keyword-013 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-014 | failed | passed |  |
| extra-keyword-015 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-016 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-017 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-018 | failed | passed |  |
| extra-keyword-019 | failed | passed |  |
| extra-keyword-020 | evidence_only | evidence_only | 输入限制：input_unreadable |
| extra-keyword-021 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-022 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-023 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-024 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-025 | failed | failed | save_model_legacy_search_path_admission |
| extra-keyword-026 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-027 | failed | passed |  |
| extra-keyword-028 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-029 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-030 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-031 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-032 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-033 | failed | passed |  |
| extra-keyword-034 | failed | passed |  |
| extra-keyword-035 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-036 | evidence_only | evidence_only | 输入限制：input_unreadable |
| extra-keyword-037 | failed | passed |  |
| extra-keyword-038 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-039 | failed | passed |  |
| extra-keyword-040 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-041 | failed | passed |  |
| extra-keyword-042 | failed | passed |  |
| extra-keyword-043 | failed | passed |  |
| extra-keyword-044 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-045 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-046 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-047 | evidence_only | evidence_only | 输入限制：input_unreadable |
| extra-keyword-048 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-049 | failed | passed |  |
| extra-keyword-050 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-051 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-052 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-053 | failed | passed |  |
| extra-keyword-054 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-055 | failed | passed |  |
| extra-keyword-056 | failed | passed |  |
| extra-keyword-057 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-058 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-059 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-060 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-061 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-062 | failed | passed |  |
| extra-keyword-063 | failed | failed | save_model_legacy_search_path_admission |
| extra-keyword-064 | failed | passed |  |
| extra-keyword-065 | failed | passed |  |
| extra-keyword-066 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-067 | failed | passed |  |
| extra-keyword-068 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-069 | failed | passed |  |
| extra-keyword-070 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-071 | failed | passed |  |
| extra-keyword-072 | failed | passed |  |
| extra-keyword-073 | failed | passed |  |
| extra-keyword-074 | failed | evidence_only | 输入限制：unsupported_native_include_variant |
| extra-keyword-075 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-076 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-077 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-078 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-079 | failed | passed |  |
| extra-keyword-080 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-081 | evidence_only | evidence_only | 输入限制：input_not_found |
| extra-keyword-082 | failed | failed | save_model_legacy_search_path_admission |
| extra-keyword-083 | failed | passed |  |
| extra-result-01 | passed | passed |  |
| extra-result-02 | passed | passed |  |
| extra-result-03 | failed | failed | reader_rejected_invalid_eof_state_time |
| extra-result-04 | passed | passed |  |
| extra-result-05 | passed | passed |  |
| extra-result-06 | passed | passed |  |
| extra-result-07 | passed | passed |  |
| extra-result-08 | passed | passed |  |
| extra-result-09 | passed | passed |  |
| extra-result-10 | passed | passed |  |
| extra-result-11 | passed | passed |  |
| extra-result-12 | passed | passed |  |
| extra-result-13 | passed | passed |  |
| extra-result-14 | passed | passed |  |
| extra-result-15 | passed | passed |  |
| extra-result-16 | passed | passed |  |
| extra-result-17 | passed | passed |  |
