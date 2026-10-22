# P02 public save diagnostic: public-save-413b

Actual Git revision: `081ad030cc1ddd8d495af4ea58b874eca00a9f5d`; working tree clean.

LS-PrePost 4.13 serial headless calls to save_model. This is a diagnostic, not a full p100 rerun.

| Case | Job status | Nodes | Elements | Reload warnings | Original bytes/list unchanged |
|---|---|---:|---:|---:|---|
| extra-keyword-025 | succeeded | 564960 | 782601 | 0 | true |
| extra-keyword-063 | succeeded | 564960 | 782601 | 0 | true |
| extra-keyword-082 | succeeded | 564960 | 782601 | 0 | true |

Each original/saved pair has identical native counts and sorted Part-ID identity.
The first run still failed because parameter function commas caused four parse warnings.
After the expression repair, the second run succeeds with no warnings. No warning was suppressed.
All native processes returned zero in -nographics mode. No full node-coordinate pagination was repeated.
The private probe is bound by SHA256; its machine paths/raw outputs are excluded from Git.
