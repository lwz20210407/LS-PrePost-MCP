# v0.3：可验证的常用流程

本轮实现安装资源接入、持久 GUI 基础、网格文件编辑和工程曲线。仍未覆盖 LS-PrePost 大部分功能；菜单中同名功能不等于全部选项都能自动执行。新增实机验证限 Windows、2026R1(v4.13.4)、已配置的应用内 Python。4.8/4.10 保留原有兼容矩阵，新功能不自动继承旧版本认证。

## 安装资源

`list_installation_assets` 读取当前安装的 `templates/kwfilter` 和 `templates/kwtemplate`；也可显式配置 `LSPP_TEMPLATE_ROOT`。厂商文件留在本机。

本机 41 个过滤器全部解析、应用于合成 deck，4 个命中该 deck 的卡片，其余返回空匹配。`apply_keyword_filter` 返回关键字块索引，保持模型完整；它不是 GUI Keyword Manager 的过滤器切换，也不是有效性检查。

`describe_installed_template` 返回参数、表达式、标签和用法。`instantiate_installed_template` 以白名单 AST 计算参数，检查依赖与循环，输出新 k 文件。输入种子模型须独立且已消解参数；合并时仅替换相同的 CONTROL、非 HISTORY DATABASE 单例卡。

| 安装模板 | 原生打开读回节点/单元 | 验证边界 |
|---|---:|---|
| 入门拉伸 | 96 / 75 | 参数展开、非空网格加载 |
| 显式设置 | 8 / 1 | 配合合成种子模型 |
| 冲击 | 8 / 1 | 配合种子及集合；不代表复制/冲击物理完成 |
| Taylor 轴对称 | 3388 / 3168 | 参数展开、非空网格加载 |
| ASTM 轴对称 | 769 / 662 | 参数展开、非空网格加载 |
| SALE 2D | 8 / 1 | 控制/结构化网格片段配合种子 |
| SALE 3D | 8 / 1 | 控制/结构化网格片段配合种子 |

这 7 项**不是**完整工程案例验收：未逐卡验证全部语义、没有生成并验收 SALE 域、没有运行求解器。`native_mesh_verified` 仅表示已读回非空节点，必须同时查看 `verification_scope`。

## 持久 GUI、检查点和录制

1. `start_gui_session` → `show_gui_session`：启动并显示本工具拥有的进程。
2. `open_in_gui_session` 或 `gui_session_action`：继续操作同一会话；输入采用有界副本。
3. `checkpoint_gui_session` → `reset_gui_session` → `restore_gui_checkpoint`：保存、清空、恢复。
4. `start_session_recording` → 若干有类型操作 → `stop_session_recording`。
5. `parameterize_workflow` 指定步骤参数 JSON 路径 → `run_workflow` 显式传入参数、会话。

实机：27 节点/8 实体的模型清空至 0/0，再恢复至 27/8，PID 不变。录制 2×2×2 盒体，宽度参数由 2 改为 5，回放后节点 X 最大值为 5。显示模式切换、隐藏/恢复部件已执行；部件可见性逐项读回核验。

### 执行方式与恢复合同

- Windows 传输只定位已核验 PID、创建时间、exe 的命令输入控件；不接管未知用户窗口。
- 每条请求有限时、唯一 ID、响应关联及产物校验；程序重启后可从磁盘找回会话。
- 未收到完成信号时状态为 `uncertain`；先调用 `recover_gui_session`，不得盲目重复。未决请求禁止覆盖。只读查询成功不能洗掉失败状态。
- 平移/旋转在原位 GUI 中出现“记录命令但未改变坐标”。当前 `gui_session_action` 对这两类操作使用 `native_checkpoint_batch_reopen`：保存检查点，启动独立原生 LSPP 进行编辑和坐标核验，成功后回原 GUI 重开。返回额外 native job ID，原 GUI PID 不变。**这不是原位内存编辑。**
- `reset_gui_session` 打开新的空 deck；不能用 `new` 命令代替，它在活跃 GUI 中可能重启软件并弹窗。
- 自动恢复仅核对迟到响应，不重放操作。真实超时/崩溃/模态框组合尚未全部实机验证；有失败边界自动测试。
- 手工界面修改不能完整映射为 `dirty`。重要模型应主动保存检查点；不将状态字段当作“用户从未编辑”的证明。
- 某些 GUI 构建保存相对文件名后标题栏显示偏好目录，与真实产物目录不同。工具依据新产物绝对路径和指纹验收；手工 Save As 时应核对目的路径。工具不改全局偏好。

### 录制范围

可执行 recipe 记录**经过 MCP 的成功操作**，保存基线模型和 GUI 需求。原生 `lspost.cfile` 单独保留，不声称任意鼠标操作均能语义回放。混用手工编辑时，应检查原始命令，不能把 managed recipe 当完整复刻。

`import_command_recording` 仅将认识的视图/显示、开文件、保存、部件显示、方块/球体创建、平移命令编译为有类型步骤。未知命令、任意 Python/系统命令、未接受的建模步骤会阻止回放。录制保存路径转换为新检查点，不覆盖旧文件。参数化后仍保留审查阻止状态。

