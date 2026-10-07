# 当前 MCP 工具

由实际 full profile registry 生成。目标工具是迁移设计，不表示已经注册。未列入任务 existing 的工具标注基础设施迁移 I08。

| 工具 | 所属任务 | 参数摘要（* 必填） |
|---|---|---|
| `activate_gui_model` | I08 | session_id*: string; source_path*: string |
| `apply_keyword_filter` | P10, A08 | model*: string; filter_id*: string |
| `assess_energy_balance` | Q12 | kinetic_curve*: string; internal_curve*: string; units*: string; hourglass_curve: union/ref; external_work_curve: union/ref; kinetic_ratio_limit: number; hourglass_ratio_limit: number |
| `build_tensile_curves` | Q07 | force_curve*: string; displacement_curve*: string; area*: number; gauge_length*: number; force_unit*: string; length_unit*: string; time_unit*: string; reference_displacement_curve: union/ref; force_sign: integer; displacement_sign: integer; true_conversion: boolean |
| `check_gui_keywords` | P09 | session_id*: string |
| `check_gui_shell_quality` | P09 | session_id*: string; thresholds*: object; units*: string |
| `check_gui_solid_quality` | P09 | session_id*: string; checks*: array; units*: string; capture_failed_ids: boolean |
| `check_model` | P09, P12 | model*: string; thresholds: union/ref; coincident_tolerance: union/ref; include_mesh: boolean |
| `checkpoint_gui_session` | P11 | session_id*: string |
| `close_gui_session` | I08 | session_id*: string; save_checkpoint: boolean |
| `combine_gui_selections` | G03 | session_id*: string; entity_type*: string; left_ids*: array; right_ids*: array; operation: string |
| `combine_history_curves` | Q07 | paths*: array; operation*: string; units*: string; source_units: union/ref; time_unit: union/ref |
| `command_help` | I08 | command*: string; limit: integer |
| `compose_keyword_deck` | P02 | cards*: array; units*: string |
| `compute_stress_invariants` | Q04 | stresses*: array; units*: string; relative_tolerance: number |
| `control_gui_animation` | Q09 | session_id*: string; operation*: string; first: integer; last: integer; increment: integer; direction: string |
| `convert_history_units` | Q07 | path*: string; value_unit*: string; output_value_unit*: string; time_unit*: string; output_time_unit*: string; time_column: string; value_column: string |
| `create_elastic_material` | P03 | material_id*: integer; density*: number; young_modulus*: number; poisson_ratio*: number; units*: string |
| `create_entities` | P04, P05, P06, P12 | model*: string; entities*: array |
| `create_gui_elements` | P08 | session_id*: string; element_type*: string; part_id*: integer; elements*: array; units*: string |
| `create_gui_entity_set` | P04 | session_id*: string; entity_type*: string; set_id*: integer; title*: string; entity_ids: union/ref; selection_job: union/ref; mode: string |
| `create_gui_nodal_load` | P05 | session_id*: string; axis*: string; curve_id*: integer; time_unit*: string; value_unit*: string; distribution*: string; node_set_id: union/ref; node_ids: union/ref; selection_job: union/ref; points: union/ref; curve_title: union/ref; scale: number; allow_superposition: boolean |
| `create_gui_nodes` | P08 | session_id*: string; nodes*: array; units*: string |
| `create_gui_nonreflecting_boundary` | P05 | session_id*: string; segment_set_id*: integer; dimension*: integer; solver_release*: integer; length_unit*: string; dilatational: boolean; shear: boolean; node_set_start_id: union/ref |
| `create_gui_prescribed_motion` | P05 | session_id*: string; motion_id*: integer; title*: string; axis*: string; motion*: string; curve_id*: integer; time_unit*: string; length_unit*: string; node_set_id: union/ref; node_ids: union/ref; selection_job: union/ref; points: union/ref; curve_title: union/ref; scale: number; birth: number; death: number; append_to_group: boolean |
| `create_gui_segment_pressure` | P05 | session_id*: string; segment_set_id*: integer; curve_id*: integer; curve_title*: string; points*: array; time_unit*: string; pressure_unit*: string; length_unit*: string; scale: number; arrival_time: number; load_id: union/ref; load_title: union/ref; curve_usage: string |
| `create_gui_segment_set` | P04 | session_id*: string; set_id*: integer; title*: string; source*: string; length_unit*: string; element_ids: union/ref; selection_job: union/ref; normal_direction: union/ref; cosine_min: number; reverse: boolean; max_warpage_degrees: number |
| `create_gui_spc` | P05 | session_id*: string; constraint_id*: integer; title*: string; dofs*: array; node_set_id: union/ref; node_ids: union/ref; coordinate_system: integer |
| `create_native_macro` | A08 | name*: string; language*: string; code*: string; defaults*: object; outputs: union/ref; expected_counts: union/ref; dependencies: union/ref |
| `create_node_set_by_box` | P04 | model*: string; set_id*: integer; bounds*: array; units*: string; tolerance: number |
| `create_shell_plate` | P07 | nx*: integer; ny*: integer; size*: array; units*: string; origin: union/ref; part_id: integer; node_start: integer; element_start: integer |
| `create_solid_box` | P07 | divisions*: array; size*: array; units*: string; origin: union/ref; part_id: integer; node_start: integer; element_start: integer |
| `create_solid_sphere` | P07 | center*: array; radius*: number; divisions*: integer; units*: string; part_id: integer |
| `create_tensile_shell_plate` | I08 | nx*: integer; ny*: integer; size*: array; thickness*: number; density*: number; young_modulus*: number; poisson_ratio*: number; displacement*: number; duration*: number; output_interval*: number; units*: string |
| `create_workflow` | A09 | name*: string; steps*: array; defaults: union/ref |
| `curve_ops` | I08 | inputs*: array; operations*: array |
| `describe_installed_template` | A08 | template_id*: string |
| `describe_pydyna_keyword` | A10 | class_name*: string |
| `edit_keywords` | P02, P03, P10 | model*: string; edits*: array; allow_new_dangling: boolean |
| `execute_gui_command` | A01 | session_id*: string; command*: string; outputs: union/ref; expected_counts: union/ref; initial_node_ids: union/ref; capture_model: boolean |
| `execute_native_program` | A01, A02, A03, A04 | prepared_job_id*: string; expected_sha256*: string; model: union/ref; file_type: string; graphics: boolean; session_id: union/ref; capture_model: boolean; inspect_selection: boolean; allow_owned_output_context: boolean; launch_mode: string |
| `export_dpf_result` | Q03 | path*: string; file_type*: string; result*: string; units*: string; states: union/ref; entity_ids: union/ref; label_filter: union/ref; component: union/ref; actunits: union/ref |
| `export_gui_animation` | Q09 | session_id*: string; last: union/ref; fps: integer; width: integer; height: integer; averaging: string |
| `export_gui_curve_plot` | Q08 | session_id*: string; path*: string; x_column*: string; y_column*: string; title*: string; x_label*: string; y_label*: string; x_unit*: string; y_unit*: string; curve_label: union/ref; additional_curves: union/ref |
| `export_gui_field_animation` | Q09 | session_id*: string; states*: array; color_range*: array; fps: integer; width: integer; height: integer |
| `export_keyword` | P11 | model*: string |
| `extract_ascii_curve` | Q06 | path*: string; time_column*: integer; value_column*: integer; units*: string; delimiter: string; skip_rows: integer |
| `extract_binout_curve` | Q06 | path*: string; branch*: string; variable*: string; units*: string; entity_id: union/ref |
| `extract_binout_table` | Q06 | path*: string; branch*: string; variables*: array; units*: string; entity_ids: union/ref |
| `extract_d3plot_field` | Q03 | path*: string; field*: string; states*: array; units*: string; entity_ids: union/ref; component_indices: union/ref; validity_policy: string |
| `extract_d3plot_nodal` | Q03 | path*: string; node_ids*: array; quantity*: string; states*: array; units*: string |
| `extract_d3plot_stress` | Q03 | path*: string; element_type*: string; element_ids*: array; states*: array; integration_point*: integer; units*: string; relative_tolerance: number; validity_policy: string |
| `extract_lsreader_nodal` | Q03 | path*: string; node_ids*: array; quantity*: string; states*: array; units*: string |
| `extract_native_ascii_curve` | Q06 | path*: string; database*: string; component*: integer; units*: string; entity_id: union/ref |
| `extract_native_binout_curve` | Q06 | path*: string; branch*: string; quantity*: string; units*: string; entity_id: union/ref; session_id: union/ref |
| `extract_native_fields` | Q03 | path*: string; entity_type*: string; entity_ids*: array; states*: array; fields*: array; integration_point*: string; units*: string; validity_policy: string |
| `extract_native_stress` | Q03, Q04 | path*: string; element_type*: string; element_ids*: array; states*: array; integration_point*: string; units*: string; validity_policy: string |
| `extract_nodal_results` | Q03 | d3plot*: string; node_ids*: array; quantity*: string; state*: integer; units*: string |
| `extract_node_history` | Q05 | d3plot*: string; node_ids*: array; quantity*: string; states*: array; units*: string; curve_components: union/ref; time_unit: union/ref |
| `extrude_shell_part` | P07 | model*: string; part_id*: integer; length*: number; layers*: integer; units*: string |
| `find_recipe` | I08 | query: string; task_id: union/ref; channel: union/ref; limit: integer; include_candidates: boolean |
| `get_element_connectivity` | G04 | model*: string; element_id*: integer; element_type: string; file_type: string |
| `gui_session_action` | I08 | session_id*: string; action*: string; parameters*: object |
| `import_command_recording` | A07 | path*: string; units*: string; recorded_model_index: union/ref |
| `inspect_binout` | Q01 | path*: string; branch: union/ref |
| `inspect_binout_variable` | Q01 | path*: string; branch*: string; variable*: string |
| `inspect_d3plot_database` | Q01 | path*: string |
| `inspect_d3plot_scl` | Q01 | path*: string |
| `inspect_dpf_results` | Q01 | path*: string; file_type*: string; actunits: union/ref |
| `inspect_gui_entity_sets` | P04 | session_id*: string; entity_type*: string; set_id: union/ref; offset: integer; limit: integer |
| `inspect_gui_menu` | I08 | session_id*: string; path_prefix: union/ref; max_depth: integer |
| `inspect_gui_mesh` | P01, G04 | session_id*: string; include_entities: boolean; entity_type: union/ref; offset: integer; limit: integer |
| `inspect_gui_mesh_quality` | P09 | session_id*: string; units*: string; max_aspect: number; max_warpage: number; min_scaled_jacobian: number; fail_on_issues: boolean |
| `inspect_gui_session` | I08 | session_id*: string; include_models: boolean |
| `inspect_keyword_deck` | P01 | model*: string |
| `inspect_lsreader` | Q01 | path*: string |
| `inspect_mesh_quality` | P09 | model*: string; units*: string; max_aspect: number; max_warpage: number; min_scaled_jacobian: number |
| `inspect_model` | P01 | model*: string; file_type: string |
| `inspect_result_fields` | Q01 | path*: string; state: integer |
| `inspect_result_validity` | Q04 | path*: string; element_type*: string; states*: array; element_ids: union/ref |
| `inspect_workflow` | A09 | path*: string; parameters: union/ref; session_id: union/ref |
| `instantiate_installed_template` | P10, A08 | template_id*: string; parameters*: object; units*: string; model: union/ref; native_check: boolean |
| `keyword_fields` | I08 | keyword*: string; field: union/ref; limit: integer; include_private: boolean |
| `list_capabilities` | I08 | 无 |
| `list_gui_sessions` | I08 | 无 |
| `list_installation_assets` | A08 | 无 |
| `list_installations` | I08 | 无 |
| `list_jobs` | I08 | limit: integer |
| `list_nodes` | P01, G04 | model*: string; file_type: string; offset: integer; limit: integer |
| `list_parts` | P01 | model*: string; file_type: string; limit: integer |
| `list_pydyna_keywords` | A10 | query: string; offset: integer; limit: integer |
| `load_gui_selection_buffer` | G03 | session_id*: string; slot*: integer |
| `measure_gui_geometry` | Q11 | session_id*: string; measurement*: string; node_ids*: array; units*: string; axis: string; state: union/ref; capture: boolean |
| `measure_parts` | Q11 | model*: string; part_ids*: array |
| `merge_duplicate_mesh_nodes` | P08 | model*: string; tolerance*: number; units*: string; native_check: boolean |
| `merge_gui_duplicate_nodes` | P08 | session_id*: string; tolerance*: number; units*: string |
| `mesh_ops` | P08 | model*: string; operations*: array |
| `model_info` | P01 | model*: string |
| `move_elements_to_part` | P03, P08 | model*: string; element_type*: string; element_ids*: array; part_id*: integer |
| `native_energy_postprocess` | Q12 | path*: string; units*: string; include_hourglass: boolean; include_external_work: boolean |
| `native_postprocess_case` | I08 | path*: string; units*: string |
| `native_tensile_postprocess` | I08 | force_path*: string; nodout_path*: string; force_database*: string; force_component*: integer; force_entity_id*: integer; top_node*: integer; bottom_node*: integer; displacement_component*: integer; area*: number; gauge_length*: number; force_unit*: string; length_unit*: string; time_unit*: string; force_sign: integer; displacement_sign: integer |
| `open_in_gui_session` | I08 | session_id*: string; path*: string; file_type: string; discard: boolean; expected_empty: boolean |
| `parameterize_workflow` | A07 | path*: string; bindings*: array |
| `prepare_native_program` | A01, A02, A03, A04, A05 | language*: string; code: union/ref; path: union/ref; parameters: union/ref; outputs: union/ref; expected_counts: union/ref; dependencies: union/ref; macro_name: union/ref; script_parameters: union/ref |
| `probe_dpf_runtime` | I08 | 无 |
| `probe_environment` | I08 | 无 |
| `probe_scl` | A03 | model*: string |
| `process_curve` | Q07 | path*: string; operation*: string; units*: string; time_column: integer; value_column: integer; delimiter: string; skip_rows: integer |
| `read_job` | I08 | job_id*: string |
| `recover_gui_session` | I08 | session_id*: string |
| `render_gui_field` | Q02 | session_id*: string; entity_type*: string; field*: string; state*: integer; units*: string; integration_point: string; part_ids: union/ref; color_range: union/ref; averaging: string; validity_policy: string |
| `render_snapshot` | Q02 | model*: string; file_type: string; view: string; state: union/ref; fringe_code: union/ref; averaging: string |
| `renumber_gui_entities` | P08 | session_id*: string; entity_type*: string; start_id*: integer; check_references: boolean |
| `replace_gui_model` | I08 | session_id*: string; path*: string; file_type: string; expected_empty: boolean |
| `replace_gui_node` | P08 | session_id*: string; source_node_id*: integer; target_node_id*: integer; units*: string |
| `reset_gui_session` | I08 | session_id*: string; save_checkpoint: boolean |
| `restart_gui_session` | I08 | session_id*: string |
| `restore_gui_checkpoint` | I08 | session_id*: string; path: union/ref; expected_empty: union/ref |
| `reverse_gui_shell_normals` | P08 | session_id*: string; units*: string; shell_ids: union/ref |
| `rotate_gui_nodes` | P08 | session_id*: string; node_ids*: array; axis*: string; angle*: number; center*: array; units*: string |
| `rotate_mesh_nodes` | P08 | model*: string; node_ids*: array; axis*: string; angle*: number; center*: array; units*: string |
| `run_native_macro` | A08 | path*: string; parameters: union/ref; model: union/ref; file_type: string; graphics: boolean; session_id: union/ref |
| `run_on_version` | A01 | version*: string; action*: string; parameters*: object |
| `run_recipe` | I08 | recipe*: string; parameters: union/ref; model: union/ref; file_type: string; session_id: union/ref; launch_mode: string |
| `run_script` | I08 | language*: string; code*: string; context: string; session_id: union/ref; model: union/ref; file_type: string; outputs: union/ref; expected_counts: union/ref; capture_model: boolean; initial_node_ids: union/ref; parameters: union/ref; dependencies: union/ref; launch_mode: string |
| `run_workflow` | A09 | path*: string; parameters: union/ref; session_id: union/ref |
| `run_workflow_sweep` | A09 | path*: string; cases*: array; outputs: union/ref; session_id: union/ref |
| `save_gui_selection_buffer` | G03 | session_id*: string; entity_type*: string; entity_ids*: array; slot*: integer |
| `search_commands` | A10 | query*: string; limit: integer |
| `search_docs` | I08 | query*: string; category: union/ref; limit: integer; include_private: boolean |
| `search_knowledge` | A10 | query*: string; limit: integer; include_private: boolean; category: union/ref |
| `search_workflows` | A10 | query*: string; limit: integer |
| `select_gui_entities` | G03 | session_id*: string; entity_type*: string; entity_ids: union/ref; part_ids: union/ref; invert: boolean; scope: string; set_ids: union/ref |
| `select_gui_nodes_by_box` | G03 | session_id*: string; bounds*: array; units*: string; inside: boolean; tolerance: number |
| `select_gui_nodes_by_plane` | G03 | session_id*: string; point*: array; normal*: array; units*: string; side: string; tolerance: number |
| `select_gui_nodes_by_sphere` | G03 | session_id*: string; center*: array; radius*: number; units*: string; inside: boolean; tolerance: number |
| `select_gui_shell_topology` | G03 | session_id*: string; seed_ids*: array; mode: string; feature_angle: union/ref; rings: union/ref; scope: string |
| `set_gui_display` | G01, G02 | session_id*: string; view: union/ref; display_mode: union/ref; background: union/ref; projection: union/ref; legend: union/ref; triad: union/ref; timestamp: union/ref; title: union/ref; state: union/ref; fringe_code: union/ref; center: boolean; capture: boolean; averaging: union/ref; zoom_scale: union/ref; pan_xy: union/ref; rotation_xyz_degrees: union/ref |
| `set_gui_entity_visibility` | G02 | session_id*: string; entity_type*: string; mode*: string; entity_ids: union/ref; capture: boolean |
| `set_gui_node_coordinates` | P08 | session_id*: string; nodes*: array; units*: string; tolerance: number |
| `set_gui_part_visibility` | G02 | session_id*: string; mode*: string; part_ids: union/ref |
| `set_view` | I08 | context: string; session_id: union/ref; model: union/ref; file_type: string; view: union/ref; projection: union/ref; rotation_xyz_degrees: union/ref; zoom_scale: union/ref; pan_xy: union/ref; fit: boolean; center_on: union/ref; save_preset_name: union/ref; restore_preset_name: union/ref; capture: boolean |
| `show_gui_session` | I08 | session_id*: string; maximize: boolean; keep_on_top: boolean |
| `start_gui_session` | I08 | 无 |
| `start_session_recording` | A07 | session_id*: string |
| `stop_session_recording` | A07 | session_id*: string |
| `transform_mesh_deck` | P08 | model*: string; operation*: string; values*: array; units*: string; node_ids: union/ref; center: union/ref; native_check: boolean |
| `translate_gui_nodes` | P08 | session_id*: string; node_ids*: array; offset*: array; units*: string |
| `translate_mesh_nodes` | P08 | model*: string; node_ids*: array; offset*: array; units*: string |
| `unload_gui_model` | I08 | session_id*: string; source_path*: string; activate_source_path*: string |
| `update_elastic_material` | P03 | model*: string; material_id*: integer; density*: number; young_modulus*: number; poisson_ratio*: number; units*: string |
| `update_keyword_fields` | P02 | model*: string; class_name*: string; selector*: object; fields*: object; units*: string |
| `update_keyword_table_row` | P02 | model*: string; class_name*: string; table_name*: string; selector*: object; values*: object; units*: string |
| `validate_model_references` | P09 | model*: string |
