# Q01 native inventory: r48b

Actual Git revision: `f9b980f88d7e1ec0e0043d6154e2a8d2fd17fc8b`

Working tree dirty: `false`

Tracked diff SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty patch; all tracked paths, no exclusions).

Test source Git blob: `afc829e8db368f871aaf2eeba2bc60f59a379c7f`

Native batch only: process argv contains -nographics. Input families and source configuration hashes stayed unchanged.

| Case | Pytest | JobResult | Reader/native states | Max time difference | Tolerance |
|---|---|---|---|---|---|
| projectile | failed | partial | 16 / None | None | None |

A private 4.8 configuration copy reused an existing initialized 4.10 Python-home setting. The user configuration was unchanged. The isolated attempt exited with 0xC0000409; root cause is unconfirmed, and 4.8 is not certified.

Full structured identity, executable SHA256, source family SHA256 and job IDs: [evidence.json](evidence.json).

Raw native logs, private paths, vendor binaries and source result files stay outside the repository.
