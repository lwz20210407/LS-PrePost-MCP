# P11 r410a：headless batch

实际 Git revision：`ad004804e3acf9d65aca0481dc5a2de2039c4459`；工作树干净。

2 passed / 0 failed。负例的作业状态保持 failed，测试按预期拒绝判定通过。

| 用例 | 期望作业状态 | 实际作业状态 | 测试 | 原生进程数 | 保存文件数 |
|---|---|---|---|---:|---:|
| empty | succeeded | succeeded | passed | 2 | 1 |
| standalone | succeeded | succeeded | passed | 2 | 1 |

所有已启动进程均使用 -nographics；没有 GUI 或远程断开测试。
初版 r413a 的公开用例在准入时失败，未启动原生进程；错误是过严的空 Include 拒绝。
4.10 只运行 standalone / empty 子集，不据此声明相对 Include 路线可用。
