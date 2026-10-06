# Changes

## 0.4.0 (development)

### 从 Skill 迁入的更新记录

- `automation.md`：For normal reversal on large keyword meshes, `reverse_gui_shell_normals` now supports standard Tri3/Quad4 all/explicit scopes through complete streamed orientation/preservation checks. Native100,000-shell full/partial reversal and save/reopen passed. It preserves part visibility and every unrequested connectivity/coordinate; it does not implement automatic outward/seed-based unification, thick-shell normals or material-axis changes. Other snapshot-based merge/renumber/quality paths retain their documented limits.
- `automation.md`：Box/sphere/plane node selections now run native reference-coordinate predicates and streamed verification on large models. Each operation may select up to20,000nodes; that is a selected-set response/command budget, not a global model cap. Boundaries/tolerances, inside/outside and empty selections are explicit.100,000-shell native checks and changed-box recorded replay passed. Use these for geometric regions, not screen pixels, deformed coordinates or physical alive masks. Generic part-filter/active-part/inverted selection now uses streamed native registry/connectivity sets. Equivalent whole/part bulk commands allow up to1,000,000 selected entities; explicit arguments/nonbulk fallback remain20,000. This guard is not certification at one million. Hidden requested parts may share nodes with active parts; preserve the computed intersection rather than merely dropping hidden part IDs.
- `automation.md`：For large-model inspection, use `inspect_gui_mesh` with an explicit `entity_type` and bounded `offset`/`limit`, then follow `next_offset`. Pages are not an atomic cross-call snapshot. Explicit/part/active-part/whole/scoped-inverse selection, set combinations/buffers, translation, rotation and absolute node correction now use complete streamed geometry fingerprints and requested-coordinate readback, with no global20,000 model bound. Operation-size limits still apply. Native100,000-shell and private larger-solid coordinate edit/save/reopen flows passed. Duplicate merging, normals, renumbering and other snapshot-based checks/edits still have the global20,000 bound; do not describe it as an LS-PrePost limit. Start a new owned GUI for the updated bridge. See `docs/MODEL_SCALE.md`.
- `automation.md`：Save `checkpoint_gui_session` before replacing meaningful state. Open/reset now require matching native source identity, valid counters and no detected errors in the request's log suffix; delayed recovery uses the same checks. A failed load leaves the session uncertain and does not advance trusted source/type/generation. Never send `new` to a live GUI: it can request a process restart. PID/create-time/exe must still match.
- `automation.md`：Native Binout `extract_native_binout_curve` now accepts session_id; within a GUI workflow it reuses that owned instance rather than launching batch. Supported MATSUM quantities include energies/eroded energies/mass/momentum/rigid-body velocity, with explicit stored database entity_id. Do not infer correspondence with displayed model parts or infer units. Missing fields/IDs fail. Use explicit `$artifact` dependencies from extraction to plot paths, including nested additional_curves paths, so changing the recorded entity ID produces and plots fresh data. GUI4.13.4 official-fixture numeric checks and ID1500→1501 energy overlay replay passed; MPP fragments and other branches remain separate work.
- `automation.md`：Selection/inspection transactions no longer export two full keyword checkpoints. They preserve prior checkpoint/dirty metadata and verify geometry; edits still create pre/post checkpoints. Inspect transaction_kind/checkpoint_created instead of assuming every result saved a new model. Full mesh snapshot/20000 limits remain until the later scale work is verified.
- `automation.md`：Unload/replacement success now requires a completed, file-bound native export of any keyword survivor after removal. Counts alone are insufficient. If the export exits or fails, retain the pre-removal checkpoint and report failure; `model_removed` / `old_model_unloaded=true` can coexist with failure, because the removal already happened. Do not replay it or auto-restart. Read [known native failures](docs/archive/2026-10/NATIVE_KNOWN_ISSUES.md); the angular-shell crash remains unresolved. A successful export is a bounded health check, not long-session certification. Result databases are not silently exported as keyword.
- `automation.md`：Node selection, sets and loads now preserve standard ELEMENT_MASS through fresh native keyword export plus SDK count, node-reference and property hashes. See [mass preservation](docs/archive/2026-10/MASS_PRESERVATION.md). Do not infer a MASS Python enum or use part-type integer6 as one. Structural element display is checked separately; auxiliary mass glyph flags remain unverified (full-display proof=null). All-element selection, topology/normal edits and Blank tools on these models still reject; inertia/other auxiliary families and old versions are separate. Use a newly created GUI session for the updated bridge.
- `automation.md`：Workflows now distinguish successful execution from successful checks. Native shell/keyword checks and scoped mesh/reference checks require explicit true verdicts by default. Use step `quality_policy="report_only"` only when the task intentionally permits findings, then define explicit `checks` for allowable counts/limits; execution failure and those checks still stop. Missing/null/invalid verdicts never count as pass. Do not set report_only simply to get past a failure.
- `automation.md`：Raw cfile import now covers explicit/whole/inverse selection, native buffer save→clear→load, selected translation/normals and shell quality checks. Dynamic whole/buffer IDs use verified result bindings. Clear before changing targets. Model-qualified IDs need explicit `recorded_model_index` matching every suffix; never silently strip `/0` or guess a multi-model mapping. Unsupported selection context remains `needs_review`.
- `common.md`：Selection preserves existing element display-active flags and no longer uses `pall`. Blank or hidden-part cases require exact-ID fallback within20,000 selected IDs because native whole/by-part selection can omit hidden members; larger requests are rejected before dispatch. This is not a model-size limit. Include explicit display setup in recordings when replay should reconstruct Blank flags; keyword checkpoints alone do not store that scene. Entity Creation node/part LIST and global SPC workflows now have bounded native verification; Pressure/nonreflecting workflows now have separate bounded native checks. See `docs/ENTITY_CREATION.md`, and do not equate existing node/element creation or generic card editing with complete set/constraint/load tools.
- `postprocessing.md`：Native SCL fields/stresses and LASSO scalar/stress exports now include `field_spec` in parameters and returned data. Read its backend, user-ID/state selection identity, sampling kind, frame, averaging, validity and transformations before comparing results. Native MID/INNER/OUTER, solid default selector 0, and reader stored slot 1 are not automatically equivalent. Nodal native extraction uses the legacy `mid` argument only as default/no-layer; numeric node integration points are rejected. Unit labels are retained with dimensional_validation=false, not inferred conversions.

