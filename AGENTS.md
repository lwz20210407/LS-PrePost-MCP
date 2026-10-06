# Development instructions

- tasks.yaml is the only source of scope, milestone order, acceptance and status. Identify a task or infrastructure ID before work; put unmatched requests in backlog.md. Do not revive archived plans or dashboards.
- Work incrementally on restructure/v0.5. M0 may change src only for its documented contract bug fixes; no new MCP tools, features or refactors. Archive with git mv; do not delete files during M0.
- Preserve user changes, validated native commands, pitfalls, result mathematics and artifact identity checks. Do not silently narrow acceptance. Ask the user to choose scope/depth changes.
- Keep capabilities.json and development_plan.json unchanged in M0; they remain runtime dependencies. Their generation/migration belongs to M1.
- Run tools/validate_tasks.py, tools/gen_docs.py --check and tools/check_doc_links.py; test minimal and optional dependency configurations when relevant. docs/DEVELOPMENT.md defines verification.
- Batch is the target default, sessions optional. A session request must not silently create a background instance. Visible GUI tests require the single agreed milestone window.
- Report at most 10 lines: completed M0 items / 8, changed status and evidence, blocker, next task. At milestone end report net line changes and open a PR without merging.
- Preserve embedded Python compatibility and explicit backend, user IDs, 1-based state, layer, units and validity semantics. Scripts execute trusted user-directed source; they are not a sandbox.
- Vendor binaries, manuals, native logs, private paths/data and credentials stay out of Git. Use explicit job directories and obey parent workspace hygiene.
- New T1 names must occur in tasks.yaml target_tools; use recipes or scripts for long-tail operations. Old names remain aliases until v0.6.
- I07 belongs to Claude on claude/keyword-engine (local commit a1fb96c). During M0–M2 do not implement I07 or create files under src/ls_prepost_mcp/domain/model/. Integrate that work in M3.

- User-approved M0 closeout: 13 remaining UU remote cells move to I04; M0 is 8/8 and PR #1 becomes Ready for review, never merge it automatically.
- Continue M1 in order I04, I08, I05, A01–A05, A08, A10 until all four exits hold. Use one branch/stacked PR per task; preserve I07 ownership and I02 contract compatibility for Claude.
- Before a commit, run full-dependency pytest, Ruff and task/docs/migration validators and confirm baseline CI green; after pushing, require that commit's CI green before reporting the task verified. CI cannot evaluate an uncommitted tree.
- local-book is restricted: register ID/relative path only; never publish its contents or derived data. Private inputs stay in external environment configuration.
- Reports use at most six Chinese lines: 完成 / 证据 / 下一项 / 待用户. Continue independent work while awaiting one batched GUI/remote window.
- I02 adds strict core contracts and migrates workflow gates; keep the I07 integration boundary.
- I01 remains partial/L1 after review; historical batch/queue tests do not certify the public Win32 path.
- I04 native execution requires explicit opt-in; remote evidence checks are not native passes.
- I08 routes and legacy aliases come from operations.json; run import-linter and preserve the registry.
- I05 references stay outside Git when private; keyword fields use Claude keyword_docs, never a parallel AST parser.
- Claude also owns domain/results/curves.py, invariants.py, lasso_backend.py, mpp_shards.py and their package exports (shared by Q01/Q03–Q07; Claude implements Q05–Q07, Q01/Q03/Q04 may be dispatched), plus model-side P-series work. Reuse those implementations at integration; do not edit or duplicate them. keyword_docs provider was introduced at ce87a62; the model directory remains read-only here.

## 多 AI 协作（用户 2026-10-07 确定）

本项目由四个 AI 并行开发：Codex、Claude、反重力（Antigravity）、Cursor。所有提交的 git 作者是同一个身份，靠下面的命名和标注区分开发者。

**分工**

| 开发者 | 负责范围 |
|---|---|
| Claude | 关键字引擎核心 `src/ls_prepost_mcp/domain/model/`；结果计算核心 `domain/results/`（曲线、LASSO 读取、MPP 分片、不变量等共享实现）与 Q05、Q06、Q07；P 系列模型侧任务；`model_target_tools.py`；`tools/l3/`（I09）；**Codex、反重力、Cursor 的 PR 审阅，以及全部 PR 的合并执行** |
| Codex | M1 原生执行通道与进程生命周期等底层修复（`engine/`、`native/`、`service.py`、`config.py`、`jobs.py` 等）；**给反重力和 Cursor 下发独立任务** |
| 反重力 | Q10 截面力与剖切面；Q12 能量平衡与部件耗散检查 `check_energy`；Codex 派发的其他任务 |
| Cursor | Codex 派发的独立任务 |

只改自己范围内的文件。确需改动别人范围时，在 PR 正文写明原因，由该范围的负责人审阅。

**可派发的结果任务（用户 2026-10-07 确定）**：Q01 结果概览、Q03 场数据提取、Q04 工程量与失效掩码，可以由 Codex 派给 Cursor 或反重力。这些任务必须复用 `domain/results` 已有的共享实现（如 `lasso_backend`、`curves`、`mpp_shards`、`invariants`），不得另写一套读取或运算代码。确需扩展共享实现时，在 PR 正文说明，由 Claude 审阅。Q05、Q06、Q07 和 P 系列不派发给其他人。

**分支、提交、PR 的标识**

- 分支名：`<开发者>/<任务ID>-<简述>`，开发者只用 `codex`、`claude`、`antigravity`、`cursor`。例：`cursor/Q08-curve-filter`。已有分支不改名。
- PR 标题以 `[开发者]` 开头，例：`[cursor] feat(Q08): ...`。
- PR 正文第一行：`开发者：Cursor；任务：Q08`。
- 提交说明末尾加一行 `Agent: cursor`（换成自己的名字）。

