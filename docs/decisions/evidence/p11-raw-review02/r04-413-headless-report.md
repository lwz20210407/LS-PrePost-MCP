# P11 raw-tree headless regression

Actual Git revision: `e3b42fb4b34135848593fee29ccc85f2ad09f407`

Working tree dirty: `False`; tracked diff SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Scope: all tracked staged/unstaged changes against HEAD, no path exclusions; untracked files excluded.

Compact public rendering of the native reporter; source/model/log/config paths remain external. Product/test blobs are bound in evidence.json.

| Case | Test | Observed job | Expected job | 当前有效 / 已被取代 |
|---|---|---|---|---|
| edited | passed | succeeded | succeeded | 当前产品范围 |
| edited-search | passed | succeeded | succeeded | 当前产品范围 |
| empty | passed | succeeded | succeeded | 当前产品范围 |
| include | passed | succeeded | succeeded | 当前产品范围 |
| mismatch | passed | failed | failed | 当前产品范围 |
| placeholder | passed | partial | partial | 当前产品范围 |
| public-edited | passed | succeeded | succeeded | 当前产品范围 |
| public-include | passed | succeeded | succeeded | 当前产品范围 |
| relative-search | passed | succeeded | succeeded | 当前产品范围 |
| search | passed | succeeded | succeeded | 当前产品范围 |
| standalone | passed | succeeded | succeeded | 当前产品范围 |
| unused-search | passed | succeeded | succeeded | 当前产品范围 |