### 从旧 README 迁入的历史说明

新增[选择驱动的三维/二维Segment集](docs/archive/2026-10/SEGMENT_SETS.md)和[压力/无反射边界](docs/archive/2026-10/BOUNDARY_CONDITIONS.md)：法向、引用、参数化回放和保存重开已有4.13.4限定原生验收；不包含求解物理验证。

开发进度见[验收台账与实时面板](docs/archive/2026-10/PROGRESS.md)，不以工具数当功能覆盖率。[Entity Creation](docs/archive/2026-10/ENTITY_CREATION.md) 已打通4.13.4选区建集、SPC、Segment压力与二维/三维无反射条件的限定流程。旧求解器二维路线使用经读回验证的有序节点对，不混用新版负SID语义。

近期增量：[标准单元显隐与受管恢复](docs/archive/2026-10/GUI_VISIBILITY.md)、保留模型标题/原生结果名称和默认 MinMax 显示平均、[可选精简 MCP 入口](docs/archive/2026-10/MCP_TOOL_PROFILES.md)。原生 4.13.4 验收与未支持范围分别记录；[外部评审处理](docs/archive/2026-10/REVIEW_RESPONSE_2026-10-03.md)保持通用前后处理定位，不把专项案例变成产品主线。

[视图控制](docs/archive/2026-10/GUI_CAMERA.md)已扩展绝对缩放/平移和增量 X/Y/Z 旋转，支持参数化回放；keyword 与代表性 d3plot 经过可见 4.13.4 验证。书签、任意旋转中心和选区适配仍待补齐。

产品与工程主线见 [顶层设计](docs/archive/2026-10/ARCHITECTURE.md)：以 **常用网格编辑与检查、明确语义的工程后处理、录制与参数化复用** 三条完整流程作为版本验收目标。统一语义/执行/质量合同后按依赖扩展模块，当前设计不代表已完成架构迁移。[资料转化状态](docs/archive/2026-10/SOURCE_ADOPTION.md)与[待开发清单](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)分别说明输入依据和缺口。

首批架构落地：[统一工作流结果与质量门槛](docs/archive/2026-10/WORKFLOW_GATES.md)。已加入检查不合格时停止后续步骤、参数化阈值和失败证据，并提供可复用配方及文件后端合成验收。

