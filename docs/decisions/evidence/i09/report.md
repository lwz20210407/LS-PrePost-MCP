# I09 L3 前处理 8 题：Codex 运行记录（2026-10-06）

- 框架提交：`11f5da0`（`tools/run_l3.py --agent codex --domain pre`），full 工具集。
- 代理：codex-cli 0.156.1，CLI 默认模型（事件流里没有记录型号）。不读用户 config.toml，关闭 apps 和插件，沙箱只读，lspp 预先批准并设为必需。
- 判分：确定性检查（见 [DEVELOPMENT.md](../../../DEVELOPMENT.md) 的“I09 L3 场景评测”）。逐题明细在 [evidence.json](evidence.json)。

**结果：8/8 成功。** lspp 调用次数平均 12.75，范围 4–19。

| 题 | 任务 | 成功 | lspp 调用 | 报错调用 | 其他工具 | 耗时 (s) |
|---|---|---|---|---|---|---|
| pre01_inspect | P01 | 是 | 4 | 1 | 1 | 82.17 |
| pre02_material_fields | P02 | 是 | 8 | 1 | 0 | 104.98 |
| pre03_jc_material | P03 | 是 | 17 | 3 | 0 | 97.63 |
| pre04_node_set | P04/G03 | 是 | 14 | 3 | 0 | 111.2 |
| pre05_boundary_velocity | P05 | 是 | 19 | 1 | 0 | 126.49 |
| pre06_contact | P06 | 是 | 10 | 1 | 0 | 97.12 |
| pre07_mesh_array | P08 | 是 | 13 | 2 | 0 | 103.36 |
| pre08_check_and_controls | P09/P10 | 是 | 17 | 1 | 0 | 148.7 |

“报错调用”只统计 MCP 层报错的调用；返回 failed 的 JobResult 不算在内，这类调用表现为同一工具的重复调用。

## 观察

- 编辑格式靠试：同一题里 create_entities / edit_keywords / mesh_ops 连续调用多次，例如 pre05 调了 11 次 create_entities，pre08 调了 9 次 edit_keywords。主要原因是工具说明只写了 `list[dict]`，没有给出每种 op 的字段示例。
- 旧别名和无关工具：8 题共有 24 次调用落在旧别名或 GUI 会话类工具上（inspect_keyword_deck、list_gui_sessions、list_capabilities 等），pre04 还启动了一个 GUI 会话。
- search_docs 调用 7 次，都因为没有配置 LSPP_KNOWLEDGE_INDEX 而失败。
- 同日第一次运行：4/8 成功，另外 4 题一次 lspp 调用都没有。原因是机器负载高时，lspp 还没启动完，Codex 会话就开始了；代理在没有工具的情况下直接作答。此后框架把 lspp 设为必需（`11f5da0`），本次就是修复后的运行结果。

## 未覆盖

- Claude 的同组运行：本机独立的 claude CLI 没有登录。
- 后处理 8 题、自动化 4 题。
- 每题只跑了一次，没有统计重复运行的方差。
