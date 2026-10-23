# Review02 P1-4: preflight confinement

Settings._keyword_report now installs confinement at the resource access point. An unguarded caller cannot read an outside Include tree before rejecting it. Files, candidates, search directories and native cwd alternatives are checked before subsequent filesystem probes; nested scopes intersect instead of replacing a stricter outer guard. The shared public access.root_guard replaces the corpus runner's private model-tool helper (review02 P2 #121).

| Verification | Result | 当前有效 / 已被取代 |
|---|---|---|
| Baseline 0563045, new regression suite | 8 failed / 1 passed control | Historical failure, retained |
| Clean 98aa2ca, new regression suite | 9 passed | Valid for recorded product blobs |
| Related configuration/access/staging/Include suites | 176 passed | Valid for recorded product blobs |

[evidence.json](evidence.json) binds actual execution revision `98aa2ca782e9c473bf82397535fcb9fbfecf9160`, product blobs and test blob. This is an offline security regression, with local owned toy files only; no network request, LS-PrePost run or solver evidence is claimed. Original baseline and fixed stdout hashes are recorded. The control ensures an enclosing narrower scope remains effective.

Baseline assertion: `Denied files were opened before confinement: ['secret.k', 'second.k']`. The UTF-16/binary cases also reject as outside before disclosing content errors; stat instrumentation verifies that rejected children are not probed afterward.

Reproduce from a checkout with PYTHONPATH=src plus repository root, PYTHONDONTWRITEBYTECODE=1, shared locked environment:

```text
python -m pytest tests/test_keyword_preflight_access_point.py -q
```

I01 remains partial/L1; this does not certify GUI or transport behavior. The public Settings rejection remains ValueError, preserving existing callers. No access policy widening, new tool, task acceptance change or raw user data is included.