当前按[交付批次](docs/archive/2026-10/DELIVERY_PLAN.md)优先推进前处理、后处理和自动参数化。[工作流框架](docs/archive/2026-10/WORKFLOW_FRAMEWORK.md)已统一操作路由和整条流程预检，支持 1–20 组显式参数独立执行及结果汇总；合成网格变换→原生质量→保存重开已在可见 4.13.4 验证。[原生输出](docs/archive/2026-10/NATIVE_MEDIA.md)现包含带标签单曲线 PNG、数值读回及从 state1 连续导出的 MP4，均已接入录制参数回放。多曲线/完整云图及任意范围/格式动画仍需补齐，现有子集不代表全部完成。

本项目独立实现任务与执行核心，吸收公开项目、官方文档和本地案例的接口经验；可复用数据与依赖按各自许可证接入。来源、已实现能力、实机验证和待开发功能分别登记，详见 [来源与复用](docs/archive/2026-10/SOURCES.md)、[兼容性](docs/COMPATIBILITY.md)、[开发路线](docs/archive/2026-10/ROADMAP.md)。

**资料尚未全部转化为可执行功能。** 按实际工作任务列出的实现与缺口见[覆盖矩阵](docs/archive/2026-10/COVERAGE.md)，不以命令目录或工具数量代替覆盖程度。

按前处理、后处理、参数化、命令/Python/宏、顶部菜单、右侧与底部工具栏逐项展开的现状见 [v0.2.0 界面与能力缺口审计](docs/archive/2026-10/FEATURE_GAP_AUDIT_v0.2.0.md)。

全部用户要求的持续开发清单见 [需求总清单与优先级](docs/archive/2026-10/REQUESTS_AND_PRIORITIES.md)。仓库现已提供 [原始 command / cfile / SCL / Python / 参数宏](docs/archive/2026-10/NATIVE_PROGRAMS.md) 的正式执行工具，逐通道记录实机范围；原始脚本入口不等于所有软件功能都已完成工程封装。

最新进展：[同一可见 GUI 的网格编辑工作流](docs/archive/2026-10/GUI_WORKFLOWS.md)，包括原生合并、法向、原位变换、新增节点/单元与质量读回；[图文/代码/视频转化记录](docs/archive/2026-10/TUTORIAL_INTEGRATION.md)标注实际阅读、观看与复现进度。

**2026-10-01 进展**：[结果合同与可见后处理流程](docs/archive/2026-10/RESULT_CONTRACTS.md)现包含 keyword/d3plot 选择、部件显隐保留、原生节点历史到相对位移三步模板及原时刻恢复。自动质量门槛、原生壳质量、Keyword Check、缓存、重编号和录制回放已有明确范围的验证。[待开发清单](docs/archive/2026-10/BACKLOG_REVIEW_2026-10-01.md)仍保留大模型、失效/层/历史语义、更多网格编辑、曲线窗口和菜单覆盖等缺口。

通用前后处理操作见 [F1–F10 子功能覆盖与缺口](docs/archive/2026-10/COMMON_OPERATIONS_COVERAGE.md)。新增 [原生几何测量](docs/archive/2026-10/GUI_MEASUREMENTS.md)，已验证参考/结果状态坐标、距离、轴向高度及关键词角度/圆心半径；完整面板与实体显隐/标记生命周期继续开发。

**2026-10-03：**新增 [DPF 可选适配与安装条件](docs/archive/2026-10/DPF_INTEGRATION.md)：已解析官方 LS-DYNA 三个示例，接入诊断、结果清单及保留标签/时间轴的导出代码。当前本机缺 DPF Server；合成合同测试不代表真实 DPF 读取已通过，原生 LS-PrePost 路线继续保留。

规模边界按工具区分：[大模型支持说明](docs/archive/2026-10/MODEL_SCALE.md)。20,000 是旧整模快照工具的实现限制，不是 LS-PrePost 软件上限。分页读取、命名字段云图以及指定节点选择/平移/旋转/坐标修改/保存重开已通过超过30万单元的私有原生验收；10万壳单元合成编辑流程也通过。其余选择和网格编辑继续迁移。