**任务派发与认领（Codex 负责）**

- 任务的唯一来源是 `tasks.yaml`。派发时，Codex 把任务的 `owner` 设为对应开发者，并在 [docs/COORDINATION.md](docs/COORDINATION.md) 看板登记一行。
- 看板只由 Codex 修改；其他开发者在自己的 PR 正文里报告进度。
- 同一任务同一时间只有一个负责人。派发的任务要相互独立：尽量不改同一批文件，也不互相等待。
- 某个开发者的 PR 合入或关闭后，Codex 给他派下一个任务。

**“做完”的标准（满足后交 Claude 审阅）**

1. 从最新 `main` 开分支。同步 `main` 只用 merge，不 rebase，不 force push。
2. 新功能有测试；修 bug 的测试在 `main` 上失败、修复后通过。
3. PR 的 GitHub CI 全部通过：`tests.yml` 在 Ubuntu 和 Windows × Python 3.11 和 3.12 四个组合上各跑 9 步，另有最小依赖任务。仓库已公开（2026-10-07），Actions 不再受额度限制。本地至少跑与改动相关的测试，并在 PR 正文写明跑过的命令和结果。
4. PR 设为 Ready（非 Draft），标题带 `[开发者]`。
5. 推送后不再改动 PR 头，等审阅结果。按审阅清单修改完后，告诉 Claude PR 号和新的头 SHA。

**审阅与合并**

- Codex、反重力、Cursor 的 PR 由 Claude 审阅；Claude 的 PR 由 Codex 审阅（交叉审阅，用户 2026-10-07 确定）。门禁以 PR 的 GitHub CI 为准，要求全部通过；如果 CI 跑完后 main 又合入了与本 PR 改动文件重叠的提交，先用 merge 同步 main，等新一轮 CI 通过再合并。
- Codex、反重力、Cursor 的 PR：审阅无 P0/P1 且门禁全部通过后，由 Claude 合并。
- Claude 自己的 PR：Claude 在“最新 main + PR”的本地合并树上非交互地启动 Codex 审阅（不改文件、不联网），Codex 的结论原样以“Codex 审阅”PR 评论发布，第一行为“结论：可以合并”或“结论：不能合并”。Codex 判可以合并、且门禁全部通过后，由 Claude 执行合并，不再等用户批准（用户 2026-10-07 授权）。判不能合并时，Claude 按清单修改，推送后请 Codex 复审。交互使用的 Codex 也可以直接在 PR 下发表审阅意见，同样有效。

**进展检查与消息传递（GitHub 是唯一的消息通道）**

Claude 每 30 分钟检查一次分支、PR 和看板：
- 有新 PR 就审阅。审阅结论和修改清单以 **PR 评论**发布，不再另发文件。
- 分支有新提交但还没开 PR，就提醒该开发者提交 PR。
- 有开发者空闲时，Claude 用本机命令行非交互地启动一次 Codex 来派发任务。这个 Codex 在单独的工作树里运行，只改 `tasks.yaml`、看板和生成的 `docs/TASKS.md`，并写一份派发说明。它会以 `codex/dispatch-<开发者>-<时间>` 分支提交派发 PR，PR 正文就是给该开发者的任务说明；Claude 核对后合并，派发即生效。交互使用的 Codex 也可以手动派发，同样只走看板和派发 PR。同一开发者在看板上有进行中、待审阅或审阅退回的任务时，不再派发。派发 PR 合并后，Claude 在 Agent Orchestrator 中启动该开发者的 worker（见下一节），不再需要用户转发唤醒口令。

**在 Agent Orchestrator（AO）中运行（用户 2026-10-07 部署）**

Cursor 和反重力的派发任务默认由本机的 Agent Orchestrator 作为 worker 运行：Cursor 用 `cursor-agent`，反重力用 `agy`。每个任务有独立的 worktree 和分支，由 AO 管理。IDE 里已经开始的工作可以在 IDE 中做完。
- worker 的启动说明只有一行，内容是派发 PR 的编号；完整任务说明以派发 PR 正文为准，worker 自己用 `gh pr view` 读取。
- 完成第一个有意义的提交后就推送并开 Draft PR，运行 `ao session claim-pr <PR号>` 认领；全部满足“做完”标准后改为 Ready。
- 审阅意见回灌：认领后，PR 上未解决的行内审阅评论由 AO 自动转给该 worker；顶层评论形式的审阅清单由 Claude 另用 `ao send` 通知 worker 去读。修改后照常推送，并在 PR 下评论新头 SHA。
- 删除文件或目录、强推、rebase、改写历史、删除分支或 worktree、向 main 推送：在 AO 中会被拒绝（Cursor 由本机钩子拒绝）或停下等待确认（反重力由其权限规则控制）。不要换写法或换工具重试，把需要处理的对象写进 PR 正文或评论，由用户决定。
- CI 失败会由 AO 转给认领该 PR 的 worker。仓库公开后 CI 恢复正常，失败就是真实问题，修复后再推送。
- 测试和临时文件放在本任务的 dated scratch 目录（`F:\PythonWoking\temp\<YYYYMMDD>-<任务>\`）或 worktree 内被 git 忽略的位置；不在 `F:\PythonWoking` 根目录新建任何东西。

**每个开发者被唤醒时先做这件事**（不在 AO 中工作时）

1. 拉取最新 `main`，读看板 `docs/COORDINATION.md`。
2. 看自己名下打开的 PR 的评论：有审阅意见就按清单修改，改完在 PR 下评论新头 SHA。
3. 看板上有自己的“进行中”任务、但还没有分支或 PR 的，从最新 `main` 开分支开始做；派发说明在对应的派发 PR 正文里。
4. 做完按上面的“做完”标准提 PR。
