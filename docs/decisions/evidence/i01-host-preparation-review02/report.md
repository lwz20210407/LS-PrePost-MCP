# Review02 I01 host preparation and dispatch identity

A HostPreparationError now separates a failing host callback from a transport send which might have reached LS-PrePost. engine-result.json and host-preparation-failed.json both record no dispatch; the engine phase is host_preparation, status failed. Empty exceptions retain their original type as the message fallback. Session log bytes from partial host panel activity are still preserved, even though no request was submitted.

This does not certify absence of panel side effects: the model/session remain uncertain with the pending request, and nothing is replayed. An actual send failure remains submitted=true/unverified. Readonly GUI idle probing before recovery is still an I01 gap and needs a new GUI validation window; this PR does not change recovery or claim that Apply has stopped.

| Evidence | 当前有效 / 已被取代 |
|---|---|
| Baseline 0563045: 2 regressions failed (submitted was true) | Historical regression proof |
| Clean 0caaa5a: related 63 passed | Current for recorded host product blobs |

[evidence.json](evidence.json) binds executed product/test Git blobs and stdout hashes. The new tests exercise both a diagnostic exception and RuntimeError with an empty message, check that transport was never called, and verify native-session.log raw bytes. No LS-PrePost process, solver or GUI was run.

Reproduce with python -m pytest tests/test_host_preparation_identity_review02.py tests/test_sessions_workflows.py tests/test_engines.py -q, the shared locked environment and an external dated basetemp/cache directory. I01 remains partial/L1.