- 标准 MCP stdio 服务及同源 CLI。
- 每任务独立目录、命令文件、输入身份、结构化结果、超时处理和日志。
- 应用内 Python 探测、模型计数、节点/部件查询、单元连通性。
- 原生壳板网格创建、保存副本、重新读取、PNG 导出。
- 原生六面体方块网格、单个平面壳部件拉伸、选定节点平移、单元转移部件，核对数量/坐标/归属并输出 k 文件。
- 原生 SCL 探测，不依赖应用内 Python。
- 节点向量和时程接口；4.13已作读取器对照，4.10旧ABI的原生向量路径主动拒绝，见矩阵。
- 可选 LASSO d3plot/binout 数值读取后端，明确返回 `backend=lasso`。
- LS-Reader独立进程适配、PyDYNA Deck清单与弹性材料创建/修改/重读核对，见[后端合同](docs/archive/2026-10/BACKENDS.md)。
- 原生 SCL 应力/应变/节点字段、六分量应力与原生 Mises 一致性检查、三轴度和明确定义的 Lode 参数。
- 原生 ASCII/XYPlot 曲线、原生 SCLBinout 曲线，以及逐组后处理验收、全时程极值和实体 ID、结果图。详见[后处理合同](docs/archive/2026-10/POSTPROCESSING.md)。
- 可选读取器的显式场分量/历史槽位导出、binout 多变量表、数值 ASCII 曲线、非均匀时间微分与积分。
- [显式单位转换](docs/archive/2026-10/UNIT_CONTRACTS.md)、不同输入时间/数值单位统一后对齐，以及力/相对位移到工程应力应变和功的可复用配方；单位制不自动猜测。
- 按坐标范围创建节点集合、限定范围的模型引用检查，以及原生网格配合 PyDYNA 的位移加载壳板生成与原生重开检查。
- PyDYNA 实际关键字类/字段检索、结构化 Deck 组合、唯一匹配的标量卡与表格行编辑，拒绝未知字段并重读核验。六个文档板块的解析及迁移边界见[PyDYNA 集成](docs/archive/2026-10/PYDYNA_INTEGRATION.md)。
- 多安装版本配置和按版本调用，避免全局切换实例。
- 持久 Windows GUI 会话、显示/部件可见性、模型检查点及恢复、迟到响应协调。协议 3 已在同一可见 GUI 原位平移/旋转；旧协议保留检查点作业后重开路径。
- 4.13.4 可见 GUI 的选择/布尔/原生缓存、全体/局部壳法向、节点/壳/部件重编号、原生壳质量 13 项可选指标及 Keyword Check 报告；均明确限定范围并保留失败案例。
- 安装模板参数表达式安全求值、模板实例化、关键字过滤器应用；网格质量、合并与文件变换走明确标注的 PyDYNA/几何后端。
- 托管操作录制、显式参数绑定、顺序工作流；原生命令录制的受限编译，未知命令阻止回放。
- 原生 ASCII 提取后构建相对位移、力—位移、工程应力—应变；原生 SCLBinout 能量提取及筛查。
- 命令目录、官方教程验收案例、来源索引和配套 [Skill](skills/ls-prepost/SKILL.md)。



### 变更

- Add native Segment pressure curves/named loads with explicit units, monotonic time, ID collision checks, direction reports, parameter replay and numeric/card readback. Add exterior3D and directed2D nonreflecting conditions, with R14+ negative Segment IDs and a separately verified ordered two-node-set route for R11..13. Reject overlap, reversed2D edges, incompatible formulations and allocation collisions. Native4.13.4 create/reopen checks do not certify solver absorption.

- Add selection-bound native Segment sets from conforming Hex8/Tet4 exterior faces, shell faces and directed XY boundary edges. Verify ownership against unselected/hidden neighbors, orientation and normal filtering, native connectivity/scene preservation, parameterized replay and reopen. Pressure/nonreflecting conditions remain separate work.

- Add selection-bound native node/part list-set creation, paged inspection and member replacement preserving native attributes; add explicit global SPC set/node constraint creation, ID/DOF conflict checks and native card/mesh/scene verification. Verify changed-selection/SID recording replay and native reopen. Add model-load generations to reject old selection artifacts even after reopening identical geometry.
- Preserve all CSV list members and native packed SPC-ID header/data pairs during targeted readback; emit one named SPC_NODE card per node after native multirow truncation was reproduced. Segment sets, pressure and nonreflecting boundaries remain incomplete.

- Preserve per-element display-active flags during selection. Remove `pall`, avoid native whole/by-part selection when hidden members would be omitted, and verify exact IDs plus scene digests. Add mixed-element/hidden-part/buffer/display-setup replay native regression and fail-before-dispatch limits.
- Add an evidence-based local release progress dashboard with explicit denominator history. Promote selection-driven Entity Creation sets/constraints/loads to required release work; these workflows remain incomplete and are not advertised as implemented tools.

