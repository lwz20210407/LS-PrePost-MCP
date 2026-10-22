# P11 sp413a: search-path tree save/reopen

Actual Git revision: `ea7d0288b7849808fd220e21acdc5b229933652f`; working tree clean.

4 passed / 0 failed. Four source cases: relative INCLUDE_PATH, main-file INCLUDE_PATH_RELATIVE,
an unused upward search directory, and a material edit followed by save/reopen.

| Case | Status | Native jobs | Nodes | Elements | Source unchanged |
|---|---|---:|---:|---:|---|
| edited-search | succeeded | 2 | 4 | 1 | True |
| relative-search | succeeded | 2 | 4 | 1 | True |
| search | succeeded | 2 | 4 | 1 | True |
| unused-search | succeeded | 2 | 4 | 1 | True |

All eight processes used -nographics, returned zero and did not time out.
Each saved tree passed shared preflight with no missing search directory. Native counts and Part IDs
were checked before/after reopen by save_model. Untouched keyword bytes were copied by the shared engine.
This does not certify Transform, opaque includes, parameterized filenames, nested relative path directives,
GUI unsaved edits or the 4.8 Python runtime. Raw paths/logs and generated input decks remain outside Git.
