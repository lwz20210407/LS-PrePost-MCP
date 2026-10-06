# Version-aligned PyDYNA routing

The supported dependency is 0.12.1. The website's six entry cards are documentation sections, not six functional modules. Review [integration analysis](../../../docs/archive/2026-10/PYDYNA_INTEGRATION.md) for source/version findings and incomplete workflows.

Use `describe_pydyna_keyword` to inspect a real class. `compose_keyword_deck` takes `cards=[{class_name, fields, options?}]`; tables are lists of column/value objects, series are flat lists. Do not pass raw scripts or copied tutorial text. Unknown names are errors, including the `elfrom` typo found in some upstream examples. Use `elform` only where the schema actually exposes it.

`update_keyword_fields` selects exactly one keyword by scalar properties. For multi-row `Part`, `Node`, `ElementShell`, etc., use `update_keyword_table_row` with an explicit unique row selector. Preserve units; do not derive material constants from a class default. TITLE/ID options must be explicit. Complex nested card sets, includes and parameter transformations remain outside the generic composer.

Validation success means the library validators and specified-field reimport checks passed, not that a solver or LS-PrePost has accepted the physics. Open generated mesh-bearing decks with native `inspect_model`/`render_snapshot` when requested. Fragment-only decks do not have nodes and should not use a nonempty-model native check.

Official examples may download data, run solvers, invoke DPF or open GUI windows at top level. Study and adapt the steps rather than execute whole files. The current project has no solver/DPF tool and does not claim complete official example migration. Prefer representative cases for new interfaces and failure modes over repeating identical processing on every private dataset.
