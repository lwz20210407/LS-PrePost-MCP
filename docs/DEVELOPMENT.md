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

I11 的 local-book 在 corpus 清单的 restricted_sources 中仅登记 ID 与相对路径；默认 catalog 校验不展开书籍内容。书籍文件、索引、图像、数值结果及其他派生数据始终只保留本机仓库外，不提交、不公开。
