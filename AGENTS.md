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
- Claude also owns domain/results/curves.py, invariants.py, lasso_backend.py and their package exports (Q07, Q04, Q01/Q05/Q06), plus model-side P01/P04 work. Reuse those implementations at integration; do not edit or duplicate them. keyword_docs provider was introduced at ce87a62; the model directory remains read-only here.

## 多 AI 协作（用户 2026-10-07 确定）

本项目由四个 AI 并行开发：Codex、Claude、反重力（Antigravity）、Cursor。所有提交的 git 作者是同一个身份，靠下面的命名和标注区分开发者。

**分工**

| 开发者 | 负责范围 |
|---|---|
| Claude | 关键字引擎核心 `src/ls_prepost_mcp/domain/model/`；纯 Python/LASSO 结果计算 `domain/results/`（Q10、Q12 除外）；`model_target_tools.py`；`tools/l3/`；**全部 PR 的审阅与合并** |
| Codex | M1 原生执行通道与进程生命周期等底层修复（`engine/`、`native/`、`service.py`、`config.py`、`jobs.py` 等）；**给反重力和 Cursor 下发独立任务** |
| 反重力 | Q10 截面力与剖切面；Q12 能量平衡与部件耗散检查 `check_energy` |
| Cursor | Codex 派发的独立任务 |

只改自己范围内的文件。确需改动别人范围时，在 PR 正文写明原因，由该范围的负责人审阅。

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
3. 本地跑完 `.github/workflows/tests.yml` 的全部 9 步，Python 3.11 和 3.12 都要跑；另跑一次最小依赖的 pytest。通过数写进 PR 正文。
4. PR 设为 Ready（非 Draft），标题带 `[开发者]`。
5. 推送后不再改动 PR 头，等审阅结果。按审阅清单修改完后，告诉 Claude PR 号和新的头 SHA。

**审阅与合并**

- 所有 PR 由 Claude 审阅。Actions 额度恢复前，Claude 在“最新 main + PR”上跑本地门禁。
- Codex、反重力、Cursor 的 PR：审阅无 P0/P1 且门禁全部通过后，由 Claude 合并。
- Claude 自己的 PR 由用户批准后合并。

**进展检查与消息传递（GitHub 是唯一的消息通道）**

Claude 每 30 分钟检查一次分支、PR 和看板：
- 有新 PR 就审阅。审阅结论和修改清单以 **PR 评论**发布，不再另发文件。
- 分支有新提交但还没开 PR，就提醒该开发者提交 PR。
- 有开发者空闲时，Claude 用本机命令行非交互地启动一次 Codex 来派发任务。这个 Codex 在单独的工作树里运行，只改 `tasks.yaml`、看板和生成的 `docs/TASKS.md`，并写一份派发说明。它会以 `codex/dispatch-<开发者>-<时间>` 分支提交派发 PR，PR 正文就是给该开发者的任务说明；Claude 核对后合并，派发即生效。交互使用的 Codex 也可以手动派发，同样只走看板和派发 PR。同一开发者在看板上有进行中、待审阅或审阅退回的任务时，不再派发。

**每个开发者被唤醒时先做这件事**

1. 拉取最新 `main`，读看板 `docs/COORDINATION.md`。
2. 看自己名下打开的 PR 的评论：有审阅意见就按清单修改，改完在 PR 下评论新头 SHA。
3. 看板上有自己的“进行中”任务、但还没有分支或 PR 的，从最新 `main` 开分支开始做；派发说明在对应的派发 PR 正文里。
4. 做完按上面的“做完”标准提 PR。
