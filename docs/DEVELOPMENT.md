# 开发指南

## 工作入口

只认 [tasks.yaml](../tasks.yaml)。每个开发项先声明任务 ID 或 I-ID；不匹配的需求写入 [backlog](../backlog.md)，里程碑结束再评估。只有用户明确要求立即插队才改变当前工作。范围与深度不能由实现者自行缩减验收标准。

M0 仅整理文档、校验、语料、实验与 M0-3 bug 修复，不重构 src、不新增工具。开发分支 restructure/v0.5；每个子项独立提交，里程碑结束开 PR 不合并。报告任务完成数和净增删行数，不再更新旧进度台账。

用户已明确授权 I02 在独立分支 codex/m1-contracts 立即先行：六个合同及工作流门槛转换以 L1 验证，M0 的远程门槛和 PR #1 范围保持不变。I02 的测试入口为 `pytest tests/test_core_contracts.py tests/test_workflow_gates.py tests/test_reference_workflow.py`。

I01 在 `codex/m1-engine` 继续，基于 I02 分支。普通单测自动跳过原生测试；原生执行需把 `LSPP_ENGINE_EXECUTABLE` 指向对应版本安装，将 `LSPP_ENGINE_FIXTURE` 指向 M0 原创八节点、三状态壳语料目录（input.k、d3plot、d3plot01），然后运行：

```shell
uv run pytest -m native tests/test_engine_native.py
```

4.13 跑全部七例；4.10 批处理和命令子集加 `-k "not queue_session"`。4.10 队列的模型来源读回问题已记录为 KI-048，版本能力表在启动前拒绝，不能通过取消来源验证来绕过。原生测试读取外部语料，所有执行副本与证据由 pytest 的 `--basetemp` 指向当次 scratch 目录；不得把语料或原生日志提交。

I03 的命令黄金输出、参数拒绝、语法集中约束、版本能力与脱离宿主包的 bridge 加载测试位于 `tests/test_native_commands.py`。新增选择/动画/云图命令必须进入 `native/commands.py`；版本判断进入 `native/versions.py`。原生回归额外核对稀疏用户 ID、缓冲区保存/恢复、状态 3 和 PNG。

## 可重复检查

```shell
uv run pytest
uv run --extra dev --extra results --extra pydyna pytest
uv run python tools/validate_tasks.py
uv run python tools/gen_docs.py --check
uv run python tools/check_doc_links.py
uv run python tools/fetch_corpus.py --check-registry
uv run --extra dev ruff check src tests
```

普通开发用 uv 默认 dev 依赖组。可选后端测试按实际导入跳过；验证最小安装时以 UV_PROJECT_ENVIRONMENT 指定新的仓库外环境。UV_CACHE_DIR、pytest cache_dir、--basetemp 必须指向本任务目录。不要复用会被 pytest 清空的旧 basetemp。

tools/gen_docs.py 生成 TASKS、TOOLS、README 能力表和 COMPATIBILITY 的版本策略部分。CI 校验生成物一致性；其他版本实测说明保留人工来源。tasks.yaml 的 ui_entry 已按既有 4.13.4 截图核正到可证实入口，截图身份保存在 ui_entry_audit；面板内子项不据此自动获得验收。

## 测试分层

- L1：CI 运行逻辑、数学、参数和产物合同；不启动 LSPP。
- L2：固定语料与真实 LSPP 的正反例、保存重开、数值与图像核对。M1/I04 将现有 tools/run_* 迁入 pytest -m native；M0 尚不把该命令列为现成能力。
- L3：M2–M4 的 Agent 自然语言场景评测，退出标准见 tasks.yaml。

原生记录必须含具体构建、输入 SHA256、精确源程序、请求关联、日志和独立产物检查。失败和未知状态保留证据，不自动重放不确定的修改。需要 GUI 的验证集中在用户确认的时间窗，实验脚本见 tools/experiments；锁屏与实际远程控制软件的断开由用户操作。本机使用 UU，断开时间窗由用户确认并单独记录，不要求配置 RDP。

