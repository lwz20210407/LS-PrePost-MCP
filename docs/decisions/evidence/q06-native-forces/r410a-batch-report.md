# Q06 r410a: independent native force curves

Actual Git revision: `c12b2d693ef1d6f713e5dac98fdfe8d06a04baf1`; clean tracked tree.

7 passed / 0 failed. Serial -nographics batch only.

| Case | Expected tool status | Native curves | Checked samples | Maximum value error |
|---|---|---:|---:|---:|
| rcforc-x_force | succeeded | 2 | 242 | 3.792999994089996e-07 |
| rcforc-y_force | succeeded | 2 | 242 | 1.6619999954059494e-07 |
| rcforc-z_force | succeeded | 2 | 242 | 2.8319999955783715e-05 |
| secforc-x_force | succeeded | 1 | 250 | 2.919999997352818e-08 |
| secforc-y_force | succeeded | 1 | 250 | 1.6730000024223202e-09 |
| secforc-z_force | succeeded | 1 | 250 | 1.1830000001822327e-07 |
| secforc-z_force-wrong-component | failed | negative | - | - |

Six positive cases check RCFORC x/y/z on both slave/main sides and SECFORC x/y/z. One negative deliberately executes native x while requesting z: the native process succeeds, the tool rejects the mismatch and returns no verified reader artifact. Reader values are never overwritten with native output.
Each version checks 1476 positive time/value pairs (2952 across the two versions). Time and values have separate tolerances: time rtol=1e-6/atol=1e-9, value rtol=2e-5/atol=1e-6 in declared source units. Every original input SHA256 matches the external public corpus manifest, and bytes plus directory inventories remain unchanged.
Raw source copies, sample CSV/XY files, native logs and private absolute paths remain outside Git.
