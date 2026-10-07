# Q03 验收验证报告：场数据提取 (Field Data Extraction)

## 1. 任务背景与目标
- **任务 ID**: Q03 (M2 / T1 / release v0.5)
- **开发者**: 反重力 (antigravity)
- **AO 会话**: `ls-prepost-mcp-21` (Harness: `agy`)
- **分支**: `antigravity/Q03-field-extraction`
- **派发 PR**: [#83](https://github.com/lwz20210407/LS-PrePost-MCP/pull/83)
- **目标工具**: `extract_field`

## 2. 验收标准满足情况

| 验收项 | 状态 | 验证方法与证据 |
|---|:---:|---|
| 1. 输出 CSV/NPZ，元数据包含量、分量、单位、状态、时间、层/积分点、坐标系、后端 | 通过 | `tests/test_field_extraction.py::test_acceptance_1_all_eight_metadata_fields_in_csv_and_npz`，CSV `# key: value` 头部及 NPZ 字典经 `read_field` 往返完整校验 8 项关键语义元数据 |
| 2. 实体与壳各一个用例；LSPP 与 LASSO 结果逐实体一致（容差内） | 通过 | `tests/test_field_extraction.py::test_acceptance_2_solid_cross_check_element_by_element`（实体用例）与 `test_acceptance_2_shell_cross_check_element_by_element`（壳用例），逐实体比较数值差异 `<= 1e-4`；积分点 2-8 明确拒绝，壳层语义保持真实 |
| 3. 删除单元按 Q04 掩码策略处理并在元数据中注明 | 通过 | `tests/test_field_extraction.py::test_acceptance_3_failure_masking_modes_and_metadata`，覆盖 `alive`、`all`、`deleted` 策略，删除数及有效数均记录进元数据及结果 |

## 3. 用户故事验证
- **故事**: *把第 20 个状态 Part 3 所有单元的应力六分量导出成 CSV*
- **测试**: `tests/test_field_extraction.py::test_user_story_state_20_part_3_stress_six_components_to_csv`
- **结果**: 准确筛选出 Part 3 的单元，导出包含所有六分量 (`sxx, syy, szz, sxy, syz, szx`) 的 CSV 文件，列格式为 `id,sxx,syy,szz,sxy,syz,szx,alive`，头部完整附带元数据。

## 4. 真实原生与语料库验证
- **原生 Headless 运行**: 在总调度获准的串行原生窗口中，成功运行 `test_native_live_field_extraction`（LS-PrePost 4.10 `-nographics` 模式），进程正常退出，无残留，并及时向 AO 及调度释放窗口。
- **真实语料**: 在 `d3plot_projectile`（穿靶实体与失效单元删除）与 `order_d3plot`（壳单元）上完成零件过滤与场提取验证。

## 5. 本地测试与工具检查
- `pytest tests/test_field_extraction.py`: 9 passed, 1 skipped (live native opt-in)
- `pytest tests/test_field_metrics.py`: 9 passed
- `pytest tests/test_operation_registry.py tests/test_results_lasso.py tests/test_results_export.py tests/test_core_contracts.py`: 63 passed
- `python tools/validate_tasks.py`: OK
- `python tools/gen_docs.py --check`: OK
- `python tools/check_doc_links.py`: 855 checked, no missing files
- `python tools/validate_tool_migration.py`: 154 registered tools OK
- `ruff check src/ tests/ tools/`: All checks passed
