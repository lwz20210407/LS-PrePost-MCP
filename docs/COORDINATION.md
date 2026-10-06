# 任务看板

由 Codex 维护（规则见 [AGENTS.md](../AGENTS.md) 的“多 AI 协作”一节）。每行一个已派发的任务；任务的范围、验收和状态以 [tasks.yaml](../tasks.yaml) 为准，这里只记录谁在做、在哪个分支、PR 到了哪一步。

状态取值：`进行中`、`待审阅`、`审阅退回`、`已合并`、`已关闭`。

| 任务ID | 负责人 | 分支 | PR | 状态 | 派发日期 |
|---|---|---|---|---|---|
| Q10 | 反重力 | feat/q10-q12-postprocessing | #57（a22773e） | 待审阅 | 2026-10-06 |
| Q12 | 反重力 | feat/q10-q12-postprocessing | #57（a22773e） | 待审阅 | 2026-10-06 |
| I04 | Codex | codex/i04-include-tree-evidence | #54（4958783；第十二轮审阅中） | 待审阅 | 2026-10-06 |
| I01 | Codex | codex/fix-native-include-diagnostics | #56（38cc02a；第十二轮审阅中） | 待审阅 | 2026-10-06 |
| I01 | Codex | codex/fix-queue-backpressure-restack | #40（Draft） | 进行中 | 2026-10-06 |
| I01 | Codex | codex/m1-panel-session-engine | #26（Draft） | 进行中 | 2026-10-06 |
| Q08 | Cursor | cursor/Q08-xyplot-render | [派发 PR #61](https://github.com/lwz20210407/LS-PrePost-MCP/pull/61) | 进行中 | 2026-10-07 |

初始内容由 Claude 于 2026-10-07 按当时的分支和 PR 填写，之后由 Codex 维护。

## Cursor 首个任务：Q08

已派发，等待 Cursor 在任务单 #62 认领并报告分支；尚未观察到分支或提交，不将派发视为已开工。先从最新 main 创建 `cursor/Q08-xyplot`；任务状态仍是 tasks.yaml 中的 partial，满足全部验收前不得改为 done。

验收标准保持 tasks.yaml 原文：

1. 最多 10 条曲线同图；图例、坐标轴标题与范围、对数轴可设。
2. PNG 与同时导出的 CSV 数值一致。
3. 批处理上下文可用（不依赖可见 GUI），依据 E5 结论。

文件分工：主体使用独立 `src/ls_prepost_mcp/xyplot.py`、对应单元/原生测试与 `docs/decisions/evidence/q08/`，复用已有曲线解析经验并保留旧入口。若需要薄接入，只为 Q08 增加 post_tools.py 转发、operations.json 注册或 native/commands.py 构建器，在 PR 逐文件说明原因。不得修改 domain/model、domain/results、原生执行引擎、config、sessions，也不接手 Q10/Q12 或 Q07 数学。遵守 D2，不能自行更换渲染后端或降低验收。详细交付与命名约定见任务单 #62。

## 派发与交接通道

通过本看板和 GitHub 任务单/PR 评论交接；分支、提交和 PR 是可核实进度，IDE 是否打开不作为已开工/已完成的证据。没有专用 IDE 消息通道时，不声称已启动对方 Agent。认领由开发者在任务单报告分支；Codex 更新本表。其他开发者不改本看板。

Cursor 或反重力报告完成时，核对双 Python 的 9 步及最小依赖、原生证据和范围；材料齐全后提醒开 Ready PR 交 Claude，冻结头。PR 合入或关闭后才派下一项，先复查 tasks.yaml 的 owner、依赖、当前分支文件范围和未合 PR；一次只派一个不冲突的任务。反重力 #57 仍待审，当前不另派新任务，也不因 Q10 原 release=v0.6 擅改它的范围。

## Codex 当前审阅与待办

- #54 4958783、#56 38cc02a 正在第十二轮审阅，保持头不动；收到审阅清单后再修。
- I01 / 第十一轮 9b：#56 **未处理** `Settings.input_path` 在允许目录检查之前 resolve UNC 的问题；原函数顺序仍然存在。不能用 #56 的 INCLUDE 检查改进代替这一项，保留为 Codex 原生路径待办并告知审阅者。
- I01 / 引用总数预算：按用户确认分工，Claude 增加共享 max_references，Codex 随接口接入与回归；未交付接口前不记完成。

## 旧分支核对

`codex/fix-native-version-detection` 头为 29a8d1d，比 main 多 6 个历史提交，不应把“多 6 个”直接解释为未交付功能：

- 29a8d1d 的 native/_version_resource.py、native/versions.py、dpf_worker.py 和 test_version_resources.py 与重挂提交 935ef0b 对应文件无差异；后者随 #39 合入（merge 9be385f），主干还有后续审阅修复。
- d6f64fa、22ce5a5 在 main 有 patch-equivalent 提交，分别经 #32/#33 交付；进程与日志改动经 #37/#38 重挂后交付。
- 9651d02 的面板迁移仍在 #26（Draft）分支历史中，不当作已经合入 main。
- 完整旧头 29a8d1d 还被 `codex/fix-session-queue-backpressure` 指向；版本工作树无未提交文件。因此无需为旧版本分支再开重复 PR，可作为待用户决定删除的冗余分支引用。**尚未删除任何分支或工作树**，其现有检出工作树也不自动清理。
