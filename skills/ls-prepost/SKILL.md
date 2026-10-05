---
name: ls-prepost
description: Drive LS-PrePost through existing MCP tools for model inspection, bounded editing, results, rendering and scripts; verify backend, units, artifacts and task limits.
---

# LS-PrePost 意图路由

先查 `list_capabilities`、`probe_environment`，再按任务选择当前入口。表中 partial/todo 是完整任务状态；目标 v0.5 工具尚未注册时不可直接调用。

| ID / 意图 | 当前工具 | 状态 / 目标版本 |
|---|---|---|
| P01 模型检视 | `inspect_model`, `inspect_keyword_deck`, `list_parts`, `list_nodes`, `inspect_gui_mesh` | partial / v0.5 |
| P02 关键字卡片读改增删（Include 保真） | `update_keyword_fields`, `update_keyword_table_row`, `compose_keyword_deck` | todo / v0.5 |
| P03 材料 / 截面 / Part 创建与关联 | `create_elastic_material`, `update_elastic_material`, `move_elements_to_part` | partial / v0.5 |
| P04 集合创建 | `create_gui_entity_set`, `create_gui_segment_set`, `create_node_set_by_box`, `inspect_gui_entity_sets` | partial / v0.5 |
| P05 边界条件与载荷 | `create_gui_spc`, `create_gui_prescribed_motion`, `create_gui_segment_pressure`, `create_gui_nonreflecting_boundary`, `create_gui_nodal_load` | partial / v0.5 |
| P06 接触定义与初始穿透检查 | 未有专用工具；查知识库后评估明确授权的脚本 | todo / v0.5 |
| P07 规则网格生成 | `create_shell_plate`, `create_solid_box`, `create_solid_sphere`, `extrude_shell_part` | partial / v0.6 |
| P08 网格编辑 | `translate_gui_nodes`, `rotate_gui_nodes`, `set_gui_node_coordinates`, `merge_gui_duplicate_nodes`, `reverse_gui_shell_normals`, `renumber_gui_entities`, `create_gui_nodes`, `create_gui_elements`, `replace_gui_node`, `translate_mesh_nodes`, `rotate_mesh_nodes`, `transform_mesh_deck`, `merge_duplicate_mesh_nodes`, `move_elements_to_part` | partial / v0.5 |
| P09 模型检查 | `check_gui_keywords`, `check_gui_shell_quality`, `check_gui_solid_quality`, `inspect_mesh_quality`, `inspect_gui_mesh_quality`, `validate_model_references` | partial / v0.5 |
| P10 控制与输出卡 | `instantiate_installed_template`, `apply_keyword_filter` | todo / v0.5 |
| P11 保存并原生重开验证 | `export_keyword`, `checkpoint_gui_session` | partial / v0.5 |
| Q01 结果概览 | `inspect_d3plot_scl`, `inspect_d3plot_database`, `inspect_result_fields`, `inspect_binout`, `inspect_binout_variable`, `inspect_lsreader`, `inspect_dpf_results` | partial / v0.5 |
| Q02 云图出图 | `render_gui_field`, `render_snapshot` | partial / v0.5 |
| Q03 场数据提取 | `extract_native_fields`, `extract_native_stress`, `extract_d3plot_field`, `extract_d3plot_stress`, `extract_nodal_results`, `extract_d3plot_nodal`, `extract_lsreader_nodal`, `export_dpf_result` | partial / v0.5 |
| Q04 工程量与失效掩码 | `compute_stress_invariants`, `extract_native_stress`, `inspect_result_validity` | partial / v0.5 |
| Q05 时程曲线（History） | `extract_node_history` | partial / v0.5 |
| Q06 binout / ASCII 全库曲线 | `extract_native_binout_curve`, `extract_native_ascii_curve`, `extract_binout_curve`, `extract_binout_table`, `extract_ascii_curve` | partial / v0.5 |
| Q07 曲线运算 | `process_curve`, `convert_history_units`, `combine_history_curves`, `build_tensile_curves` | partial / v0.5 |
| Q08 XYPlot 出图 | `export_gui_curve_plot` | partial / v0.5 |
| Q09 动画导出 | `export_gui_animation`, `export_gui_field_animation`, `control_gui_animation` | partial / v0.5 |
| Q10 截面力与剖切面 | 未有专用工具；查知识库后评估明确授权的脚本 | todo / v0.6 |
| Q11 测量 | `measure_gui_geometry`, `measure_parts` | partial / v0.6 |
| Q12 能量检查 | `assess_energy_balance`, `native_energy_postprocess` | partial / v0.5 |
| A01 命令栏 Command（单条原生命令） | `prepare_native_program`, `execute_native_program`, `execute_gui_command`, `run_on_version` | partial / v0.5 |
| A02 cfile 命令流 | `prepare_native_program`, `execute_native_program` | partial / v0.5 |
| A03 SCL 脚本 | `prepare_native_program`, `execute_native_program`, `probe_scl` | partial / v0.5 |
| A04 应用内 Python 脚本 | `prepare_native_program`, `execute_native_program` | partial / v0.5 |
| A05 原生宏执行 | `prepare_native_program` | partial / v0.5 |
| A06 宏安装与快捷键管理 | 未有专用工具；查知识库后评估明确授权的脚本 | todo / v0.6 |
| A07 命令录制转配方 | `start_session_recording`, `stop_session_recording`, `import_command_recording`, `parameterize_workflow` | partial / v0.5 |
| A08 配方库 | `create_native_macro`, `run_native_macro`, `list_installation_assets`, `describe_installed_template`, `instantiate_installed_template`, `apply_keyword_filter` | partial / v0.5 |
| A09 参数化批量 | `run_workflow_sweep`, `create_workflow`, `run_workflow`, `inspect_workflow` | partial / v0.5 |
| A10 知识检索 | `search_commands`, `search_knowledge`, `search_workflows`, `list_pydyna_keywords`, `describe_pydyna_keyword` | partial / v0.5 |
| G01 视图控制 | `set_gui_display` | partial / v0.5 |
| G02 显示控制 | `set_gui_part_visibility`, `set_gui_entity_visibility`, `set_gui_display` | partial / v0.6 |
| G03 统一选择器 | `select_gui_entities`, `select_gui_nodes_by_box`, `select_gui_nodes_by_sphere`, `select_gui_nodes_by_plane`, `select_gui_shell_topology`, `combine_gui_selections`, `save_gui_selection_buffer`, `load_gui_selection_buffer` | partial / v0.5 |
| G04 实体识别 Identify | `list_nodes`, `get_element_connectivity`, `inspect_gui_mesh` | partial / v0.5 |

