# G04 验收验证报告：统一实体识别 (Entity Identify)

## 1. 任务背景与目标
- **任务 ID**: G04 (M2 / T1 / release v0.5 / general)
- **开发者**: 反重力 (antigravity)
- **AO 会话**: `ls-prepost-mcp-25` (Harness: `agy`)
- **分支**: `antigravity/G04-entity-identify`
- **派发 PR**: [#83](https://github.com/lwz20210407/LS-PrePost-MCP/pull/83)
- **PR 编号**: [#98](https://github.com/lwz20210407/LS-PrePost-MCP/pull/98)
- **目标工具**: `query_entities`
- **对应 UI 路径**: `FEM > Element Tools > Identify`

## 2. 验收标准满足情况

| 验收项 | 状态 | 验证方法与证据 |
|---|:---:|---|
| 1. 节点 / 单元 / Part 的 ID、坐标、连接、所属 Part / 材料、指定状态的结果值 | 通过 | `tests/test_entity_identify.py::test_acceptance_1_node_identify`、`test_acceptance_1_element_identify`、`test_acceptance_1_part_identify`，全量验证节点（坐标、连接、所属 Part、位移/速度结果）、单元（节点连接、形心、Part、材料、六分量应力/Mises/塑性应变）、Part（单元分布、节点列表、包围盒、活动/失效单元统计） |
| 2. 结果值与 Q03 同一量一致 | 通过 | `tests/test_entity_identify.py::test_acceptance_2_equivalence_with_q03_solid`、`test_acceptance_2_equivalence_with_q03_shell`，同一实体单元（实体 5 在状态 20、壳 101 在状态 10）的 von Mises 应力与 Cauchy 分量与 Q03 `extract_field` 严格等价（误差 `<= 1e-7`） |

## 3. 用户故事验证
- **故事**: *节点 1001 的坐标和它在第 30 个状态的位移是多少？属于哪个 Part？*
- **测试**: `tests/test_entity_identify.py::test_user_story_node_1001_displacement_and_part_at_state_30`
- **结果**: 一次查询直接返回节点 1001 参考坐标 `[10.0, 20.0, 30.0]`，第 30 状态位移矢量 `[1.2, 2.4, 3.6]` 与幅值，以及所属 Part ID `[3]` 和 Part 名称 `["part_3"]`。

## 4. 关键字模型与语料库验证
- **关键字卡片验证**: `test_keyword_deck_identify_nodes_and_elements` 测试从标准 `*.k` 卡片解析网格，正确提取 `*PART` 与 `*MAT_*` 卡片的材料 ID 与名称，对状态结果显式返回需 d3plot 数据库说明，不伪造数据。
- **公共语料库验证**: `test_public_corpus_d3plot_projectile` 验证穿靶模型 `d3plot_projectile`，成功查询弹体 (Part 1) 与靶板 (Part 2) 单元及形心，并与 Q03 在相同单元/状态下的 Mises 应力严格对齐。

## 5. 本地测试与工具检查
- `pytest tests/test_entity_identify.py`: 12 passed
- `pytest tests/test_field_extraction.py`: 9 passed
- `pytest tests/test_field_metrics.py`: 9 passed
- `python tools/validate_tasks.py`: OK
- `python tools/validate_tool_migration.py`: 155 registered tools OK
- `python tools/gen_docs.py --check`: OK
- `python tools/check_doc_links.py`: 855 checked, no missing files
- `ruff check src/ tests/ tools/`: All checks passed