## 网格闭环与后端边界

- 原生 `create_solid_sphere` 已验证新增节点及半径；不代表所有球网格质量都已认证。
- 原生 `rotate_mesh_nodes` 按全局轴、中心、角度检查所有选中和未选中节点，输出新 deck。实机 27 节点绕 Z 轴 90°，最大坐标误差约 2.4e-7。
- `transform_mesh_deck` 是 **PyDYNA+几何数学** 的平移/任意轴旋转/正比例缩放，再原生重开。只变换节点，载荷方向/材料坐标系不随之旋转。
- `merge_duplicate_mesh_nodes` 是 **PyDYNA** 的最低 ID 代表点合并；更新支持的单元、节点集、节点边界/载荷、历史引用。未知节点引用、坍塌单元和重复边界/载荷失败。不是原生 Duplicate Nodes 按钮封装。
- `inspect_mesh_quality` 是几何计算：线性三角/四边壳、四面体/六面体、两节点梁；面积、边长比、角度、翘曲、体积、8 Gauss 点 Jacobian。拒绝无法解析的结构卡，未知拓扑不能整体判通过。不是完整 Model Checking。
- 实机文件闭环：5→4 节点合并，壳与集合引用更新；旋转，质量检查，原生重开节点数核对成功。原输入字节保持不变。

原生 Duplicate Nodes、完整 Model Checking、通用拓扑修复、镜像方向处理和复制阵列仍是缺口。几何建模与由几何划网格暂后排。

## 具有明确语义的后处理

`native_tensile_postprocess` 调用原生 ASCII/XYPlot 提取力和两端节点位移，再调用 `build_tensile_curves`。显式指定实体、分量、面积、标距、力/长度/时间单位、正负号。面积按长度单位平方解释。

合成 ASCII 实机验收：末端力 200 N、两端相对位移 1.8 mm，面积 2 mm²、标距 10 mm → 工程应力 100 MPa、工程应变 0.18、积分功约 0.18 J。这是人工构造的可检查输入，不是求解结果。

`combine_history_curves` 支持求和/平均/差；所有曲线在共同时间区间的采样并集上线性插值，不外推。时间单位必须已一致。真应力/真应变转换为显式可选，限均匀、不可压缩、颈缩前假设；不会把它当单元 Cauchy 应力。

`native_energy_postprocess` 经原生 SCLBinout 提取命名 GLSTAT 能量，再检查 KE/|IE|、可选 HG/|IE| 及部分能量预算。动能/内能实机闭环通过。请求的沙漏能不可读时失败，省略沙漏能时输出空值，不补成真实 0。零内能分母为空；阈值是筛查，不能据此认证准静态或完整能量守恒。

仍缺：更广泛 ASCII 数据库、MPP binout、原生任意历史变量完整编号/层语义、局部坐标系、截面力/路径、完整虚拟应变计、统一色标/平均/积分点控制、动画视频验收。

## 菜单/工具栏映射

| 界面常用任务 | 本轮工具/验证 | 剩余范围 |
|---|---|---|
| File 打开、保存、清空、图像导出 | 会话副本打开、检查点、空 deck 重置、PNG | 全格式导入导出、所有偏好与保存选项 |
| View / 底部视角、显示、居中 | `set_gui_display`；等轴测/顶视、着色/线框、背景实机执行 | 所有组合、分屏、统一图例标尺 |
| 右侧/底部 Part 显示 | `set_gui_part_visibility`；隐藏/恢复逐部件验证 | 通用选择、群组、装配操作 |
| FEM/Element Tools 变换 | 原生平移/旋转作业；同窗口重开衔接 | 原位 GUI 编辑、其他变换/拓扑操作 |
| Duplicate Nodes / Model Checking | 文件后端合并、几何质量，原生重开 | 原生完整面板及全部指标 |
| Post / 底部状态、云图、动画 | 状态/云图有接口；动画命令提交实现 | 本轮未完整验证动画起止/视频，不能标已验收 |
| 宏与参数模板 | 托管操作录制、参数绑定和同会话回放 | 任意鼠标录制完整编译、交互分支/循环 |

公开仓库只保存代码、合成测试和此类非数据结论；用户工程模型、派生结果、原生日志和厂商模板不公开。

## 可复现验收

外部环境安装 dev、pydyna extras，并配置应用内 Python 后，可运行：

```powershell
python tools/run_workflow_acceptance.py --executable 'C:/path/lsprepost.exe' --workspace 'C:/path/owned-jobs' --keep-open
```

脚本只创建合成模型，在指定 workspace 的唯一子目录保存逐步报告。覆盖录制/参数回放、平移/旋转原生衔接、质量检查、可见性、清空/恢复和 PNG；默认关闭自己启动的会话，`--keep-open` 留作查看。进程未实际退出时不能将 `close_pending` 记为关闭通过。

本轮本地自动测试 65 项通过，包含 MCP stdio、响应关联、超时禁止重放、原生变换衔接的失败保护、参数化审查标记保留以及缺失能量/未知拓扑边界。自动测试不代替上述实机证据。
