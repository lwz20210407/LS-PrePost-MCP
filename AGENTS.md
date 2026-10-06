# Development instructions

- tasks.yaml is the only source of scope, milestone order, acceptance and status. Identify a task or infrastructure ID before work; put unmatched requests in backlog.md. Do not revive archived plans or dashboards.
- Work incrementally on restructure/v0.5. M0 may change src only for its documented contract bug fixes; no new MCP tools, features or refactors. Archive with git mv; do not delete files during M0.
- Preserve user changes, validated native commands, pitfalls, result mathematics and artifact identity checks. Do not silently narrow acceptance. Ask the user to choose scope/depth changes.
- Keep capabilities.json and development_plan.json unchanged in M0; they remain runtime dependencies. Their generation/migration belongs to M1.
- Run tools/validate_tasks.py, tools/gen_docs.py --check and tools/check_doc_links.py; test minimal and optional dependency configurations when relevant. docs/DEVELOPMENT.md defines verification.
- Batch is the target default, sessions optional. A session request must not silently create a background instance. Visible GUI tests require the single agreed milestone window.
- Report at most 10 lines: completed M0 items / 8, changed status and evidence, blocker, next task. At milestone end report net line changes and open a PR without merging.
- Preserve embedded Python compatibility and explicit backend, user IDs, 1-based state, layer, units and validity semantics. Scripts execute trusted user-directed source; they are not a sandbox.
- Vendor binaries, manuals, native logs, private paths/data and credentials stay out of Git. Use explicit job directories and obey parent workspace hygiene.
- New T1 names must occur in tasks.yaml target_tools; use recipes or scripts for long-tail operations. Old names remain aliases until v0.6.
- I07 belongs to Claude on claude/keyword-engine (local commit a1fb96c). During M0–M2 do not implement I07 or create files under src/ls_prepost_mcp/domain/model/. Integrate that work in M3.

- User-approved M0 closeout: 13 remaining UU remote cells move to I04; M0 is 8/8 and PR #1 becomes Ready for review, never merge it automatically.
- Continue M1 in order I04, I08, I05, A01–A05, A08, A10 until all four exits hold. Use one branch/stacked PR per task; preserve I07 ownership and I02 contract compatibility for Claude.
- Before a commit, run full-dependency pytest, Ruff and task/docs/migration validators and confirm baseline CI green; after pushing, require that commit's CI green before reporting the task verified. CI cannot evaluate an uncommitted tree.
- local-book is restricted: register ID/relative path only; never publish its contents or derived data. Private inputs stay in external environment configuration.
- Reports use at most six Chinese lines: 完成 / 证据 / 下一项 / 待用户. Continue independent work while awaiting one batched GUI/remote window.
- I02 adds strict core contracts and migrates workflow gates; keep the I07 integration boundary.
- I01 remains partial/L1 after review; historical batch/queue tests do not certify the public Win32 path.
- I04 native execution requires explicit opt-in; remote evidence checks are not native passes.
- I08 routes and legacy aliases come from operations.json; run import-linter and preserve the registry.
- I05 references stay outside Git when private; keyword fields use Claude keyword_docs, never a parallel AST parser.
- Claude also owns domain/results/curves.py, invariants.py, lasso_backend.py and their package exports (Q07, Q04, Q01/Q05/Q06), plus model-side P01/P04 work. Reuse those implementations at integration; do not edit or duplicate them. keyword_docs provider was introduced at ce87a62; the model directory remains read-only here.
