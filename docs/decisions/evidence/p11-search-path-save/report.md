# P11: search-path layout preservation

The public-100 run on clean c46bb9d reached native reading for three large decks but save_model
rejected their INCLUDE_PATH cards through the legacy plain-Include guard. The owned snapshot
reader already supported checked main-file search directories.

save_model now uses the same guarded native tree policy. save_as includes existing relative
search directories when choosing the relocation root and mirrors empty search directories as
well as file parents. Raw path cards and untouched file bytes stay unchanged. Unchanged absolute
dependencies stay explicitly external; modifying a fixed external dependency is still refused.

Four regression tests first failed on the old implementation (three at admission, one missing
directory after admission was fixed). Related Python coverage: 81 passed. Native evidence on
clean ea7d028 is 4/4 for 4.13 and 4/4 for 4.10; see [4.13](sp413a-batch-report.md),
[4.10](sp410a-batch-report.md) and [machine-readable evidence](evidence.json).

P11 remains partial. Transform/opaque variants, parameterized filenames, nested INCLUDE_PATH_RELATIVE,
GUI unsaved edits and 4.8 verification are not closed by these eight cases. Public large-deck
rechecks are separate from this small-fixture native evidence; their historical failures remain.
