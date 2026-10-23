# G04 shared entity identification

`query_entities` replaces the abandoned whitespace parser and companion-file guessing with the existing keyword/Include engine, Selector and LASSO readers. It returns user IDs, reference/deformed coordinates, solid/shell connectivity, Part ownership, available keyword material/section links, and an explicitly requested scalar at a 1-based state. All sources are read-only with full file-family SHA256 verification.

69 related tests passed, plus 8 shared history/result tests. Before implementation, the first five identification tests failed because the target was absent; five sparse-ID guards failed before allocating a large array (one dense control passed). A separate blank-diagnostic regression failed on 60edd97, then passed after fixing the failed JobResult diagnostic.

Native evidence: [first run](r413a-batch-report.md) retained 1 passed / 2 failed (test adapter quantity names); [4.13 recheck](r413b-batch-report.md) and [4.10 recheck](r410b-batch-report.md) each passed all three cases at clean 2b81ae3. Actual revisions, empty tracked diff hashes, LF-normalized test hashes and binary/config identities are in [evidence.json](evidence.json).

Sparse geometry indexing uses memory proportional to stored nodes when IDs are widely spaced. The 90-million and 2-billion ID regressions guard allocations before memory is touched; they do not certify LS-PrePost memory behavior at those IDs.

G04 remains partial: beam/tshell, general d3plot Selector predicates, explicit companion-model validation/material mapping and complete native sampling certification are outstanding. Binary Part/material type is never substituted for a keyword material user ID. d3plot query status stays partial for missing material/section IDs even when the tested coordinates/connectivity/results agree. No source data, private manuals, raw native output or local absolute path is published.