## 数据与知识

回归语料登记在 tests/corpus/manifest.yaml：仅保留公开语料 ID 和相对路径，私有条目仅保留 ID。`LSPP_CORPUS_DIR` 指向已整理的统一根目录，其下同时有 `public-keyword/manifest.json` 和 `public-results/manifest.json`。来源 URL、许可、SHA256 和特征从这两份外部清单读取，不在仓库重复保存。不复制、重新下载或执行收集的文件；许可不明、GPL/NC 等原始文件均留在仓库外。

`tools/fetch_corpus.py` 保留旧命令名，现为只读定位/校验入口：`--list` 列出 ID 与相对路径；默认核对目录与外部清单；`--verify-all` 流式校验外部清单列出的全部文件；指定 ID 只校验该引用范围。它不会修复、改写或下载缺失文件，且拒绝越界路径和指向根目录外的链接。不要把环境变量设成 public-keyword 子目录；I07 独立分支的旧测试入口在 M3 集成时适配此统一约定，M0 不改动其代码。

私有 `fangzhen`、`deployed_wings` 只登记 ID；`large_private` 保留为 deployed_wings 的旧场景 ID。私有路径及其派生数据不入库，本公共语料入口不猜测私有绑定。tasks.yaml 的 corpus: 引用给出覆盖任务，登记和校验哈希不改变任务完成状态。

`include_contact`、`shell_d3plot`、`solid_d3plot`、`binout_forces`、`mpp_binout` 已指向统一目录中的具体输入；力库清单包含 RCFORC/SECFORC，MPP 分片已可定位。相应数值、原生交叉验证及 MPP 与单机等价性仍按 Q06 的验收标准完成。

## 迁移约束

保留已验证命令、原生坑、产物身份校验、结果数学和旧接口。M1 建立 core/engine，再按领域迁移；重复实现改为别名并删除旧主体。embedded 保留兼容应用内 Python 的语法。禁止下层导入上层，由 M1 的 import-linter 强制。

capabilities.json 与 development_plan.json 目前仍被运行时路由读取，M0 原样冻结，禁止手改。M1 将职责拆开：任务由 tasks.yaml 定义，运行时操作元数据由 registry 生成。旧 release_progress.json 与 progress_dashboard.py 已归档停用；不得继续将其当成验收分母。

原生错误与规避集中维护在 [KNOWN_ISSUES](KNOWN_ISSUES.md)。不得隐式修改安装配置、UAC、全局快捷键或覆盖用户源模型。
## I04 统一验收入口

`tests/test_native_acceptance.py` 自动收集当前全部 55 个 tools/run_* 脚本，保留原脚本的工程正反例断言。program_acceptance 的 batch/GUI 和 parameter_study 的 file/GUI 分开，得到 57 个用例。普通 pytest 只收集并跳过它们。先运行 `pytest tests/test_native_acceptance.py --collect-only -q` 查看用例 ID。

在确认的 GUI 时间窗和完整输入配置下，一条命令运行并生成 `<新建的外部目录>/report.md`、report.json 和各用例的 verified.json：

```shell
uv run pytest -m native --run-native --native-strict --native-gui --native-executable "<LSPP路径>" --native-fixture "<M0原创语料目录>" --native-inputs "<本地输入配置.json>" --native-output "<新建的外部目录>"
```

`--native-gui` 表示已有用户确认的可见桌面时间窗；省略时相关用例跳过，strict 模式则失败。输入不足也同样区分 skip/failed，报告不会把它们算为通过。输出目录必须在仓库外且尚不存在；运行器设置独立临时目录，并只清理本轮记录、进程身份仍匹配的会话。超时终止本轮脚本及已确认身份的子进程，保留日志与失败证据。

