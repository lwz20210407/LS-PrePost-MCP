# Q01 native inventory: r413b

Actual Git revision: `55581bec789c5dc3469cf3b1e029783af28b84bc`

Working tree dirty: `false`

Tracked diff SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty patch; all tracked paths, no exclusions).

Test source Git blob: `afc829e8db368f871aaf2eeba2bc60f59a379c7f`

Native batch only: process argv contains -nographics. Input families and source configuration hashes stayed unchanged.

| Case | Pytest | JobResult | Reader/native states | Max time difference | Tolerance |
|---|---|---|---|---|---|
| bolt | passed | succeeded | 102 / 102 | 0.0 | 5.00006628036499e-06 |
| long | passed | succeeded | 2001 / 2001 | 0.0 | 2e-06 |
| projectile | passed | succeeded | 16 / 16 | 4.137556942396259e-06 | 7.002789652944805e-05 |
| shell | passed | succeeded | 7 / 7 | 0.0 | 9.999999999999999e-05 |

Full structured identity, executable SHA256, source family SHA256 and job IDs: [evidence.json](evidence.json).

Raw native logs, private paths, vendor binaries and source result files stay outside the repository.
