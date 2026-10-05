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

## Additional acquired history fixture (2026-10-04)

[saudbinayed/binout](https://github.com/saudbinayed/binout) supplies an MIT-licensed
plane-strain example at pinned commit `345d6997514059baf0c4e1f0608dafef9c43ee7d`.
Five files were fetched locally: license, sample README, `plane_strain_impact.k`,
root `d3plot` and the81,205,008-byte `binout`. Exact size, upstream Git blob SHA1
and local SHA256 were checked. No upstream executable script was run.

Read-only LASSO inventory confirms `elout`, `glstat`, `matsum`, `ncforc`, `nodout`.
The sample README's `rcforc` wording does not match the actual `ncforc` branch.
ELOUT/shell, GLSTAT, MATSUM and NODOUT have138 finite, strictly increasing time
samples; ELOUT shell IDs are a138×4200 per-state array, so a fixed one-dimensional
ID mapping cannot be assumed. NCFORC has master/slave subbranches.

The upstream **root d3plot is mesh/control data only**, not a complete solved
state family. Use the binout for the database-panel audit; do not use this root
file to claim animation or d3plot time-history completeness. Native4.13.4 opening,
UI inspection, curve extraction and numerical cross-checks of this new fixture
remain separate acceptance work. On2026-10-05, the visible4.13.4 Binout panel loaded
the file and exposed all five branches; GLSTAT/MATSUM/NCFORC master/slave/NODOUT/
ELOUT-shell panels were captured. No extracted numeric curve is certified by this
UI inventory. Local data/manifest are retained under the dated task's
`ui-audit/public-history-corpus/saudbinayed-binout`; binaries are not committed.

## Official expansion and actual loading checks (2026-10-05)

Ten additional fixture groups were acquired locally: six Ansys groups (about
31.6 MB of original payloads) plus four educational keyword cases from Ansys's
official mirror of the DYNA examples. Raw data, pages, archives and logs remain
outside Git; fixed-commit URLs, archive members, sizes and SHA256 are in the
local `ui-audit/official-corpus` manifests.

| Source / fixture | Actual acquisition | New native4.13.4 inventory check |
| --- | --- | --- |
| [Ansys general d3plot](https://github.com/ansys/example-data/tree/c0bdfaf25b0dd0ca1bc2e952b48e408c6223b8a7/result_files/d3plot) | d3plot+01+02 and actunits |1065nodes,548elements,22states; node page and native viewport PNG |
| Ansys beam result family; exact pinned paths in local manifest | d3plot+01+02 and actunits |1940nodes,2056elements,12states; includes1512solids and544beams per independent inventory |
| [Official composite/SPH bird example](https://composites.dpf.docs.pyansys.com/version/stable/examples/gallery_examples/016_lsdyna_bird_strike.html) | input.k, MatML.xml, d3plot+01+02 | Result inventory2957nodes,3005elements,3states and native PNG; keyword transition **not accepted**, see below |
| [Official Binout examples](https://dpf.docs.pyansys.com/version/0.16/examples/14-lsdyna/00-lsdyna_operators.html) | Separate binout_glstat and binout_matsum | Native checks pending; LASSO inventory below |
| [Thermal flow](https://lsdyna.ansys.com/thermal-flow/) | ZIP withi.k+mesh.k | Input only, native check pending; no solved data supplied |
| [Uncoupled welding](https://lsdyna.ansys.com/uncoupled-d3plot/) | ZIP with3keyword files | Input only, native check pending; required thermalstep.d3plot absent |
| [Lobatto shell](https://lsdyna.ansys.com/shell-2-d44/) | ZIP/fullk |93nodes,60elements,1state; native open/page/view |
| [Solid hourglass](https://lsdyna.ansys.com/solid-d66/) | ZIP/fullk |529nodes,322elements,1state; native open/page/view |
| [Contact III](https://lsdyna.ansys.com/contact-iii/) | ZIP/fullk |46nodes,29elements,1state; native open/page/view |
| [Prescribed motion](https://lsdyna.ansys.com/presrcibed/) | ZIP/fullk |1437nodes,1313elements,1state; native open/page/view |

The three result inventories and four keyword loads are **seven opening/viewport
smoke checks, not seven full preprocessing/postprocessing workflows**. Source
hashes remained unchanged. The keyword-only checks used a separate owned
maximized GUI, reviewed per-load native logs and closed only that owned process.
The original menu-audit instance was preserved. No solver was run.

Read-only LASSO inventory confirms `binout_glstat` contains `glstat` and `rwforc`;
GLSTAT has251times. `binout_matsum` has12branches: `abstat`, `deforc`, `elout`,
`glstat`, `jntforc`, `matsum`, `nodout`, `rbdout`, `rcforc`, `sbtout`, `secforc`,
`sleout`. Sampling frequencies differ by branch; never zip these histories by
row number or treat the two named files as one MPP family.

Two important failures were retained:

1. Opening the bird keyword after its result produced native `Prog Error`,
   while the API reported success with the previous3-state inventory. Independent
   review rejects that keyword test and marks the owned session uncertain.
2. LASSO warned of shell-variable-count mismatch and failed to reshape the
   composite plastic-strain tensor. Matching node/state counts do not certify
   those result arrays. See [audit findings](UI_AUDIT_POST_GAPS.md).

The six Ansys groups' Git assets retain upstreamMIT licensing; website input
headers can impose non-commercial-copy conditions. Official mirrors are public
educational downloads, not automaticallyMIT. Keep original notices and do not
redistribute these datasets in this repository.

Local evidence: `official-corpus/ansys/manifest.json`,
`official-corpus/dynaexamples-official-mirror/manifest.json`, and dated task
subdirectories `nv-7f4f588e` (including independent-review.json) and
`nk-10fb52dc`. The first long-path failure remains separately preserved.

## Broader official input and LS-PrePost tutorial corpus

The next acquisition adds20 distinct official input entry points in17 unique
ZIP archives (21,649,316 bytes downloaded;79keyword texts). Shared implicit
packages were downloaded once. Cases include planar/revolute/screw joints,
extra-node rigid bodies, CNRB, shell-solid coupling, spot/butt welds, gravity,
discrete springs, prescribed motion, Node/Part/Shell/Segment sets, thermal
contact, coupled thermal models, moving rigid walls, implicit/restart and
parameter/Include structures. Original notices and complete package directories
are preserved; scanned direct Includes resolve, but restart/dump/thermal result
dependencies are not thereby certified. Three package `dynain.lsda` files are
explicitly dummy/fake placeholders and **excluded from solved result counts**.
Exact official pages, hashes and suggested entry points are in the local
`official-corpus/ansys-expansion` manifest and capability-map.csv.

Nine official LS-PrePost tutorial ZIPs were also acquired: Element Editing,
ElGen, Curves/Surfaces, Block Mesher, Force–Displacement, Post Tools,
Occupant Injury, XYPlot and Animation. These contain12files:5keyword decks,
2IGES files,2ASCII histories,2CRV files and1old binary result. NODOUT/RCFORC
and bothCRV have121times; NODOUT's translation/rotation blocks must not be
counted as242states. Contact2 in the tutorial RCFORC explicitly has undefined
resultants, not valid zero forces. The old animation binary passed ZIP CRC
but failed LASSO decoding; native compatibility remains unverified. The official
SCL archive returned403 and was not counted as acquired.

An additional [official GENEX sample](https://lsdyna.ansys.com/download-more-examples/)
provides `sample_glstat`, `sample_nodout`, `sample_rwforc` and `sample_d3hsp`
from one case. This is one new ASCII case, not four. The original tar.gz passed
CRC and members were hashed; native extraction remains pending.

These inputs support the ongoing menu/handbook gap audit and later functional
tests. Acquisition does not change release gates. None of these original
datasets, legal texts or manual pages is committed to the repository.

## Community result samples

Three additional author-maintained sources were downloaded (48,224,169 payload
bytes;55original/extracted files checked twice bySHA256). Their local
`official-corpus/community-results` manifests record exact revisions, URLs,
license texts and reader/static evidence. No upstream program was executed.

| Source | Actual data | Acceptance role |
| --- | --- | --- |
| [Renumics mesh2vec HAT](https://github.com/Renumics/mesh2vec/tree/e06485562862453511074b1fa428e4a426b556bd/data/hat), MIT | Submitted d3plot family, binout, keyword;18446nodes,9768solids,6400shells,3states from LASSO inventory | Normal native-verification candidate; ELOUT/solid andELOUTDET/shell have16times.20shell stress slots require verifiedIP/layer meaning |
| [node997 dyna_pladebuk](https://github.com/node997/dyna_pladebuk), MIT; exact revision in manifest | BB d3plot family, binout, Include inputs, ASCII/diagnostic logs | **Failed/truncated run**: error termination,2result states, several histories initial-only; reader tensor warning. Use for failure detection, not normal thermal certification |
| [Author's RHHSP dataset](https://zenodo.org/records/21476569), CC-BY-4.0 |8configurations,30CSV tables plus2nativeCurveplot files mislabeled.csv | Format sniffing/time alignment/data-quality tests. Some energy/TiedArea columns are extreme; do not certify all fields |

These samples are locally acquired and inspected; native workflows remain
pending. Nineteen repository candidates were checked and duplicated Ansys/LASSO
payloads were excluded. This is not an exhaustive survey of all online datasets.

## Additional verified sources awaiting acquisition

[DYNAmore's example collection](https://www.dynaexamples.com/) provides public
educational input downloads. Candidate cases are
[Lobatto shell bending](https://www.dynaexamples.com/introduction/examples-manual/section/shell-2),
[solid hourglassing](https://www.dynaexamples.com/introduction/examples-manual/section/solid),
[tied/automatic contact](https://www.dynaexamples.com/introduction/intro-by-k.-weimar/contact/contact-iii),
and [prescribed motion/loading](https://www.dynaexamples.com/introduction/examples-manual/load/presrcibed).
Their pages were verified, but direct acquisition timed out in this session;
do not report those original-site downloads as successful. The four cases were
subsequently acquired from official Ansys mirror pages, as recorded below.
Public access is not a blanket
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
