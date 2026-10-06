# 任务看板

由 Codex 维护。范围、验收和任务状态以 [tasks.yaml](../tasks.yaml) 为准；本表记录交接进度，协作规则见 [AGENTS.md](../AGENTS.md)。截至 2026-10-07，本轮核对 main 为 ad475c1（已合入 #69 交叉审阅）。

| 任务 ID | 负责人 | 分支 | PR / 派发 | 交接状态 |
|---|---|---|---|---|
| Q10、Q12 | 反重力 | feat/q10-q12-postprocessing | #57，02e10c6 | AO 中修改：agy 接手 WIP，按 Claude 第十二轮清单修复 |
| Q08 | Cursor | cursor/Q08-xyplot-render | [派发 #61](https://github.com/lwz20210407/LS-PrePost-MCP/pull/61)；#71（Draft，a1f386b） | AO 中执行：cursor-agent 已认领 #71，正在补门禁和原生证据 |
| I04 | Codex | codex/i04-include-tree-evidence | #54，bdbf3c7 | 已按审阅合入 main 448087f，I01/I04 两节均保留；门禁通过，待 Claude 最终合并 |
| I01 | Codex | codex/fix-native-include-diagnostics | #56，38cc02a | 已合并；UNC 入口问题另开分支处理 |
| I01 | Codex | codex/I01-input-path-guard | #72，7c8609c | 已 Ready，待 Claude 审阅；UNC / 设备名在 resolve 前拒绝，双版本九步及最小依赖通过 |
| I01 | Claude → Codex | claude/I01-max-references | #70（Draft） | Claude 交付共享预检接口，Codex 审阅后接入原生调用；待接口正文与验收 |
| I01 | Codex | codex/fix-queue-backpressure-restack | #40，7bacdec | 已 Ready：同步 main，本地九步与最小依赖通过，历史队列证据已核正 |
| I01 | Codex | codex/m1-panel-session-engine | #26，0ef4aa5 | 已 Ready：同步 main/#40、补 ADR 证据链接，门禁通过；按 #40 → #26 审阅 |
| I06 | Codex | codex/I06-cursor-dispatch | #64 | 已合并；本次更新 AO 状态及交接规则 |

- 已合入 #67（AO 流程）、#68（分工及可派发结果任务）、#69（交叉审阅）。Codex 留在桌面版维护 M1 底座和本看板；Claude 启动 AO worker。GitHub 派发 PR 正文是完整任务说明，进展、认领与审阅使用 PR 评论。
- Cursor 的 Q08 与反重力的 #57 各自合入或关闭后，才派下一项。候选为 Q01、Q03、Q04，必须复用 domain/results 的共享读取与计算实现；Q05–Q07、P 系列不外派，Q11 暂不派发。派发前重新核对 owner、依赖、打开及刚合入的派发 PR，防止桌面与非交互 Codex 重复派发。
- #63 已由用户关闭，其越界 Q05/Q07/Q08/Q11 代码不再复用；重复任务单 #62 已关闭，Q08 唯一正式分支为 cursor/Q08-xyplot-render。
- 交付须完成双 Python 3.11/3.12 的 tests.yml 九步、最小依赖 pytest 和任务所需原生证据，再转 Ready 并冻结头。Codex 审 Claude，Claude 审其他三方并执行所有合并；Claude 的 PR 须有 Codex“结论：可以合并”。Actions 额度恢复前以本地门禁为准。
