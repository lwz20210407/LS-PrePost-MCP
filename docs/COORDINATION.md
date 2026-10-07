# 任务看板

由桌面 Codex 维护，范围与原验收见 [tasks.yaml](../tasks.yaml)，协作规范见 [AGENTS.md](../AGENTS.md)。本次核对 main 为 e41cf65（#40 已合入）。

## Claude 周限额期间的临时认领（用户 2026-10-07 授权）

用户明确要求通过 AO 给 Codex、Cursor、反重力派发独立任务继续开发。此期间派发 PR 发布后可直接认领，不等待 Claude 先合入派发 PR；旧 Ready PR 冻结待审，不等于已合并。每位开发者只推进一个新的活动任务，完成后仍必须 CI 全绿并等待 Claude 审阅；不转移合并权限。下表活动任务的 owner 同步登记在本派发栈的 tasks.yaml 中。

| 任务 | 开发者 | 新分支 | 派发说明 | 状态 |
|---|---|---|---|---|
| Q01 | Cursor | cursor/Q01-result-overview | 本派发 PR（见标题） | 已派发，待 AO 认领 |
| Q04 | 反重力 | antigravity/Q04-field-metrics | 本派发 PR（见标题） | 已派发，待 AO 认领 |

## 已交审与保留事项

| 任务 / PR | 当前状态 |
|---|---|
| Q08 / #71（Cursor，7a92bca） | 修改已交审、五项 CI 全绿；冻结，Y 轴范围验收仍待裁定，保持 partial |
| Q10/Q12 / #57（反重力，8b2a9a1） | 修改已交审、五项 CI 全绿；冻结，未判定审阅通过 |
| I01 / #40 | 已合入 main e41cf65 |
| I01 / #26、#72 | 已 Ready，CI 通过，等待复审 |
| I04 / #54、I03 / #76 | 已 Ready，CI 通过，原生记录按实际 revision 保留 |
| I06 / #73 | 较早的看板更新待审；本派发栈提供本次最新认领快照，合并时保留最新状态 |
| #70/#75 | 共享引用预算接口已合入；本次派发 Codex 接入原生路径 |
| #77、Claude 的 Q06 会话 | Claude 自己的工作保留，不转给其他人，不改其文件 |

- Q01 与 Q04 的读取/数学复用 domain/results 共享实现，Claude 的 domain/model 和共享 curves/lasso_backend/mpp_shards/invariants 保持只读。Q03 暂不派，避免与 Q04 的 extract_field 入口冲突；Q05–Q07/P 不外派，Q11 暂不派。#63 已关闭的越界实现不得复用。
- 三个活动任务的具体文件所有权、原验收、原生路径、语料许可和分支均在各自派发 PR 正文。实现 PR 只改本任务；schema/registry 的不同条目合并时取并集，不重写其它任务。
- 新分支同步只用 merge；四组合加最小依赖五项 GitHub CI 全绿为交付门禁，本地至少跑相关测试并写命令/结果。需要可见 GUI/UU 的验证先准备后集中申请，默认仅跑无图形。
- GitHub 是唯一任务说明与审阅记录；AO 启动提示只给派发 PR 编号。Worker 先评论认领，开实现 Draft 后 claim 实现 PR；Ready 后冻结，不自行合并 main。桌面 Codex 只协调，不与 AO Codex 同时编辑 I01 引用预算文件。
