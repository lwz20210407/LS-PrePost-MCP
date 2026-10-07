# Q04 验收验证报告：工程量与失效掩码 (Field Metrics & Failure Mask)

## 1. 任务背景与目标
- **任务 ID**: Q04 (M2 / T1 / release v0.5)
- **开发者**: 反重力 (antigravity)
- **AO 会话**: `ls-prepost-mcp-agy-3` (Harness: `agy`)
- **分支**: `antigravity/Q04-field-metrics`
- **派发 PR**: [#79](https://github.com/lwz20210407/LS-PrePost-MCP/pull/79)
- **目标工具**: `extract_field`

## 2. 验收标准满足情况

| 验收项 | 状态 | 验证方法与证据 |
|---|:---:|---|
| 1. Mises、主应力、三轴度、Lode 参数、Lode 角、等效塑性应变在实体与壳上与独立计算一致 | 通过 | `tests/test_field_metrics.py::test_independent_calculation_match_solids` 与 `test_independent_calculation_match_shells`，基于张量理论公式独立计算，数值完全吻合 |
| 2. 公式定义（尤其 Lode 的符号约定）写进结果元数据 | 通过 | `tests/test_field_metrics.py::test_metadata_and_lode_conventions`，返回结果 `conventions` 及 CSV/NPZ 元数据完整包含 Lode 参数公式、Lode 角公式与未定义 NaN 约定 |
| 3. 掩码策略 alive / all / deleted 可选；极值附带实体 ID 与状态 | 通过 | `tests/test_field_metrics.py::test_mask_modes_and_extrema_with_id_and_state`，验证 alive、all、deleted 三种模式，极值返回附带单元 ID 与具体状态 |

## 3. 实现与边界说明
- 新增适配层 Mixin `src/ls_prepost_mcp/field_metrics_tools.py`，实现目标工具 `extract_field`。
- 直接复用 Claude 负责的 `domain.results.invariants` (`invariants`, `masked`, `extrema`, `CONVENTIONS`, `QUANTITIES`) 与 `domain.results.lasso_backend` (`field`, `FAMILIES`)，未修改共享计算实现。
- `src/ls_prepost_mcp/service.py` 仅继承 `FieldMetricsTools`，未改动任何现有方法主体。
- `src/ls_prepost_mcp/data/operations.json` 注册 target tool `extract_field`，旧入口保持别名到 v0.6。
- 完整支持输出 CSV 与 NPZ 工件，并使用 `read_field` 校验往返一致性。
- 在真实语料库 `order_d3plot`（壳单元）与 `d3plot_projectile`（穿靶实体与失效单元删除）上完成冒烟验证。

## 4. 本地测试与工具检查
- `pytest tests/test_field_metrics.py`: 9 passed
- `pytest tests/test_operation_registry.py`: 6 passed
- `python tools/validate_tasks.py`: OK
- `python tools/gen_docs.py --check`: OK
- `python tools/check_doc_links.py`: 854 checked, no missing files
- `python tools/validate_tool_migration.py`: 154 registered tools OK
- `ruff check src/ tests/ tools/`: All checks passed
