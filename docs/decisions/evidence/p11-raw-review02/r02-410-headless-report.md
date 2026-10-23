# P11 raw-tree headless regression

Actual Git revision: `151f2b85259f32a2971ada58c785907fbb9f8c33`

Working tree dirty: `False`; tracked diff SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Scope: all tracked staged/unstaged changes against HEAD, no path exclusions; untracked files excluded.

Compact public rendering of the native reporter; source/model/log/config paths remain external. Product/test blobs are bound in evidence.json.

| Case | Test | Observed job | Expected job | 当前有效 / 已被取代 |
|---|---|---|---|---|
| edited | passed | succeeded | succeeded | 历史运行，已被取代 |
| edited-search | passed | succeeded | succeeded | 历史运行，已被取代 |
| empty | passed | succeeded | succeeded | 历史运行，已被取代 |
| include | passed | succeeded | succeeded | 历史运行，已被取代 |
| mismatch | passed | failed | failed | 历史运行，已被取代 |
| public-edited | passed | succeeded | succeeded | 历史运行，已被取代 |
| public-include | passed | succeeded | succeeded | 历史运行，已被取代 |
| relative-search | passed | succeeded | succeeded | 历史运行，已被取代 |
| search | passed | succeeded | succeeded | 历史运行，已被取代 |
| standalone | passed | succeeded | succeeded | 历史运行，已被取代 |
| unused-search | passed | succeeded | succeeded | 历史运行，已被取代 |
