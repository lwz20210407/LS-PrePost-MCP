# 任务看板

由桌面 Codex 维护；范围、验收和完成状态以 [tasks.yaml](../tasks.yaml) 为准。2026-10-07 核对 main e41cf65。

## 顺序任务队列（持续续派）

用户明确要求每人认领3–4项；初始每人3项；用户随后明确要求持续有可推进任务，Codex现续派第4项I04，一个AI同时推进一项。派发PR发布后临时认领，Ready旧头冻结等待Claude审阅，禁止自行合并main。验收和release未改。统一AO项目 `ls-prepost-mcp`；具体说明见本轮 `codex/dispatch-batch-20261007` 派发PR正文。

| 开发者 | 顺序 | 任务 | 分支 | 状态 |
|---|---|---|---|---|
| codex | 1 | I01 | codex/I01-atomic-process-start | #86 Ready，CI五项通过，冻结待审 |
| codex | 2 | I03 | codex/I03-command-path-regression | #87 Ready，CI五项通过，仍partial |
| codex | 3 | A05 | codex/A05-macro-parameters | #88 Ready，CI五项通过，仍partial |
| codex | 4 | I04 | codex/I04-public-failure-diagnostics | 本续派PR；待AO认领 |
| codex | 5 | A08 | codex/A08-installed-recipe-integration | 安装资产配方归并；本派发发布后临时认领，由总调度启动唯一实现 worker |
| cursor | 1 | Q01 | cursor/Q01-result-overview | #84 Ready，CI五项通过，冻结待审 |
| cursor | 2 | I05 | cursor/I05-index-source-coverage | #89 Ready，CI五项通过，仍partial |
| cursor | 3 | A10 | cursor/A10-search-quality | AO会话23执行中 |
| antigravity | 1 | I02 | antigravity/I02-fieldspec-adapter | #85 Ready，CI五项通过，冻结待审 |
| antigravity | 2 | Q03 | antigravity/Q03-field-extraction | 本地d499b0c；发布诊断阻塞已提醒处理 |
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

## Codex I04 续派边界

I04 owner在tasks.yaml已为codex，保持原验收/状态不变。独立分支codex/I04-public-failure-diagnostics，先以#54冻结证据定位extra-keyword-064原生失败、extra-result-03后端状态数差异；新测试/诊断脚本/脱敏证据不覆盖#54旧记录。只跑经总调度串行安排的headless，用公开语料只读验证；GUI/UU继续等待新窗口。详情见本续派PR正文。

## 2026-10-08 A08 安装资产配方归并续派

承接冻结派发 #91（2df2f762f6a48c01ab65839956e6e53d8dd6cde0），保留 #83 及此前全部登记。其上表历史状态不覆盖后续 GitHub 交接：I04 #92 已 Ready，426f3245741e6e4912135e624f9dfbb62830350e 正式五项 CI 通过；Q03 #90 已 Ready；A10 继续原会话23，G04保留原会话25，均不重复创建。旧 Ready 头保持冻结。

A08 owner 新增为 codex，验收、release、depends_on: [I01]、status: partial 和 gaps 均不变。用户在 #83 的持续续派授权允许发布即临时认领，不等 Claude 合派发；审阅与合并权不转移。唯一实现分支 `codex/A08-installed-recipe-integration`，统一 AO project `ls-prepost-mcp`；本协调 worker 不实现业务代码或启动实现 worker。

核查依据：[配方模块](../src/ls_prepost_mcp/automation/recipes.py)、[安装资产 API](../src/ls_prepost_mcp/installation_assets.py)、[旧 JSON 回归](../tests/test_recipes.py)、[安装资产回归](../tests/test_workflow_foundations.py)。#13 已把 JSON 模板接入配方候选检索/执行并保留旧名，不重复迁移。真实断点是安装目录的 template.k / kwfilter txt 仅能经安装 API 使用，find_recipe 不发现安装资产，run_recipe 无安装资产引用路由。

实现独占：新 `src/ls_prepost_mcp/automation/installed_recipes.py`、`src/ls_prepost_mcp/automation/recipes.py` 的安装资产接线、新 `tests/test_installed_recipes.py`、必要专属原生测试 `tests/test_installed_recipes_native.py`、`docs/decisions/evidence/a08-installed/`。复用既有 catalog/describe/instantiate/apply，不复制解析器或核心读取器；installation_assets.py、programs.py/native_macros.py（冻结 A05 #88）、service/registry、Cursor 查询与索引/schema、反重力 G04/Q03、Claude 共享核心保持只读。实现者不改本看板/owner；任务事实如需更新仅提交 A08 的真实 evidence/gaps 及生成 TASKS，原验收/release/依赖/status 不变，保留并行修改。

离线先完成发现、真实候选元数据、参数/单位合同、现有执行适配和新旧结果等价测试；不把模板/过滤器假装为已验证 cfile，不以静态 alias 或元数据冒充执行。I01 已有程序引擎及安装实例化作业/可选 inspect_model 底座可复用；不依赖待完成 GUI 面板、G03 或共享计算新实现。原生 reopen 必须另向总调度申请唯一 headless lease，GUI/UU 不在本派发授权中。全量安装覆盖、30 配方各自 L2 和原有失败/未验证模式继续如实保留，不能因适配层交付宣布 A08 done。

执行要求以本分支自足派发 PR 正文为准：首个有效提交开 Draft 并 claim 实现 PR；本地相关测试和静态校验，exact head 正式五项 CI 全绿后 Ready 冻结交 Claude。私有/厂商内容及派生数据留外部配置，公开仅原创夹具与脱敏证据；复用现有环境、单原生 lease，不全量本地测试、不复制语料。只 merge，不改旧头、不合 main。
