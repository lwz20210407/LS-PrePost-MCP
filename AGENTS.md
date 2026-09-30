# Development notes

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