- Extend the existing display tool with strict native absolute zoom/pan and incremental X/Y/Z view rotations. Preserve operation ordering and managed parameter replay; verify zoom/pan idempotence, changed pixels, X/inverse rotation and reference-mesh preservation in visible4.13.4. Named view persistence remains a separate incomplete feature.

- Add optional compact MCP discovery/schema/execution profile while keeping original interfaces; preserve strict validation and explicit GUI routing without silent fallback. Resolve common panels through the current menu tree, constrain command-entry fallback, and reject locked desktops before creating pending native jobs.
- Add standard element Blank operations with whole-state binary readback, geometry/state/part preservation and owned restore/replay. Optimize sparse isolation using the smaller complement. Verify mixed shell/solid/beam and representative result workflows in visible4.13.4; use fresh native keyword beam endpoints after reproducing native array-binding heap faults.
- Preserve model titles and plain native result captions. Default field PNG/snapshot/movie display averaging to MinMax, retain explicit nodal/none overrides and keep raw CSV sampling distinct. Verify native averaging control, identical raw values, recorded replay and decoded three-frame MP4.

- Add native single-curve XYPlot PNG export from explicit CSV columns, labeled axes/units, fresh plot windows and numeric readback. Preserve hysteresis row order and original engineering CSV; disclose and validate native float32 storage. Verify changed-area recording/replay, old plot data preservation and native result-history/relative-displacement-to-PNG integration.

- Add native visible-GUI H264 MP4 export with state1/step1 bounds, explicit fps/resolution, ordered native frame evidence, independent full decode validation and state restoration. Verify complete57-state timeline and3/4-frame recorded parameter replay; arbitrary start/step modes remain rejected after failed native probes.

- Unify workflow operation routing and add a non-executing `inspect_workflow` preview. Preflight every step's parameters, signatures, references and quality thresholds before any native action; validate resolved dependency types again before dispatch.
- Add bounded explicit parameter studies with all-case preflight, separate child jobs, explicit GUI baselines, failure stopping and scalar/CSV summaries. Verify two native synthetic Hex8 transform/check/save/reopen cases and analytical engineering curves; recheck native post/recording flows. Native curve-image and animation export remain core gaps.

- Add opt-in native failed-solid ID capture, per-criterion artifacts and a verified deduplicated union for localization and dependency-preserving replay. Explicitly invalidate/backup known Buffer1 metadata and preserve other slots. Invalidate stale selection identities when replacing/resetting models; prevent a d3plot session from inheriting the prior keyword's default checkpoint.

- Add six native visible Hex8 quality criteria with explicit comparison thresholds, native failure counts/percent and zero-failure capture-state evidence. Preserve part visibility and mesh; integrate automatic workflow gates and recorded-threshold replay. Verify twelve pass/fail cases plus partial failures, hidden parts and blocked edits on synthetic 4.13.4 models.

- Add explicit scalar-history unit conversion and per-source normalization before curve alignment. Preserve rational scale provenance, reject incompatible dimensions and numerical range loss, and mark legacy shared-unit assumptions. Verify a mixed-unit force/relative-displacement -> stress/strain/work recipe in CI; no solver unit inference is implied.

- Add bounded absolute global node-coordinate/axis alignment through native grouped translations. Preserve untouched nodes/topology and part flags; report affected elements and checkpoints. Verify native quality gating, coordinate-parameter recording/replay, save/reopen and explicit recovery on a synthetic visible 4.13.4 mesh.

- Preserve explicit result/artifact dependencies through managed recording and include engineering/file steps of the recorded workflow. Changed selectors now drive new extraction IDs and new curve artifacts; unresolved dependencies and failed argument resolution require review. Verify changed-node replay in visible 4.13.4.

- Route native field/stress actions through the current visible GUI when used in a GUI workflow. Share SCL generation, ID/state matrix validation and Mises/tensor parsing with the batch backend; verify original state, selection, topology and part visibility without reopening or starting another LSPP.
- Verify selected-solid six-component stress/Mises, strain components and effective plastic strain on a representative private 4.13.4 result. Fix Windows SCL path separators without changing user preferences.

- Connect visible native node selection, component-history export and relative-displacement processing through a reusable three-step workflow; validate two component runs and native position/reference/displacement identity on one private result copy.
- Add explicit per-node/component scalar curves, bounded output counts and strict physical-time ordering. Preserve nodal FieldSpec and strict integer IDs/states. Restore and confirm GUI state through native command flow; keep animation stopped.
- Fix state-switch completion checks and application-reset working directories: history files always use owned absolute output paths.

