# Q01 native inventory: r413a

Actual Git revision: `465c129186be7d9db462acdef543e5644b3ee44c`

Working tree dirty: `false`

Tracked diff SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty patch; all tracked paths, no exclusions).

Test source Git blob: `e3da28e2ecba62260ba289d6b03366605b5dd699`

Native batch only: process argv contains -nographics. Input families and source configuration hashes stayed unchanged.

| Case | Pytest | JobResult | Reader/native states | Max time difference | Tolerance |
|---|---|---|---|---|---|
| bolt | passed | succeeded | 102 / 102 | 0.0 | 5.00006628036499e-06 |
| projectile | passed | succeeded | 16 / 16 | 4.137556942396259e-06 | 7.002789652944805e-05 |
| shell | passed | succeeded | 7 / 7 | 0.0 | 9.999999999999999e-05 |

Historical first run before removal of the 2000-state omission; later r413b also covers a generated 2001-state history.

Full structured identity, executable SHA256, source family SHA256 and job IDs: [evidence.json](evidence.json).

Raw native logs, private paths, vendor binaries and source result files stay outside the repository.
