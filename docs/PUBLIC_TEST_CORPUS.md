# Public development fixtures

Snapshot: 2026-10-04. Public inputs complement the private, read-only regression
models. Dataset acquisition does not count as an implemented capability or a
passed release gate. Keep original downloads and native evidence outside Git.

## Downloaded sources

| Source | Pinned revision | Acquired data | Intended coverage |
| --- | --- | --- | --- |
| [QD-CAE](https://github.com/qd-cae/qd-cae-python/tree/805e19645c2acaf8725194a0803e2e86fda7201d/test) | `805e19645c2acaf8725194a0803e2e86fda7201d` | d3plot + d3plot01, binout, four keyword files with Include structure | Shell integration points; spot-weld force histories; raw keyword/Include preservation |
| [LASSO](https://github.com/open-lasso-python/lasso-python/tree/723b93037427a6202d97f787104d29f2b696ed38/test/test_data) | `723b93037427a6202d97f787104d29f2b696ed38` | Complete checked-in beamip, node_temperature and solid_int result families | Beam integration points; thermal nodal results; solid/shell integration-point axes |
| [dynakw](https://github.com/WillemJR/dynakw/tree/HEAD/test/full_files) | Exact revision in the local download manifest/source URLs | Fourteen .k fixtures | Sets, parameters, joints, materials, sections; parser fixtures, not certified solve-ready models |
| [UMAT_2scale_LSDYNA](https://github.com/DataAnalyticsEngineering/UMAT_2scale_LSDYNA/tree/HEAD/repo_files/examples/analytical_mat_parameter) | Exact revision in the local download manifest/source URLs | Six .key files | Thermal/coupled Include structures; retained for review only pending license applicability assessment |
| [Ansys example-data](https://github.com/ansys/example-data/tree/c0bdfaf25b0dd0ca1bc2e952b48e408c6223b8a7/ls-dyna) | `c0bdfaf25b0dd0ca1bc2e952b48e408c6223b8a7` | Beer-can, John Reid pendulum and pipe mesh decks | General shell/mesh/part/selection tests, beyond the existing projectile deletion fixture |

The acquisition contains 62 files, including five license texts: 27 keyword
files and 30 result-family/binout files (file count is not case count).
Each downloaded Git blob was checked against its upstream blob hash; the
local manifests also record SHA-256, byte count and immutable source URL.

QD-CAE and LASSO license texts contain BSD three-clause terms; dynakw and
Ansys example-data use MIT. UMAT_2scale's license includes an additional
geographic/company-use clause: do not treat it as ordinary BSD or import its
code/assets into this project without resolving applicability. Downloading
a fixture does not authorize executing scripts contained alongside it.

## Native loading evidence

The following loaded successfully through the repository's persistent GUI
service in maximized LS-PrePost 4.13.4, embedded Python 3.10.18. Counts were
read back from the application; these are loading/inventory checks, not full
numerical or solver acceptance.

| Fixture | Nodes | Elements | Native states |
| --- | ---: | ---: | ---: |
| QD shell result | 4915 | 4696 | 1 |
| LASSO beamip | 2 | 1 | 2 |
| LASSO node_temperature | 2185 | 2075 | 23 |
| LASSO solid_int | 106 | 32 | 22 |
| Beer-can mesh | 3437 | 3320 | 1 |
| Pendulum mesh | 784 | 776 | 1 |
| Pipe mesh | 2049 | 1704 | 1 |

LASSO independently read the four result families with matching state counts.
Stored shapes include beam axial stress `(2,1,4)`, temperature `(23,2185)`,
solid stress `(22,16,8,6)`, and shell stress `(22,16,5,6)` in solid_int.
The QD binout contains `swforc`; it must not be advertised as a global-energy
fixture. The keyword-only mesh decks do not contain solved time histories.

Local evidence folders, under the current dated task's `public-corpus`:

- `native-open-8789c926aa3a483b8caaee654087f033`: four result opens and session closure.
- `native-open-a75c362792f64f2694804660f0b8176a`: three keyword opens and session closure.
- `download-manifest.json`, `keyword-download-manifest.json`, `reader-inventory.json`.

## Additional verified sources awaiting acquisition

[DYNAmore's example collection](https://www.dynaexamples.com/) provides public
educational input downloads. Candidate cases are
[Lobatto shell bending](https://www.dynaexamples.com/introduction/examples-manual/section/shell-2),
[solid hourglassing](https://www.dynaexamples.com/introduction/examples-manual/section/solid),
[tied/automatic contact](https://www.dynaexamples.com/introduction/intro-by-k.-weimar/contact/contact-iii),
and [prescribed motion/loading](https://www.dynaexamples.com/introduction/examples-manual/load/presrcibed).
Their pages were verified, but direct acquisition timed out in this session;
do not report those four decks as downloaded. Public access is not a blanket
redistribution license. Educational parameters are not physical reference truth.

[GMU CCSA vehicle models](https://www.ccsa.gmu.edu/models/) are candidates for
large assembly/Include stress tests. No vehicle archive was acquired or tested
in this session. Review download terms and size before selection.

## Next regression uses

1. Cross-check stored integration-point indices and user IDs against native
   extraction on the LASSO beam and mixed solid/shell fixtures.
2. Extend field extraction coverage to the temperature fixture and history
   inspection to QD `swforc`; do not infer absent variables.
3. Apply selection-to-set, pressure/constraint creation and native reopening
   to isolated copies of the general mesh decks.
4. Use parser fixtures for text/Include preservation and expected rejection
   tests; use a complete engineering deck for subsequent native acceptance.
5. Retain the existing projectile case specifically for per-state deletion
   semantics, while adding other element domains as suitable results appear.
