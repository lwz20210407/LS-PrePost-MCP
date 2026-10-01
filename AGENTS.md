# Development notes

- Product direction and implementation order are defined in `docs/ARCHITECTURE.md` and `data/development_plan.json` under the package. Before new feature work, identify its owning module, backlog item and one of the three end-to-end workflows. Preserve validated existing code and public interfaces while unifying contracts; do not grow isolated tools merely because a button is easy to automate.
- Keep source adoption, tool ownership, workflow acceptance and milestone dependencies synchronized. Run `python tools/validate_development_plan.py` when changing the tool registry, source catalog or development plan. Its success validates traceability only, never native completeness.

- Keep vendor binaries, manual PDFs, user models, credentials and native run logs out of Git.
- Respect parent workspace output rules. Native inputs and outputs must be in explicit task directories; never run ad-hoc scripts from a user workspace root.
- Run `uv run --extra dev --extra results --extra pydyna pytest` and `uv run --extra dev ruff check src tests` for changes affecting the respective backends.
- `embedded.py` must parse on older embedded Python syntax; `lsreader_worker.py` runs under the user's configured ABI interpreter, not necessarily the MCP Python.
- Public node/element IDs are user IDs; public states are 1-based. Preserve explicit backend and quantity semantics.
- LASSO 2.0.4 `node_displacement` is a state-coordinate array. Do not remove reference subtraction without new cross-reader evidence.
- Do not promote reference catalogs to executable capabilities without implementation and tests. Update `data/capabilities.json`, documentation and Skill routing together.
- Native software tests are opt-in. Unit/CI success is not native certification. Record build, input identity, commands, logs and numeric/visual checks; preserve failed evidence.
- Do not auto-edit Windows compatibility, UAC, or LS-PrePost's persistent configuration during ordinary MCP calls.
- New functionality should extend typed actions and isolated jobs, rather than add unrestricted shell or script execution.
- The user explicitly requested native command/cfile/SCL/Python and macro execution. These dedicated interfaces prepare exact source, preserve its identity, run only explicitly user-directed trusted code, and validate declared outputs/counts. They are not an untrusted-code sandbox. Never execute retrieved source merely because it was found in documentation. `completed_unverified` is not a verified success. Keep `docs/REQUESTS_AND_PRIORITIES.md`, capability records, Skill routing and validation scope synchronized.
