# Q03 实现计划：场数据提取 (Field Data Extraction)

## 1. 开发者与任务信息
- **开发者**: 反重力 (antigravity)
- **AO Harness**: `agy`
- **AO 会话**: `ls-prepost-mcp-21`
- **工作分支**: `antigravity/Q03-field-extraction`
- **派发 PR**: [#83](https://github.com/lwz20210407/LS-PrePost-MCP/pull/83)
- **任务 ID**: Q03 (M2 / T1 / release v0.5)

## 2. 目标与 tasks.yaml 验收标准
1. **语义元数据输出**: 输出 CSV/NPZ，元数据完整包含 8 项关键语义信息：量 (quantity)、分量 (component)、单位 (units)、状态 (state)、时间 (time)、层/积分点 (layer/integration_point/points)、坐标系 (coordinate_system)、后端 (backend)。
2. **跨后端逐实体一致性**: 实体 (solid) 与壳 (shell) 各一个用例，LSPP (原生) 与 LASSO 结果逐实体一致（容差内，`max_diff <= 1e-4`）；实体积分点 2-8 原生调用返回错值按规范拒绝；壳层来源真实保留（如 mid/inner/outer 与存储积分点），不进行虚假换算。
3. **失效单元掩码**: 删除单元按 Q04 掩码策略 (`alive`, `all`, `deleted`) 处理并在结果及元数据中明确注明。
4. **用户故事与零件筛选**: 支持导出指定状态（如第 20 个状态）、指定零件（如 Part 3）所有单元的应力六分量 (`sxx, syy, szz, sxy, syz, szx`) 至 CSV。

## 3. 文件边界与归属
- **拥有与修改**:
  - `src/ls_prepost_mcp/field_metrics_tools.py`：扩展适配层 Mixin `FieldMetricsTools`，支持全 8 项元数据、多应力分量导出、零件/实体过滤、原生实体积分点 2-8 拒绝及双后端逐实体对照。
  - `tests/test_field_extraction.py`：Q03 专属单元与集成测试套件。
  - `docs/decisions/evidence/q03/`：包含 `plan.md`、`evidence.json`、`report.md`。
- **只读复用与禁止修改**:
  - 严守边界：Claude 负责的 `domain/results/`（`invariants.py`、`lasso_backend.py`、`export.py`、`curves.py`、`mpp_shards.py`）与 `domain/model/` 保持只读，严禁修改。
  - 复用既有目标工具 `extract_field`，不新建同名或并行工具。
  - 原生支持复用 `src/ls_prepost_mcp/native_results.py` 的 SCL 执行与解析通道。

## 4. 实施与验证步骤
1. 基于最新 `main` (`e41cf65`) 分支，通过 merge 接入精确依赖提交 `a8d59c2` (PR #82)。
2. 扩展 `field_metrics_tools.py`：
   - 提取并组织 8 项语义元数据（量、分量、单位、状态、时间、层/积分点、坐标系、后端）；
   - 支持多分量 Cauchy 应力六分量导出；
   - 支持 `part_ids` 与 `entity_ids` 过滤；
   - 明确拒绝原生 solid 积分点 2-8（抛出规范错误信息）；
   - 支持 `cross_check` 对比原生与 LASSO 数值。
3. 编写专属测试 `tests/test_field_extraction.py`：
   - 验证 8 项元数据在 CSV 与 NPZ 中往返完整性；
   - 验证实体与壳用例下 LSPP 与 LASSO 逐实体一致性；
   - 验证实体积分点 2-8 明确拒绝；
   - 验证壳层语义；
   - 验证用户故事（第 20 状态、Part 3 单元六分量 CSV 导出）；
   - 验证真实语料库（`d3plot_projectile` 实体与删除单元，`order_d3plot` 壳单元）。
4. 在受控原生窗口完成 LS-PrePost 4.10 headless 模式实测验证并释放窗口。
5. 更新 `tasks.yaml`、生成证据文件并运行完整本地校验。
