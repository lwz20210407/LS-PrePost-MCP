# A08 安装资产配方适配

派发来源：[PR #94](https://github.com/lwz20210407/LS-PrePost-MCP/pull/94)。A08 保持 partial；这里交付安装目录到配方入口的适配，不改变 30 个配方各有 L2 的发布验收。

## 使用合同

`find_recipe(include_candidates=True)` 从现有安装 catalog 枚举全部 `kwtemplate/**/template.k` 和 `kwfilter/**/*.txt`，复用安装 API。默认查询仍只列原五个已验证配方。排序、limit 和旧语言 channel 筛选保持；安装项 `channel=null`、`adapter_kind=installed_template|installed_filter`、`task_id=A08`，不会混入 cfile/python 等通道查询。安装项没有原生 `execution_modes` 或已验证版本声明。

外部配置使用 `LSPP_TEMPLATE_ROOT`，或现有 Settings 的显式安装 executable。未配置、不可用或无 catalog 条目时发出 RuntimeWarning，已有配方和 JSON 查询继续工作；不会启动安装探测进程。带空格的名称、相对路径、template/filter、installed、安装/模板/过滤器可供关键词检索。返回数量仍受 limit 限制，完整目录以旧 `list_installation_assets` 为准。

每个成功描述的候选给出 `installed:<资源ID>@<内容SHA256>` 引用，可原样传入 `run_recipe`。哈希固定模板或过滤器内容，变化即拒绝并要求重新发现。`installed:<资源ID>` 也可用，含义是重新解析当前资源，不保证上次发现的内容。缺失 ID 拒绝；每次运行重新读取参数和来源，执行前后复核目录映射、输入及可选 info.txt 身份，不使用缓存能力结论。info.txt 是本次调用的说明依赖，其哈希随结果保留，但不包含在发现引用的模板哈希中。

模板请求：

```python
run_recipe(reference, parameters={
    "values": {"T": 20},
    "units": "调用者明确声明的单位制",
    "native_check": False,
}, model=None)
```

- `units` 必填，非空且最多 100 字符；只声明单位，不转换或猜测安装资源单位。
- `values` 默认 `{}`。schema 来自 `describe_installed_template` 的实际 R/I/S 声明、标签、表达式及默认值；键按旧 API 规则不区分大小写，但重复大小写键拒绝。未知参数、非有限数、布尔数字、非整数 I 参数、不合规字符串拒绝。
- schema 展示的依赖表达式默认值仅用于说明。执行只传显式覆盖值，由既有求值器重新计算依赖，避免覆盖 T 后仍使用旧 DOUBLE 默认值。
- `native_check` 必须是布尔值，默认 false。true 时由 `instantiate_installed_template` 委托 `inspect_model` 显式 batch 重开；没有 NODE 的 fragment 保持未验证。无求解器验证。
- `model` 是显式 keyword 路径，可选。合并复用旧 API 的 CONTROL/DATABASE 替换、INCLUDE/未解析参数限制及路径权限边界；输出新 model.k，不改输入。

过滤器请求：`run_recipe(reference, model=keyword_model)`；parameters 只能为 None 或空对象。不接受 values、units、native_check。复用 `apply_keyword_filter` 返回原 `block_index`/`keyword`，在真实作业目录写 filter-result.json，包含过滤器与模型身份。它只选择关键字类别，既不删除模型，也不判定几何/工程有效性。作业的 dimensionless 标签仅表示索引选择，不推断模型单位。

所有安装请求在创建作业前拒绝 session_id（包括空串）、runc 和 d3plot。发现/离线生成不启动 LS-PrePost。解析错误或旧 API 不能生成 KEYWORD/END 产物的条目保留为 `support=unsupported` 并附具体原因；可适配项为 `support=offline_adapter`。两者均不升级为 T2。

返回 JobResult/v1，operation=run_recipe；data 包括 inputs、安装来源、实际请求/求值、验证范围和 native_reopen 状态；artifacts 保留产物 SHA256，evidence 指向作业记录。生成成功仅证明离线产物合同，`solver_validated=false`，`native_mesh_verified` 只有旧重开成功时才为 true。原安装四入口、YAML/JSON 与宏别名保持原接口。

## 原创夹具与覆盖

测试来源均为仓库内原创字符串，临时构建安装树；不读取本机厂商安装、真实网络或私有语料。

| 清单范围 | 结果及边界 |
| --- | --- |
| 原创参数模板、材料过滤器各 1 个 | 新旧入口生成内容、参数依赖、匹配索引等价 |
| 另外 6 个原创模板目录 | 所有 catalog 条目参与发现，筛选/排序/limit 可重复 |
| 错误声明、循环、未解析变量、不安全表达式、缺 KEYWORD/END | 各自明确 unsupported 和原因，启动前拒绝 |
| R/I/S 参数、单位、未知键、非有限数、布尔值、上下文 | 正反例覆盖，错误请求不创建作业 |
| 模板/过滤器/模型变更、消失、配置根更换 | 发现引用或执行中身份复核失败 |
| 安装路径与 info.txt 符号链接越界 | 支持符号链接的平台执行；不具权限时明确 skip |
| fragment、模型合并、原生委托成功/失败 | 离线或 mock 验证；mock 不计 L2 |
| 真实厂商安装清单与每个资产的 L2 | 未提供授权真实清单，未测；不以原创夹具推断全量覆盖 |

实现位于 [installed_recipes.py](../../../../src/ls_prepost_mcp/automation/installed_recipes.py)，仅在 [recipes.py](../../../../src/ls_prepost_mcp/automation/recipes.py) 接线；回归见 [离线测试](../../../../tests/test_installed_recipes.py) 和 [显式原生测试](../../../../tests/test_installed_recipes_native.py)。未修改安装解析/执行实现、共享合同、模型/结果核心、服务注册及并行任务文件。

## 验证记录

基线 main `e41cf65551274c496f0bb1802f952d1a30e024b2`：新增的发现/执行两条回归均失败；旧安装入口已成功，因此证明是配方入口缺口。基线 [正式 CI](https://github.com/lwz20210407/LS-PrePost-MCP/actions/runs/37539391882) 全绿，不替代实现头 CI。

本地复用既有锁定环境；命令中的 `<scratch>` 为任务外部临时目录，不提交本机绝对路径、原生日志或厂商内容。实际本地测试与实现头 CI 结果由实现 PR 记录。

```text
python -m pytest tests/test_installed_recipes.py tests/test_installed_recipes_native.py tests/test_recipes.py tests/test_workflow_foundations.py tests/test_core_contracts.py tests/test_task_catalog.py tests/test_doc_links.py -q -p no:cacheprovider --basetemp <scratch>/green
python -m ruff check . --no-cache
lint-imports --no-cache
python tools/validate_tasks.py
python tools/gen_docs.py --check
python tools/validate_tool_migration.py
python tools/fetch_corpus.py --check-registry
python tools/check_doc_links.py
git diff --check
```

剩余 gap：真实安装逐项清单/支持/不支持/未测证据；各版本各模式 L2；30 配方发布门槛；session/GUI、许可证受限来源。原生执行必须另有 headless lease 与显式 --run-native；不复用旧授权。本适配不改变任务 acceptance、release、status、depends_on 或删除旧 gap。
