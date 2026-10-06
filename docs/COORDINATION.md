# 任务看板

由 Codex 维护（规则见 [AGENTS.md](../AGENTS.md) 的“多 AI 协作”一节）。每行一个已派发的任务；任务的范围、验收和状态以 [tasks.yaml](../tasks.yaml) 为准，这里只记录谁在做、在哪个分支、PR 到了哪一步。

状态取值：`进行中`、`待审阅`、`审阅退回`、`已合并`、`已关闭`。

| 任务ID | 负责人 | 分支 | PR | 状态 | 派发日期 |
|---|---|---|---|---|---|
| Q10、Q12 | 反重力 | feat/q10-q12-postprocessing | #57 | 待审阅 | 2026-10-06 |
| I04 | Codex | codex/i04-include-tree-evidence | #54 | 审阅退回 | 2026-10-06 |
| I01 | Codex | codex/fix-native-include-diagnostics | #56 | 待审阅 | 2026-10-06 |
| I01 | Codex | codex/fix-queue-backpressure-restack | #40（Draft） | 进行中 | 2026-10-06 |
| I01 | Codex | codex/m1-panel-session-engine | #26（Draft） | 进行中 | 2026-10-06 |
| （待派发） | Cursor | — | — | — | — |
| Q08 | Cursor | cursor/Q08-xyplot-render | — | 进行中 | 2026-10-07 |

初始内容由 Claude 于 2026-10-07 按当时的分支和 PR 填写，之后由 Codex 维护。
