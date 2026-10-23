# Q03 r413b: native six-component field checks

Actual Git revision: `1be3f454544d6aab64867722cf66075f555d0ec5`; clean working tree.

8 passed / 0 failed tests. Expected failure jobs are not native export failures.

| Case | Expected job | Observed job | Test | Tensor shape | Stored point |
|---|---|---|---|---|---|
| public-shell-inner | succeeded | succeeded | passed | [8, 6] | 2 |
| public-shell-mid | succeeded | succeeded | passed | [8, 6] | 1 |
| public-shell-outer | succeeded | succeeded | passed | [8, 6] | 5 |
| public-shell-wrong-inner | failed | failed | passed | [8, 6] | 1 |
| public-shell-wrong-mid | failed | failed | passed | [8, 6] | 3 |
| public-solid | succeeded | succeeded | passed | [548, 6] | None |
| synthetic-shell | succeeded | succeeded | passed | [4, 6] | None |
| synthetic-solid | succeeded | succeeded | passed | [4, 6] | None |

Each case used one real SCL/native export in -nographics mode; all input-family bytes and source-directory listings were unchanged.
Positive cases round-trip both CSV and NPZ through the shared field reader. Native values are compared by state/time/user ID and all six components;
they never replace LASSO values. Public solid compares every one of 548 entities; each public shell selection compares eight entities.
For this public shell file only, MID agrees with stored slot 1, INNER with slot 2, OUTER with slot 5. This is not a general layer-order mapping.
The first run retained one long-line SCL compilation failure and two failed tests with incorrectly assumed slot/depth equivalence.
Later runs explicitly select both reader slot and native layer, including two deliberate mismatch rejections. No GUI/UU/solver was used.
