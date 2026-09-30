# Initial implementation verification

This is a bounded development acceptance record, not certification of all LS-PrePost features or engineering models.

## Automated checks

- 33 Python tests including input boundaries, include handling, old-output rejection, job correlation, process isolation, vector semantics, version dispatch, optional PyDYNA reimport, literal binout paths and standard MCP stdio discovery/tool calls.
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
