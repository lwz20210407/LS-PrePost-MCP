# G04 r410b: headless entity identification

Actual Git revision: `2b81ae38dab3be05d9d57b065c9f104047249dce`; clean working tree.

3 passed / 0 failed.

| Case | Test status | Query status | Nodes compared | Native jobs | Result absolute error |
|---|---|---|---:|---:|---:|
| keyword-include | passed | succeeded | 4 | 2 | None |
| public-solid | passed | partial | 10 | 3 | 0.0 |
| public-shell | passed | partial | 10 | 3 | 0.0 |

All native processes are serial headless batch. No GUI, UU or solver.
The Include keyword fixture uses blank coordinate fields and a multi-line ELEMENT_SHELL_THICKNESS. Reference coordinates and connectivity independently match native DataCenter. Public solid stress matches Q03 and native SCL; public shell nodal displacement matches native SCL. No shell stored-point/layer mapping is inferred.
Each public result file hash matches the external corpus manifest before execution; all source bytes and directory inventories remained unchanged. Binary material/section user IDs remain null, with partial query status; this does not change a correct native comparison into full G04 acceptance. Keyword material/section links are checked against the fixture, not independently queried from native DataCenter.
Raw model copies, samples, native logs and local absolute paths remain outside Git.
