# Q05 r413b: real history comparison

Actual Git revision: `6be5764c5ef8af7119e917a8d8062365fbc1de12`; clean working tree.

2 passed / 0 failed. Serial -nographics processes; no GUI, UU or solver.

| Domain | Source | Curves | Total samples | Native jobs | Value error |
|---|---|---:|---:|---:|---:|
| global | binout | 1 | 3201 | 1 | 0.0002416058860035264 |
| part | binout | 2 | 6402 | 2 | 9.073298627981785e-07 |

Node/solid histories use the registered solid_d3plot. Part/global histories use the registered qd-cae LSDA binout.
Every original file-family SHA256 matches its external public manifest before the run; all source bytes and directory inventories remained unchanged.
LASSO curves are independently compared against real SCL output by every requested user ID and sample. Native values never replace reader values.
The first complete runs preceded tightening the binout time tolerance; the later Part/global runs recheck that changed branch with separate time/value tolerances.
Time tolerance: rtol=1e-6, atol=1e-9 in declared source time units; value tolerance: rtol=2e-5, atol=1e-6 in declared source value units.
Old max_absolute_error used the maximum over both columns for binout; new runs report value/time errors separately. No unit conversion is implied.
Raw CSV samples, binaries, logs and local absolute paths stay outside Git.
