# G04 r413a: headless entity identification

Actual Git revision: `60edd973e852b51432c40e8b2447bdc7707b52db`; clean working tree.

1 passed / 2 failed.

| Case | Test status | Query status | Nodes compared | Native jobs | Result absolute error |
|---|---|---|---:|---:|---:|
| keyword-include | passed | succeeded | 4 | 2 | None |
| public-solid | failed | not completed | - | - | - |
| public-shell | failed | not completed | - | - | - |

All native processes are serial headless batch. No GUI, UU or solver.
The initial public result tests failed before native field launch: the test adapter used reader names (sxx/displacement_z) instead of native names (stress_x/disp_z). Geometry assertions had run, but these cases are retained as failed, not as complete numerical verification.
Raw model copies, samples, native logs and local absolute paths remain outside Git.
