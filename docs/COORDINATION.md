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

派发已通过 #61 合入 main，owner 为 cursor，采用 `cursor/Q08-xyplot-render`。已观察到本地分支及独立工作树，当前头仍为基线 ab01bdc，未见实现提交；Cursor 按 #61 正文执行并在该 PR 评论报告进展。并行产生的重复任务单 #62 已关闭，不另建 `cursor/Q08-xyplot`。任务状态仍为 tasks.yaml 中的 partial，满足全部验收前不得改为 done。

验收标准保持 tasks.yaml 原文：

1. 最多 10 条曲线同图；图例、坐标轴标题与范围、对数轴可设。
2. PNG 与同时导出的 CSV 数值一致。
3. 批处理上下文可用（不依赖可见 GUI），依据 E5 结论。

文件分工以已合入的派发 PR #61 正文为准：Q08 的 gui_curves.py、gui_media.py、专属测试与去私有信息证据；保留旧入口，必要注册仅调整 Q08 项。不得修改 Claude 的核心目录或自行扩展为 M1 底座修复，也不接手 Q10/Q12 或 Q07 数学。跨范围变更先报告并在 PR 中说明原因。遵守 D2，不能自行更换渲染后端或降低验收。

## 派发与交接通道

GitHub 是唯一消息通道，派发说明使用派发 PR 正文，审阅与进度使用 PR 评论；分支、提交和 PR 是可核实进度，IDE 是否打开不作为已开工/已完成的证据。没有专用 IDE 消息通道时，不声称已启动对方 Agent。认领由开发者在派发 PR 评论报告分支；Codex 更新本表。其他开发者不改本看板。

Cursor 或反重力报告完成时，核对双 Python 的 9 步及最小依赖、原生证据和范围；材料齐全后提醒开 Ready PR 交 Claude，冻结头。PR 合入或关闭后才派下一项，先复查最新 tasks.yaml 的 owner、依赖、当前分支文件范围，以及打开和刚合入的派发 PR；Claude 启动的非交互 Codex 也可能正在派发，发布前再次核对，已有任务不得重复；一次只派一个不冲突的任务。反重力 #57 仍待审，当前不另派新任务，也不因 Q10 原 release=v0.6 擅改它的范围。

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

## 待解决的范围冲突

#63（antigravity/q05-q11-postprocessing，75b3680）包含 Q05/Q07/Q08/Q11，未见正式派发；Q08 与 #61 已派给 Cursor 的任务直接重叠，#57 又仍待审。已在 #63 与 #61 评论协调：保留提交、暂缓重叠部分合并，不修改 Q08 owner，不自动认可额外任务。Pillow 绘图路线也不能自行替代已定 D2 与 #61 验收。由 Claude 先核对范围与交接；若要改变分工或后端标准，交用户决定。此记录不是新任务派发。
