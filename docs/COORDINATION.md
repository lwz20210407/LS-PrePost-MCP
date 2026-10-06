# 任务看板

由 Codex 维护。范围、验收和任务状态以 [tasks.yaml](../tasks.yaml) 为准；本表记录交接进度，协作规则见 [AGENTS.md](../AGENTS.md)。截至 2026-10-07，本轮核对 main 为 fb750d3（已合入 #70 引用预算接口、#74 公开仓库 CI 恢复）。

| 任务 ID | 负责人 | 分支 | PR / 派发 | 交接状态 |
|---|---|---|---|---|
| Q10、Q12 | 反重力 | feat/q10-q12-postprocessing | #57，6f39de9 | AO 已推送新修复，等待 Claude 核对审阅清单 |
| Q08 | Cursor | cursor/Q08-xyplot-render | [派发 #61](https://github.com/lwz20210407/LS-PrePost-MCP/pull/61)；#71（Ready，a7c3a3b） | AO 中执行：cursor-agent 已认领 #71，已交审，等待 Claude 审阅 |
| I04 | Codex | codex/i04-include-tree-evidence | #54，c7ce2d3 | 已同步 main fb750d3，I01/I04 两节均保留；等待五项托管 CI |
| I01 | Codex | codex/fix-native-include-diagnostics | #56，38cc02a | 已合并；UNC 入口问题另开分支处理 |
| I01 | Codex | codex/I01-input-path-guard | #72，5b3f889 | 已 Ready：UNC / 设备名在 resolve 前拒绝；同步 main 后本地 62 项通过；CI 暴露的 POSIX 测试路径已修，等待新 CI |
| I01 | Claude → Codex | claude/I01-max-references | #70（已合并） | 共享接口已交付；Codex 后续接入原生准入，原生调用尚未传上限 |
| I01 | Codex | codex/fix-queue-backpressure-restack | #40，ca34077 | 已 Ready：同步 main fb750d3，本地 8 项队列回归通过，等待托管 CI |
| I01 | Codex | codex/m1-panel-session-engine | #26，7f7e33d | 已 Ready：同步 main/#40，本地 90 项通过；等待托管 CI，按 #40 → #26 审阅 |
| I06 | Codex | codex/I06-cursor-dispatch | #64 | 已合并；本次更新 AO 状态及交接规则 |

- 已合入 #67（AO 流程）、#68（分工及可派发结果任务）、#69（交叉审阅）。Codex 留在桌面版维护 M1 底座和本看板；Claude 启动 AO worker。GitHub 派发 PR 正文是完整任务说明，进展、认领与审阅使用 PR 评论。
- Cursor 的 Q08 与反重力的 #57 各自合入或关闭后，才派下一项。候选为 Q01、Q03、Q04，必须复用 domain/results 的共享读取与计算实现；Q05–Q07、P 系列不外派，Q11 暂不派发。派发前重新核对 owner、依赖、打开及刚合入的派发 PR，防止桌面与非交互 Codex 重复派发。
- #63 已由用户关闭，其越界 Q05/Q07/Q08/Q11 代码不再复用；重复任务单 #62 已关闭，Q08 唯一正式分支为 cursor/Q08-xyplot-render。
- 交付以 PR 的 GitHub CI 全绿为门禁：Ubuntu/Windows × Python 3.11/3.12 四组合加最小依赖；本地至少运行相关测试并记录命令与结果，原生证据仍按任务要求提供。Codex 审 Claude，Claude 审其他三方并执行所有合并；Claude 的 PR 须有 Codex“结论：可以合并”。仓库已公开，CI 已恢复；失败须定位修复。本地九步记录保留为历史证据，不再代替 CI。CI 跑完后若 main 有重叠文件改动，先 merge main 并等待新 CI。