- Unify keyword/d3plot GUI entity selection with shared user-ID contracts and verified reference/state scope. Use native bulk part selection to avoid thousands of individual node commands; retain exact ID readback.
- Preserve part visibility across selections; add all/active-parts scopes with explicit shared/orphan node and inversion semantics. Verify 9 synthetic keyword cases and 11 representative private result cases in visible 4.13.4; no alive/deletion, deformed-coordinate or full menu coverage is implied.
- Separate selection/inspection from mesh-edit checkpoints, avoiding unnecessary keyword exports while preserving dirty state and the saved recovery checkpoint.

- Add backend-aware ResultSelection/SamplingSpec/FieldSpec to native SCL and LASSO field/stress exports. Preserve immutable ordered selection provenance, sampling distinctions and actual displacement-reference transformations. These metadata contracts do not infer layer equivalence or physical units.
- Enforce strict integer entity/state/reader-index inputs at the MCP boundary for these extraction tools; reject meaningless nodal integration-point selectors.

- Implement workflow-boundary execution/check outcomes, automatic gates for mapped checks, strict scalar predicates and parameterized thresholds. Failed gates stop dependent actions while preserving original reports/checkpoints and explicit failure evidence.
- Accept prepared programs only as preparation, reject unknown/missing/unverified execution statuses, and distinguish attempted steps from completed steps. Add five reproducible synthetic file-backend gate cases and packaged MCP smoke verification.
- Verify gates in visible 4.13.4: failed checks block actual coordinate edits; explicit finding policies and thresholds survive managed recording, parameterization and replay. Provide an opt-in native acceptance driver; no hosted CI or arbitrary-version GUI certification is implied.

- Add same-session visible GUI mesh editing, duplicate-node merge, all/subset shell normal reversal, native entity selection, boolean selection, geometric predicates and native selection buffers.
- Add node/shell/part renumbering through the native dialog with mapping-log verification and scoped reference checks; handle zero padding in native node-list sets.
- Verify selection recording, parameter binding and replay against the same visible application.
- Add actual native shell Model Checking (13 selectable criteria, explicit thresholds and native statistics) and version-specific menu discovery. These do not imply full menu/solver coverage.
- Preserve existing user preferences in isolated GUI session configuration and recover exited sessions from checkpoints. Retry transient Windows manifest replacement failures without replacing the original early.

## 0.3.0

**v0.3.0 增量**：41 个安装过滤器与 7 个模板的接入，持久 GUI/检查点/托管录制和参数回放，网格变换/重复节点合并/质量检查，以及原生曲线到工程曲线和能量筛查。各项实机范围、后端区别和未完成项见 [v0.3 工作流与验证](docs/archive/2026-10/WORKFLOWS_v0.3.md)。

- Add trusted native command, cfile, SCL, embedded Python and macro preparation/execution with output contracts.
- Add persistent GUI sessions, checkpoints, recording/workflow templates, installation filter/template discovery and engineering curve/energy workflows.
- Track remaining preprocessing, postprocessing, menu and language-interface gaps explicitly. Native evidence is scoped by build and workflow.

## 0.2.0

- Add native solid-box meshing, planar shell extrusion, selected-node translation and element part reassignment with explicit output checks.
- Add native SCL stress/strain/nodal export, native Mises comparison, tensor invariants with explicit triaxiality/Lode definitions, and undefined hydrostatic ratios.
- Add native ASCII/XYPlot and SCLBinout curve routes, representative acceptance workflow, whole-field extrema, and owned staging cleanup.
- Add optional reader field/history-slot extraction, nested binout tables, strict numeric ASCII import and nonuniform curve calculus.
- Add coordinate-box node sets, bounded model reference checks and a prescribed-displacement shell-plate deck with native reopen.
- Add installed PyDYNA keyword/schema discovery, structured deck composition, scalar keyword editing and table-row editing with reimport checks.
- Document actual feature gaps, six PyDYNA documentation sections, source-version mismatches and private-data boundaries. Keyword catalogs and repeated tests are not feature-coverage claims.

## 0.1.0

- Initial MCP/CLI, native command/Python/SCL jobs, model/entity queries, shell plate and snapshot operations.
- Optional LASSO, LS-Reader and PyDYNA material adapters; source, command and tutorial references.
