# 任务看板

由桌面 Codex 维护；范围、验收和完成状态以 [tasks.yaml](../tasks.yaml) 为准。2026-10-07 核对 main e41cf65。

## 本轮每人三项顺序队列

用户明确要求每人认领3–4项；本轮每人3项，一个AI同时推进一项。派发PR发布后临时认领，Ready旧头冻结等待Claude审阅，禁止自行合并main。验收和release未改。统一AO项目 `ls-prepost-mcp`；具体说明见本轮 `codex/dispatch-batch-20261007` 派发PR正文。

| 开发者 | 顺序 | 任务 | 分支 | 状态 |
|---|---|---|---|---|
| codex | 1 | I01 | codex/I01-atomic-process-start | 已派发，按队列认领 |
| codex | 2 | I03 | codex/I03-command-path-regression | 已派发，按队列认领 |
| codex | 3 | A05 | codex/A05-macro-parameters | 已派发，按队列认领 |
| cursor | 1 | Q01 | cursor/Q01-result-overview | 接续已有会话，6b8b6f0，待开实现PR |
| cursor | 2 | I05 | cursor/I05-index-source-coverage | 已派发，按队列认领 |
| cursor | 3 | A10 | cursor/A10-search-quality | 已派发，按队列认领 |
| antigravity | 1 | I02 | antigravity/I02-fieldspec-adapter | 已派发，按队列认领 |
| antigravity | 2 | Q03 | antigravity/Q03-field-extraction | 已派发，按队列认领 |
| antigravity | 3 | G04 | antigravity/G04-entity-identify | 已派发，按队列认领 |

## 已交审与保留事项

| 任务 / PR | 状态 |
|---|---|
| I01引用预算 / #81（998040d） | Ready；原始会话已移入统一AO项目，冻结待审 |
| Q04 / #82（a8d59c2） | Ready；冻结待审；Q03使用新分支merge其已验证依赖，不改旧头 |
| Q08 / #71（7a92bca） | Ready；待审，保持partial |
| Q10/Q12 / #57（8b2a9a1） | Ready；待审，原会话已归统一项目 |
| I01 / #26、#72 | Ready；冻结待审 |
| I04 / #54；I03 / #76 | Ready；冻结待审，不冒充新头原生复跑 |
| I01 / #40；#56、#64、#67、#68、#70、#74、#75 | 已合并 |
| Q07 / #77 | Claude负责；已有Codex审阅，Claude执行合并；不抢占 |
| Q06 / AO ls-prepost-mcp-11 | Claude的原会话保留，不转派 |
| #63 | 已关闭，禁止复用其越界实现 |
| #73、#78–#80 | 历史协调/派发PR保留；本派发栈接续最新队列，合并时保留最新状态 |

## 并行边界与交接

- Codex拥有进程/命令/宏底座；Cursor拥有Q01薄适配与I05/A10索引/检索；反重力拥有新FieldSpec适配、Q03场提取和G04识别薄适配；共享核心仍由Claude维护。
- Q01复用原AO会话，不重复建分支。I05→A10、I02→Q03→G04按序交付；每项独立PR，未合依赖只用merge形成明确栈，不改旧Ready头。
- GitHub是任务和审阅记录；AO只负责启动、认领与回灌。每项本地相关测试真实记录，GitHub五项CI全绿才交付；无需GUI的部分持续推进，GUI/UU另等新窗口。
- F盘空间紧张，复用已锁定环境与语料，不复制全语料/全环境，原生进程串行，不能自行删除旧文件。看板不把待认领写成已开工。
