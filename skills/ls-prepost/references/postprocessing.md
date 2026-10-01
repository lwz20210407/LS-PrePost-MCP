# Result routing

Native SCL fields/stresses and LASSO scalar/stress exports now include `field_spec` in parameters and returned data. Read its backend, user-ID/state selection identity, sampling kind, frame, averaging, validity and transformations before comparing results. Native MID/INNER/OUTER, solid default selector 0, and reader stored slot 1 are not automatically equivalent. Nodal native extraction uses the legacy `mid` argument only as default/no-layer; numeric node integration points are rejected. Unit labels are retained with dimensional_validation=false, not inferred conversions.

Use the native route when requested. `extract_native_stress` obtains all six components and Mises from native SCL; its derived triaxiality/Lode calculation is explicitly labeled Python mathematics on native data. Inspect the native-Mises agreement rather than inferring correctness from a valid CSV.

For visible selected-node histories, bind `select_gui_entities.verification.selected_ids` to `extract_node_history.node_ids` inside a GUI workflow. Add explicit `curve_components` and `time_unit` to export scalar curves for `combine_history_curves`; inspect each curve's node/component/quantity/unit metadata. The shared template `examples/workflows/visible_gui_relative_displacement.json` computes first minus second in sorted selected-ID order, not a gauge projection. Supply exactly two IDs, increasing states and explicit unit labels. At most 100 scalar curves; no position magnitude. Extraction stops animation and confirms restoration of the original state; it does not resume playback. Native 4.13.4 passed the two-component workflow and position/reference/displacement identity check. Keep all private input and derived evidence local.

Tensor order: xx, yy, zz, xy, yz, xz. Tension positive. Shell/solid integration point must be explicit; no averaging is implied. Mises=sqrt(3J2), triaxiality=mean/Mises. `lode_angle_parameter=1−6θ/π` is +1 in uniaxial tension; `lode_parameter=(2σ2−σ1−σ3)/(σ1−σ3)` is −1. Preserve these different names and the returned definitions. Hydrostatic ratios are null/empty, not zero.

Native ASCII uses database-specific UI component numbers, not d3plot fringe/ntime codes. Inspect installed-version documentation and the tested scope. Contact master/slave selectors and ELOUT integration points need dedicated adapters; do not append arbitrary tokens to existing tools.

For optional reader extraction, call `inspect_result_fields`, then select actual user IDs, states and every trailing stored-axis index. History-slot interpretation requires the material/version/output definition. A missing field cannot be reconstructed by naming it. No generic native history-variable route is certified yet.

Native batch acceptance samples three geometry records per entity type for histories, scans whole fields for extrema, exports available supported ASCII curves and renders a native image. It preserves native returned values, including deleted entities/rigid zeros unless documented otherwise. All checks and source copies belong to owned job directories. Keep private engineering results out of Git and public reports.

See the repository [full contract](../../../docs/POSTPROCESSING.md) for supported tools and remaining gaps.
