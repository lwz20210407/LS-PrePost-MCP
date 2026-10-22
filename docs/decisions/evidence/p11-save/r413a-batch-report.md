# P11 r413a：headless batch

实际 Git revision：`ee6a9e02da4d5c96016966458f97c350f0ae3539`；工作树干净。

3 passed / 1 failed。负例的作业状态保持 failed，测试按预期拒绝判定通过。

| 用例 | 期望作业状态 | 实际作业状态 | 测试 | 原生进程数 | 保存文件数 |
|---|---|---|---|---:|---:|
| edited | succeeded | succeeded | passed | 2 | 3 |
| include | succeeded | succeeded | passed | 2 | 3 |
| public-include | succeeded | failed | failed | 0 | None |
| standalone | succeeded | succeeded | passed | 2 | 1 |

所有已启动进程均使用 -nographics；没有 GUI 或远程断开测试。
初版 r413a 的公开用例在准入时失败，未启动原生进程；错误是过严的空 Include 拒绝。
4.10 只运行 standalone / empty 子集，不据此声明相对 Include 路线可用。