`LSPP_EXECUTABLE`、`LSPP_ENGINE_FIXTURE` 可替代路径选项；`LSPP_NATIVE_INPUTS` 指向仓库外 JSON，以完整用例 ID 为键，值为 CLI 参数对象。公开输入可写 `{"source":{"corpus":"solid_d3plot"},"part":1}`，通过现有登记和 LSPP_CORPUS_DIR 解析；part、states、bounds 必须按实际语料核对。私有输入在该本地 JSON 中显式提供路径，仓库的 corpus 清单仍只登记私有 ID。运行器不猜私有路径、不下载、不向仓库复制语料。

运行器掌管 workspace/executable/output 和会缩减验收或保留进程的开关，输入配置不能覆盖这些选项。每例必须正常退出并产生新的非空验收报告，报告带 status 时必须 succeeded；native inventory 的每个子结果都须成功。负例结果保留，由原验收脚本的明确断言核对。已验证报告附带源脚本和证据 SHA256。

无 GUI 的三项工程/工作流验收也走同一入口，CI 使用：

```shell
uv run pytest tests/test_native_acceptance.py -m native -k "engineering_unit or workflow_gate or parameter_study_acceptance.file" --run-native --native-strict --native-output "<新建的外部目录>"
```

I04 在全量原生用例完成前保持 partial。用户已把 M0 剩余 13 个 UU 远程格转入 I04，不能用默认桌面结果替代。

### UU 远程格的捕获与确认

13 格由 `tests/test_native_remote.py` 收集。只在用户明确安排的窗口内使用 `--remote-capture --native-gui`，并提供 `--native-executable-410`、`--native-fixture` 和 `--remote-confirmation`。确认文件放仓库外，捕获前为 `{"environment":"UU","phase":"armed","operator_ready":true}`；程序预留 30 秒供用户断开 UU。

捕获后必须由用户确认实际断开区间，将本地确认文件改为 confirmed，含 operator_confirmed=true、disconnected_from/disconnected_until 两个 Unix 时间戳。随后用同一 pytest 入口传 `--remote-evidence <原捕获目录>` 和确认文件，在新的 native-output 目录验证。未确认区间不会判为通过；记录/每阶段产物哈希变化也会失败。

这些用例核验的是实验记录及远程条件，原生各 lane 的 succeeded/failed 原样保留在报告，不能把“记录已验证”解释成不支持的 runc/宏路线已成功。每阶段保留自己的回执、模型和媒体，后续阶段不能用同名文件覆盖前一阶段证据。

远程证据用例在 pytest 中标为 xfail，在 report.md/JSON 中标为 evidence_only，并逐项显示
execution / PNG / MP4 状态。普通 pytest 即使设置安装路径环境变量也不会启动原生 fixture，
必须明确传 --run-native；显式路径选项优先于 LSPP_ENGINE_EXECUTABLE，再其次为 LSPP_EXECUTABLE。
[已有验收的历史附件](decisions/evidence/i04/report.md) 不替代未完成的 GUI/UU 回归。


I11 的 local-book 在 corpus 清单的 restricted_sources 中仅登记 ID 与相对路径；默认 catalog 校验不展开书籍内容。书籍文件、索引、图像、数值结果及其他派生数据始终只保留本机仓库外，不提交、不公开。

I08 的运行时注册表为 `src/ls_prepost_mcp/data/operations.json`；新增或迁移操作更新此处，再运行 gen_docs.py。兼容名称和 canonical operation_id 均需通过同一签名/路由验证。CI 执行 `uv run lint-imports --no-cache`；本地也使用 no-cache，避免在仓库生成缓存。

import-linter 固定 2.6：2.7–2.9 的 rich>=14.2.0 与已验证 LASSO2.0.4 的 rich==13.* 冲突，保留数值后端锁定，选择可共存版本。约束使用官方的 protected/forbidden 合同（https://import-linter.readthedocs.io/en/v2.6/contract_types.html）。I02 的六个合同字段未改变。
