# G04 实现计划：统一节点/单元/Part 实体识别 (Entity Identify)

## 1. 开发者与任务信息
- **开发者**: 反重力 (antigravity)
- **AO Harness**: `agy`
- **AO 会话**: `ls-prepost-mcp-25`
- **工作分支**: `antigravity/G04-entity-identify`
- **派发 PR**: [#83](https://github.com/lwz20210407/LS-PrePost-MCP/pull/83)
- **PR 编号**: [#98](https://github.com/lwz20210407/LS-PrePost-MCP/pull/98)
- **任务 ID**: G04 (M2 / T1 / release v0.5 / general)
- **目标工具**: `query_entities`
- **UI 路径**: `FEM > Element Tools > Identify`

## 2. 目标与 tasks.yaml 验收标准
1. **实体识别全量查询 (Acceptance 1)**:
   - 节点 (Node): user ID、参考坐标 (reference) 与变形坐标 (deformed)、连接单元 (connected elements)、所属 Part (part_ids / part_names)、指定状态的结果值 (位移矢量与幅值、速度矢量与幅值)。
   - 单元 (Element): solid / shell / beam / tshell 用户 ID、单元类型、节点连接 (connectivity node_ids)、节点坐标与形心 (centroid)、所属 Part (part_id / part_name)、材料参考 (material_id / material_title，若 d3plot 独占未存则显式声明说明，不伪造 ID)、指定状态结果值 (Cauchy 应力六分量、von Mises 应力、静水压、三轴度、有效塑性应变)。
   - Part: 用户 Part ID、名称/标题 (title)、材料参考、单元总数与类型分布、包含节点总数与 ID 列表、空间包围盒 (bounding box) 与形心、指定状态存活/删除单元统计。
2. **与 Q03 场提取数值完全等价 (Acceptance 2)**:
   - 对同一实体单元/壳单元，在指定状态下的 von Mises 应力、Cauchy 应力分量 (`sxx` 等) 与 Q03 `extract_field` 计算结果完全一致 (`max_diff <= 1e-6`)。
3. **用户故事验证 (User Story)**:
   - “节点 1001 的坐标和它在第 30 个状态的位移是多少？属于哪个 Part？”经由单次 `query_entities` 查询准确输出。
4. **关键字模型兼容性**:
   - 支持直接从标准关键字卡片 (`*.k`, `*.key`) 查询节点、单元与 Part，提取卡片材料与截面信息；对状态结果明确注明需 d3plot 数据库，不伪造不存在的仿真步数据。

## 3. 文件边界与归属守则
- **新加与专属文件**:
  - `src/ls_prepost_mcp/entity_identify.py`：新适配层 Mixin `EntityIdentifyTools`，实现统一 `query_entities`。
  - `tests/test_entity_identify.py`：G04 专属测试套件，全面覆盖验收标准、用户故事、等价性及边界测试。
  - `docs/decisions/evidence/g04/`：`plan.md`、`evidence.json`、`report.md`。
- **跨范围最小接线（仅限两处）**:
  - `src/ls_prepost_mcp/service.py`：引入 `EntityIdentifyTools` 并添加至 `Service` 继承列表。
  - `src/ls_prepost_mcp/data/operations.json`：注册 `query_entities` 目标工具条目。
  - `tools/tool_migration_map.yaml`：注册 `query_entities` 迁移映射。
- **只读与严格隔离**:
  - Claude 负责的 `domain/model/`、`domain/results/`、`src/ls_prepost_mcp/model_target_tools.py` 严格保持只读，不进行任何修改。
  - 纯复用 `domain.results.lasso_backend`、`domain.results.invariants` 与 `domain.model.operations.inspect_deck`。

## 4. 实施与验证步骤
1. 从最新 `main` (`e41cf65`) 分支，通过 merge 接入精确依赖 Q03 `d499b0c`。
2. 实现 `EntityIdentifyTools` 适配层与严格契约 `JobResult/v1` 返回格式。
3. 最小跨范围接线到 `service.py`、`operations.json` 与 `tool_migration_map.yaml`。
4. 编写并运行 `tests/test_entity_identify.py`，全部测试通过。
5. 推送并建立 Draft PR #98，通过 `ao session claim-pr 98` 认领。
6. 更新 `tasks.yaml` 状态为 `done` 并补充证据链条。
7. 运行 `tools/gen_docs.py`、`tools/validate_tasks.py`、`tools/validate_tool_migration.py`、`tools/check_doc_links.py` 及 `ruff check` 全量静态验证。
8. 转换为 Ready PR 并等待 GitHub CI 全绿。
