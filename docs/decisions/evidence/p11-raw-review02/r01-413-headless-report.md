# P11 raw-tree headless regression

Actual Git revision: `ccaed425a9f44c5635fe27a1fbd9aae9af9fd228`

Working tree dirty: `False`; tracked diff SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Scope: all tracked staged/unstaged changes against HEAD, no path exclusions; untracked files excluded.

Compact public rendering of the native reporter; source/model/log/config paths remain external. Product/test blobs are bound in evidence.json.

| Case | Test | Observed job | Expected job | 当前有效 / 已被取代 |
|---|---|---|---|---|
| edited | failed | failed | succeeded | 历史运行，已被取代 |
| edited-search | failed | failed | succeeded | 历史运行，已被取代 |
| empty | failed | failed | succeeded | 历史运行，已被取代 |
| include | failed | failed | succeeded | 历史运行，已被取代 |
| mismatch | passed | failed | failed | 历史运行，已被取代 |
| public-edited | failed | failed | succeeded | 历史运行，已被取代 |
| public-include | failed | failed | succeeded | 历史运行，已被取代 |
| relative-search | failed | failed | succeeded | 历史运行，已被取代 |
| search | failed | failed | succeeded | 历史运行，已被取代 |
| standalone | failed | failed | succeeded | 历史运行，已被取代 |
| unused-search | failed | failed | succeeded | 历史运行，已被取代 |
