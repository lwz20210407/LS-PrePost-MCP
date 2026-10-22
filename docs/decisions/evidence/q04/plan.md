# Q04 实现计划：工程量与失效掩码 (Field Metrics & Failure Mask)

## 1. 开发者与任务信息
- **开发者**: 反重力 (antigravity)
- **AO Harness**: `agy`
- **AO 会话**: `ls-prepost-mcp-agy-3`
- **工作分支**: `antigravity/Q04-field-metrics`
- **派发 PR**: [#79](https://github.com/lwz20210407/LS-PrePost-MCP/pull/79)
- **任务 ID**: Q04 (M2 / T1 / release v0.5)

## 2. 目标与 tasks.yaml 验收标准
1. **量与一致性**: von Mises、主应力 (principal 1/2/3)、应力三轴度 (triaxiality)、Lode 参数 (lode_parameter)、Lode 角 / 参数 (lode_angle_rad, lode_angle_parameter)、等效塑性应变 (effective_plastic_strain) 在实体 (solid) 与壳 (shell) 上与独立计算/标准公式完全一致。
2. **元数据约定**: 计算公式与符号约定（尤其是 Lode 参数定义、undefined NaN 规则、应力分量顺序）写入结果元数据 `conventions`。
3. **失效掩码与极值**: 掩码策略可选 `alive` (默认)、`all`、`deleted`；极值 `extrema` 附带最大/最小值、有效单元计数以及极值对应的实体 ID 与状态。
4. **统一接口**: T1 仅使用既有目标工具名 `extract_field`，支持 LASSO 读取与已有有效性验证，返回 `JobResult/v1` 契约，保留向后兼容别名至 v0.6。

## 3. 文件边界与归属
- **拥有与新建**:
  - `src/ls_prepost_mcp/field_metrics_tools.py` (适配层 Mixin `FieldMetricsTools`)
  - `tests/test_field_metrics*.py`
  - `docs/decisions/evidence/q04/`
- **最小接线与配置**:
  - `src/ls_prepost_mcp/service.py`: 仅引入 `FieldMetricsTools` 并作为 `Service` 基类继承，不修改任何现有方法主体。
  - `src/ls_prepost_mcp/data/operations.json`: 添加 `extract_field` 运行时条目 (`domain: results, target: extract_field, task_id: Q04, legacy_until: null`)。
  - `tasks.yaml`: 仅更新 Q04 的真实状态、gaps 与 evidence，不改 owner、验收或看板。
- **只读复用与禁止修改**:
  - 直接复用 `domain/results/invariants.py` (`invariants`, `masked`, `extrema`, `CONVENTIONS`, `QUANTITIES`) 与 `domain/results/lasso_backend.py` (`field`, `FAMILIES`, `_element_values`)。
  - 禁止修改 Claude 负责的 `domain/results/` 下共享文件 (`invariants.py`, `lasso_backend.py`, `curves.py`, `mpp_shards.py`)。
  - 禁止修改 `engineering.py` (旧 #57 待审中)、`result_overview.py`、`config.py`、`engine/`、`native/`、`post_tools.py`。
  - 不新建 `extract_field_q04` 并行工具。

## 4. 实施步骤
1. 在派发 PR #79 提交认领评论（身份、分支、AO 会话、本计划相对路径）。
2. 实现 `FieldMetricsTools` mixin:
   - 实现 `extract_field(path, family, quantity, state=-1, mask="alive", units=None, ...)` 接口；
   - 包装为符合 `JobResult/v1` 标准的规范化返回，包含元数据、conventions、extrema、ids、values、mask、alive；
   - 支持实体 (solid) 与壳 (shell) 以及三维厚壳 (tshell)；
   - 严密校验输入合法性（family, quantity, mask, state, path），缺失或除零产生 NaN（不吞错误，不将缺失值置为 0）；
   - 保留与原有 `compute_stress_invariants` / `inspect_result_validity` 的一致性与兼容性。
3. 接线 `service.py` 与更新 `operations.json`。
4. 编写全面的单元与集成测试 `tests/test_field_metrics.py`:
   - 验证实体与壳上的各工程量计算精度与独立公式一致性；
   - 验证掩码策略 `alive` / `all` / `deleted` 正确筛选；
   - 验证极值查找正确匹配单元 ID 与状态；
   - 验证异常输入与退化情况（如纯静水压状态下的 NaN 处理）；
   - 验证 MCP 工具注册与 FastMCP 发现。
5. 运行本地完整验证（pytest, ruff, validate_tasks.py, gen_docs.py, check_doc_links.py）。
6. 生成独立证据 `docs/decisions/evidence/q04/evidence.json` 与 `report.md`。
7. 提交首个有意义 Commit（尾注 `Agent: antigravity`），推送分支，创建 Draft PR，执行 `ao session claim-pr <PR号>`。
8. 观察 CI 状态，修正任何问题直至五项 CI 全绿，转为 Ready 状态。
