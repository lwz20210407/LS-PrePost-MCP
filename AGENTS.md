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
- The user authorized continuing M1: I02 contracts, I01 engines I03 command builders/version capabilities and I04 native regression. Keep each change reviewable on its own stacked branch; M0 evidence remains in its separate PR.
- UU remote is the actual confirmed remote environment. The user moved thirteen remaining runc/macro UU cells to I04; M0 is 8/8. Keep them unverified until the remote evidence and operator window are validated.

- Follow through I04, I08, I05, A01–A05, A08, A10 until all M1 exits pass. Batch GUI/remote needs into one external pending list and continue independent work while waiting. Keep local-book content and derivatives private and outside Git.
