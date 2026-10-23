# P11 review02: reopen the actual saved tree

The second headless inspection now bypasses filename/search-path normalization for the owned saved tree only. The bridge changes to the saved root, opens the relative original main filename and attests cwd/load_name/resolved_main from inside the application. The host validates that attestation before accepting the observation. Ordinary source inspection still uses its confined owned snapshot; no user source directory becomes the raw reopen cwd.

A raw reopen is private, headless, inspect-only and limited to a saved tree under the job root. Existing lspost.db assets are refused before launch. During real native testing LSPP created a fresh lspost.db in the saved root: it is relocated, without rewriting any deck, into that inspection job's exclusive native-open-side-effects directory and its identity is recorded. Unknown new files are not silently discarded. Saved bytes AND directory listings, and original source bytes/listings, are checked after reopening.

| Run | Revision | Result | 当前有效 / 已被取代 |
|---|---|---|---|
| [r01 4.13](r01-413-headless-report.md) | ccaed42 | 1 passed / 10 failed | Historical failure: newly generated lspost.db changed the listing |
| [r02 4.13](r02-413-headless-report.md) | 151f2b8 | 11 passed | Superseded by merged required-check policy run |
| [r02 4.10](r02-410-headless-report.md) | 151f2b8 | 11 passed | Superseded by merged required-check policy run |
| [r03 4.13](r03-413-headless-report.md) | a181aa1 | 11 passed | Historical before layout/warning protection |
| [r03 4.10](r03-410-headless-report.md) | a181aa1 | 11 passed | Historical before layout/warning protection |
| [r04 4.13](r04-413-headless-report.md) | e3b42fb | 12 passed | Current for recorded product blobs |
| [r04 4.10](r04-410-headless-report.md) | e3b42fb | 12 passed | Current for recorded product blobs |

The historical r03 clean revision is `a181aa11ea24d39d0bca9985403f81f947be100d`, including #133. Latest r04 executes `e3b42fb4b34135848593fee29ccc85f2ad09f407`. Each version covers standalone, disabled-comment Include, a three-file tree, edited tree, public Bolt Include, public control edit, expected-count mismatch, two relative search-path forms, an empty search directory and an edited search-path tree. The mismatch is a successful negative TEST with a failed JOB and no artifacts. Every positive after_reopen attests the actual saved root and unnormalized main. The two r03 runs contained 42 native headless processes; r04 adds the expected-partial placeholder case and contains 46 processes in total; no GUI or remote session was exercised.

[evidence.json](evidence.json) is compact metadata: actual revision, clean/diff status, twelve product-module blobs, both native test blobs, executable/config identities, case verdicts, observed counts/Part-ID hashes, source-tree hashes and native auxiliary identities. Reports use UTF-8/LF hashing. Raw native jobs, models, logs and local paths remain outside the repository. Product changes cannot retain the active evidence claim without refreshing it or explicitly downgrading its validity; the evidence regression checks the actual product blobs, not just the test blob.

Baseline 0563045: the three raw-tree routing regressions failed because LS-PrePost was given native_<token>_00000.k instead of saved main.k. The additional provenance regression failed because historical native claims bound no product modules. These are separate from the ten real first-run failures retained above. The raw-path routing and admission/auxiliary controls now pass offline.

Reproduce separately, serially, from a clean checkout with the locked full environment and these environment variables: PYTHONPATH=src plus repository root; PYTHONDONTWRITEBYTECODE=1; OPENBLAS_NUM_THREADS=1; LSPP_CORPUS_DIR pointing to the external registered public corpus. Use the appropriate initialized executable without changing its configuration:

```text
python -m pytest tests/test_save_model_native.py tests/test_save_search_paths_native.py -m native --run-native --native-strict --native-executable "<4.13 executable>" --native-output "<outside-repo>/p11-413" -q
python -m pytest tests/test_save_model_native.py tests/test_save_search_paths_native.py -m native --run-native --native-strict --native-executable "<4.10 executable>" --native-output "<outside-repo>/p11-410" -q
```

P11 stays partial/L2 for this registered headless subset. GUI unsaved edits, 4.8, unsupported Include variants/parameterized names/nested relative search semantics and non-ASCII saved filenames are not certified by these cases. A saved-root asset named lspost.db is an explicit refusal. This evidence does not establish material/connection/solver correctness.


## Review02 linked-layout and template-warning refresh

Fresh clean execution e3b42fb4b34135848593fee29ccc85f2ad09f407: [r04 4.13](r04-413-headless-report.md) and [r04 4.10](r04-410-headless-report.md) each passed 12 tests. The new template case is an expected partial result with a missing template_inputs_resolved check and visible warning; both native observations and raw saved-root path checks succeeded. Ordinary disabled Include remains allowed with its warning. Sources, saved bytes and directory inventories remained intact. The previous eleven-case runs stay historical and retain their actual source blobs and failures. L2 covers this registered subset, not link materialization, solver physics, GUI/4.8 or arbitrary path cases.
