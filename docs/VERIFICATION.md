# Implementation verification

This is a bounded development acceptance record, not certification of all LS-PrePost features or engineering models.

Native media increment: Windows4.13.4 exported a complete57-state native H264 movie and3/4-frame workflow-recording replay. Native state/frame logs, independent decoded frame count, dimensions/fps/duration, full decoding and source-family hashes passed; original current state restored. Non-default start/step probes failed and remain unsupported. See [native media scope](NATIVE_MEDIA.md).

Latest framework increment (2026-10-01): 265 local tests passed, including static workflow rejection before side effects, runtime dependency type checks and parameter-study stop/summary behavior. Two synthetic visible 4.13.4 mesh parameter cases passed native quality and save/reopen, and representative private native post/recording workflows passed again through the shared runner. Engineering parameter cases matched analytical peak stress/work. This does not verify complete curve image export or animation file export. Counts below describe earlier increments.

Latest dated increment (2026-10-01): 237 local tests passed. Visible 4.13.4 verification adds workflow gates/parameter replay, keyword/d3plot selection, 9 synthetic part-visibility cases, 11 private-result selection cases, and two parameterized three-step selected-node history/relative-displacement runs. Same-session SCL solid stress/Mises, strain/plastic-strain and stress recording/parameter replay and changed-node history/math dependency replay also passed. Absolute node XYZ/axis alignment, native quality failure, parameter replay, save/reopen and checkpoint recovery also passed on a synthetic keyword model. Original state, geometry, selection, part flags and source-family hashes were checked, including native position minus reference versus displacement. See [result contracts](RESULT_CONTRACTS.md), [GUI verification](GUI_WORKFLOWS.md) and the [current backlog audit](BACKLOG_REVIEW_2026-10-01.md). Test counts do not measure feature coverage; older counts below describe earlier releases.

## Initial automated checks (historical)

- 49 Python tests including input boundaries, include handling, old-output rejection, job correlation, process isolation, vector semantics, version dispatch, PyDYNA scalar/table/series reimport, keyword typo/injection rejection, exact integer IDs, analytic and rotated stress tensors, nonuniform curve calculus, staged native failures and standard MCP stdio discovery/tool calls.
- Skill frontmatter validation and Ruff checks.
- Embedded bridge and LS-Reader worker syntax checked against the older Python grammar they target.

## Native application checks

| Build/profile | Checked result |
|---|---|
| 4.8 | SCL node count; SCL staged d3plot inventory matching independent readers |
| 4.10 | Generated 5×5 shell plate, 36 nodes/25 shells, saved/reopened, IDs/connectivity queried; keyword image visually inspected; d3plot inventory and stress image |
| 4.13 | Generated 4×3 shell plate, 20 nodes/12 shells, saved/reopened and imaged; SCL; d3plot inventory and stress image visually inspected; vector cross-check |

4.13 native displacement and velocity were compared with LASSO at three states for a moving node. LASSO displacement was separately compared with LS-Reader. The compared arrays agreed for the selected fixture after correcting the raw-coordinate interpretation. Unit systems were retained as unspecified fixture units; no physical model validation was claimed.

PyDYNA 0.12.1 created, updated, exported and reimported an elastic material card while preserving the source. LASSO exported a 1001-point binout curve from a separate local sample.

## Findings incorporated into code

- Pin application cwd before bridge execution; load native result families from their parent using a basename, then restore the job cwd.
- Use a relative keyword output name in the owned job cwd where native temporary-name handling rejects absolute drive paths.
- Copy native component arrays before subsequent native queries.
- Block the older embedded vector ABI because its values did not pass numerical comparison; do not return the observed wrong values as success.
- Normalize LASSO 2.0.4 state coordinates to displacement using reference geometry; pin the tested dependency version.
- Reject multi-shard binout input rather than silently read a partial shard set.
- Keep failed and superseded prototype evidence local; do not publish raw user/vendor fixtures.

The first commit's hosted CI passed. Later commits must pass their own workflow; consult the current GitHub Actions status rather than treating this sentence as a perpetual green badge.

## v0.2 development checks

- Native SCL six-component stress exports and comparison with native `von_mises` passed on 4.8, 4.10 and 4.13 representative data. The derived definitions are explicit; private tensors/curves/numeric reports are not published.
- Native ASCII/XYPlot GLSTAT, NODOUT and MATSUM routes and native SCLBinout NODOUT/GLSTAT were exercised on 4.13. Unverified branches are not certified by these checks.
- 4.10 and 4.13 generated structured solid boxes. 4.13 additionally performed selected-node translation, element part reassignment and planar shell extrusion. Count, coordinate/ID/part-membership and extent checks were included.
- The prescribed-displacement shell plate builder exported an analysis deck and reopened it in 4.13. No solver was launched; no quasi-static or physical validation is claimed.
- The generic PyDYNA composer created a synthetic mesh/material/section/part/control deck, reopened in 4.13 with correct node/element IDs and connectivity. This checks that composed standard cards can reach the native workflow, not that all installed keyword classes are supported correctly.
- Graphics startup and SCL file resolution use different native working-directory behavior. Batch numeric export uses SCL without graphics; images use a separate verified Python bridge job while staged inputs remain available.
- A raw `historyvar` probe did not establish trustworthy native slot semantics. That generic native route remains unverified; it is not exposed as a working history-variable tool.

Private case processing was stopped when repetitive runs no longer added coverage. Logs and test output remain local; future tests should target distinct interfaces, formats and failure conditions. Public examples and tests use synthetic inputs only.

Explicit-unit curve mathematics also passed a synthetic mixed-unit force/relative-displacement -> engineering stress/strain/work workflow, including dimensional rejection and unchanged source files. This Python-only check does not launch native software; see UNIT_CONTRACTS.md.

Native solid Model Checking now has six Hex8 criteria verified through twelve pass/fail cases, explicit zero-capture evidence, partial failure counts, hidden-part restoration, no inspection keyword exports, and automatic/recorded-threshold gates blocking edits. Tests use synthetic models on Windows 4.13.4; other solid topologies remain outside this new certification.

Optional native failed-solid capture/localization passed with noncontiguous IDs, disjoint criterion sets, zero after a prior failure, explicit Buffer1 identity invalidation/metadata recovery, other-buffer preservation and parameterized dependency replay. Model replacement/reset invalidation and stale keyword checkpoint rejection have regression coverage.
