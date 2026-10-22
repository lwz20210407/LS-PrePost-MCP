# P02 public save diagnostic: public-save-413a

Actual Git revision: `37c17e2483ae34c43d2109c52e6bdf9cb90f2e0b`; working tree clean.

LS-PrePost 4.13 serial headless calls to save_model. This is a diagnostic, not a full p100 rerun.

| Case | Job status | Nodes | Elements | Reload warnings | Original bytes/list unchanged |
|---|---|---:|---:|---:|---|
| extra-keyword-025 | failed | 564960 | 782601 | 4 | true |
| extra-keyword-063 | failed | 564960 | 782601 | 4 | true |
| extra-keyword-082 | failed | 564960 | 782601 | 4 | true |

Each original/saved pair has identical native counts and sorted Part-ID identity.
The first run still failed because parameter function commas caused four parse warnings.
After the expression repair, the second run succeeds with no warnings. No warning was suppressed.
All native processes returned zero in -nographics mode. No full node-coordinate pagination was repeated.
The private probe is bound by SHA256; its machine paths/raw outputs are excluded from Git.