## 执行规则

- full 暴露当前工具；compact 用 lspp_find_operations / lspp_describe_operation / lspp_run_operation 按需查询严格 schema。
- 工具返回 failed 时读 read_job；completed_unverified、prepared、partial 不能当成工程验证通过。
- 用户 ID 不等于数组下标；状态从 1 开始。时间请求核对实际状态与时间。
- 明确单位、实体域、坐标系、层/积分点、平均、失效掩码；未知单位不猜常数。
- 数值可用 LASSO / LS-Reader，始终标明后端并查交叉验证范围；原生渲染/派生量使用 LSPP。
- 4.10 内置向量 ABI 与原生实体积分点 2–8 存在已知错误，保留拒绝；不能用读取器结果冒充原生。
- 当前 Include 保真编辑、接触与 MPP 合并有缺口；先查任务验收，不用整体重写替代保真。
- 会话动作使用指定会话；失败时不自动改用后台实例。新建的批处理请求与会话请求明确区分。
- unknown/uncertain 请求先核对回执与保存副本，不自动重放。只关闭本任务创建且允许关闭的进程。
- 脚本只运行用户授权且已检查的源码；Python/SCL 不是沙箱。知识检索命中不等于执行授权或功能验收。
- 输出写入明确 job 目录；保存后原生重开、检查数值/图像、输入哈希与产物身份。
- 4.13 全量验收目标；4.10 子集、4.8 尽力、排除 4.11。已有验证只限记录的构建与语料。

## 参考

- [任务与验收](../../docs/TASKS.md) · [工具参数](../../docs/TOOLS.md)
- [已知问题](../../docs/KNOWN_ISSUES.md) · [兼容性](../../docs/COMPATIBILITY.md)
- [前后处理 SOP](references/task-sops.md) · [程序通道](references/programs.md) · [结果语义](references/postprocessing.md)
- [会话与工作流](references/automation.md)

新开发只认 tasks.yaml；本 Skill 在 M0 仅压缩路由，完整 SOP 重写属于 M4。
