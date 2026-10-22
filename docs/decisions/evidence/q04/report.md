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
| 3. 掩码策略 alive / all / deleted 可选；极值附带实体 ID 与状态 | 通过 | `tests/test_field_metrics.py::test_mask_modes_and_extrema_with_id_and_state`，验证 alive、all、deleted 三种模式，极值返回附带单元 ID 与 1 起算状态号 |
| 故事：靶板所有单元、排除删除单元、找出最大值所在单元 | 通过 | `part_ids` 部件筛选：合成 `test_part_filter_story_target_plate`；公开语料（需 `LSPP_CORPUS_DIR`）`test_corpus_story_target_plate_maximum`：d3plot_projectile 靶板 part 2 三轴度最大单元 2840（1.6415，第 16 状态），逐单元与按张量定义的独立计算一致；不筛选时最大值是弹体单元 1681 |
| 壳在真实语料上与独立计算一致 | 通过 | `test_corpus_shells_match_independent_calculation`（登记 ID `shell_d3plot`，层平均后独立计算）；未做 LS-PrePost 原生对照，验收要求的是与独立计算一致 |

## 2.1 审阅修复（PR #82 审阅 P1-82a/b/c，Claude 2026-10-22 修复）
- `state` 改为 1 起算状态号；`-1` 或 `"last"`（默认）表示最后一个状态。0、超过状态数、其他负数、bool 和其他字符串在建作业前拒绝，不取模；状态数由共享 `lasso_backend.state_times` 只读时间步得到。测试：`test_state_is_one_based`、`test_state_out_of_range_refused_before_job`、`test_backend_field_refuses_out_of_range_state`；MCP 层用 StrictInt，true 或 1.0 不会被转成状态 1（`test_mcp_layer_does_not_coerce_state_or_part_ids`）。
- 测试不再写本机绝对路径：语料测试从 `tests/corpus/manifest.yaml` 登记 ID 和 `LSPP_CORPUS_DIR` 解析路径，未设置时 skip；作业目录放 tmp_path，不写入语料目录。
- 部件筛选：共享 `lasso_backend.field` 新增 `part_ids`（按 `part_ids`，文件只有标题时按 `part_titles_ids` 解析）；未知部件、部件中没有该族单元时明确失败。测试：`test_backend_field_selects_parts_by_user_id`、`test_part_filter_story_target_plate`、`test_part_filter_refusals`。
- 为此修改了 Claude 负责的共享实现：`lasso_backend`（`field` 的 `part_ids` 与越界拒绝、新增 `state_times`）、`export`（有筛选时元数据写 `part_ids`）、`invariants.CONVENTIONS`（补主应力、最大剪应力、平均应力定义，P2-82a）。下文第 3 节“未修改共享计算实现”的说法对修复后的版本不再成立。
- 壳和多积分点单元先对存储点/层求平均再计算不变量（工具说明已注明，P2-82c）。

## 3. 实现与边界说明
- 新增适配层 Mixin `src/ls_prepost_mcp/field_metrics_tools.py`，实现目标工具 `extract_field`。
- 直接复用 Claude 负责的 `domain.results.invariants` (`invariants`, `masked`, `extrema`, `CONVENTIONS`, `QUANTITIES`) 与 `domain.results.lasso_backend` (`field`, `FAMILIES`)，未修改共享计算实现。
- `src/ls_prepost_mcp/service.py` 仅继承 `FieldMetricsTools`，未改动任何现有方法主体。
- `src/ls_prepost_mcp/data/operations.json` 注册 target tool `extract_field`，旧入口保持别名到 v0.6。
- 完整支持输出 CSV 与 NPZ 工件，并使用 `read_field` 校验往返一致性。
- 在真实语料库 `order_d3plot`（壳单元）与 `d3plot_projectile`（穿靶实体与失效单元删除）上完成冒烟验证。

## 4. 本地测试与工具检查
- 修复后（2026-10-22，lspp-py311）：`LSPP_CORPUS_DIR=<公开语料根> pytest tests/test_field_metrics.py` 27 passed；不设该变量 25 passed、2 skipped
- 修复后语料核对：新工具与直接调用共享 `lasso_backend.field` 逐单元比较（d3plot_projectile 实体、lsdyna_bird_strike 壳；5 个量；状态 1、末状态、-1；有/无部件筛选），max|diff| = 0，NaN 位置与极值 ID/值一致
- 以下为原作者修复前的记录：
- `pytest tests/test_field_metrics.py`: 9 passed
- `pytest tests/test_operation_registry.py`: 6 passed
- `python tools/validate_tasks.py`: OK
- `python tools/gen_docs.py --check`: OK
- `python tools/check_doc_links.py`: 854 checked, no missing files
- `python tools/validate_tool_migration.py`: 154 registered tools OK
- `ruff check src/ tests/ tools/`: All checks passed
