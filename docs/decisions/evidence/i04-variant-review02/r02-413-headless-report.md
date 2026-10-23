# I04 review02 focused native run and frozen ledger

Actual clean Git revision: `046b512ea424f9fd08a2c01072744a24d0e6f174`; tracked diff SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
This is a focused 15-case rerun, not a clean-head rerun of all 100 cases.

Focused run: 3 passed / 12 failed. Eleven failures are legal product-unsupported Include variants;
all eleven completed an independent raw native read, then remain failed product round trips.
025/063/082 passed complete native save/reopen; 010 still fails saved reload parameter checks.
All source file/tree bytes and recursive directory inventories stayed unchanged.

The original recorded 45 passed / 5 failed / 50 evidence_only are retained as historical facts.
Correct historical interpretation: 45 passed / 16 failed or product gaps / 39 true input limits (45/61 runnable).
Latest frozen ledger: 48 passed / 13 failed / 39 input limits, combining this focused run with historical records.
The 85 cases not rerun keep their actual old revisions and are not new acceptance evidence.

| Case | Historical | Corrected historical | Latest | Revision | 当前有效 / 已被取代 |
|---|---|---|---|---|---|
| extra-keyword-001 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-002 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-003 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-004 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-005 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-006 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-007 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-008 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-009 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-010 | failed | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-011 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-012 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-013 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-014 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-015 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-016 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-017 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-018 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-019 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-020 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-021 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-022 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-023 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-024 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-025 | failed | failed | passed | 046b512 | focused_review02_rerun |
| extra-keyword-026 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-027 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-028 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-029 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-030 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-031 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-032 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-033 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-034 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-035 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-036 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-037 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-038 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-039 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-040 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-041 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-042 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-043 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-044 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-045 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-046 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-047 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-048 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-049 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-050 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-051 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-052 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-053 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-054 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-055 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-056 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-057 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-058 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-059 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-060 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-061 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-062 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-063 | failed | failed | passed | 046b512 | focused_review02_rerun |
| extra-keyword-064 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-065 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-066 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-067 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-068 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-069 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-070 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-071 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-072 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-073 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-074 | evidence_only | failed | failed | 046b512 | focused_review02_rerun |
| extra-keyword-075 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-076 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-077 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-078 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-079 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-keyword-080 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-081 | evidence_only | input_limited | input_limited | c46bb9d | historical_only_not_rerun |
| extra-keyword-082 | failed | failed | passed | 046b512 | focused_review02_rerun |
| extra-keyword-083 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-01 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-02 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-03 | failed | failed | failed | c46bb9d | historical_only_not_rerun |
| extra-result-04 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-05 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-06 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-07 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-08 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-09 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-10 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-11 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-12 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-13 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-14 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-15 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-16 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
| extra-result-17 | passed | passed | passed | c46bb9d | historical_only_not_rerun |
