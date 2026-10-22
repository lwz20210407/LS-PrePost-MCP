# P11 r413e：headless batch

实际 Git revision：`c6415c5e0bd4423ab66e3313c12b0b88ff4152e8`；工作树干净。

7 passed / 0 failed。负例的作业状态保持 failed，测试按预期拒绝判定通过。

| 用例 | 期望作业状态 | 实际作业状态 | 测试 | 原生进程数 | 保存文件数 |
|---|---|---|---|---:|---:|
| edited | succeeded | succeeded | passed | 2 | 3 |
| empty | succeeded | succeeded | passed | 2 | 1 |
| include | succeeded | succeeded | passed | 2 | 3 |
| mismatch | failed | failed | passed | 1 | None |
| public-edited | succeeded | succeeded | passed | 2 | 4 |
| public-include | succeeded | succeeded | passed | 2 | 4 |
| standalone | succeeded | succeeded | passed | 2 | 1 |

所有已启动进程均使用 -nographics；没有 GUI 或远程断开测试。
初版 r413a 的公开用例在准入时失败，未启动原生进程；错误是过严的空 Include 拒绝。
4.10 只运行 standalone / empty 子集，不据此声明相对 Include 路线可用。
