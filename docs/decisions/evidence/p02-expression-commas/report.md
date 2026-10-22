# P02: function argument commas in parameter expressions

Public search-path save diagnostics reached equal before/after native counts but were
refused because the keyword parser split fixed-width max(a,b) at the argument comma.
The complete prefix before the first comma must now be a valid parameter name before
it is treated as a card separator. Otherwise the original 10-column name field applies.
For free-format expression cards the editable field is the complete suffix after the
name delimiter, so nested comma arguments can be edited without changing the name/EOL.
The existing whitelisted AST evaluator and single-line writer remain in use.

Three new counterexamples failed on main: fixed-width function parsing, fixed-width
edit/save, and free-format nested-function edit/save. Two controls already passed.
The related pure Python suite passes 124 tests. Native evidence on clean 081ad03:
4.13 2/2 and 4.10 2/2; [4.13](ex413a-batch-report.md), [4.10](ex410a-batch-report.md),
[machine-readable records](evidence.json). P02 remains partial for its other gaps.

Three public search-path decks (025/063/082) were then checked directly through save_model.
Before this repair they all still failed with four reload warnings, despite equal native counts;
afterwards all three succeeded with zero warnings. Each has 564960 nodes / 782601 elements.
Original tree bytes and directory inventories stayed unchanged; full coordinate pagination was
not repeated, so the original public-100 45/5/50 verdicts remain historical and unchanged.
See [before](public-save-413a-batch-report.md) and [after](public-save-413b-batch-report.md).
These three records are separate samples, not evidence for three unrelated model families.
