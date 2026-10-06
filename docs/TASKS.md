# 任务目录

由 `tools/gen_docs.py` 从 `tasks.yaml` 生成，请修改源数据。

## 前处理

### P01 模型检视

状态：partial；版本：v0.5；里程碑：M3；层：T1

打开这个 k 文件，告诉我有哪些部件、材料、截面、集合、单元类型和数量，以及 Include 结构

验收：

- corpus:include_contact 上返回部件/材料/截面/集合/单元类型计数，与 LSPP Keyword Manager 读回一致
- 返回 Include 树（文件、相对路径、层级），与源文件结构一致
- 只读：输入文件哈希不变
- 超过 30 万单元的模型在 60 s 内返回摘要（corpus:large_private，私有语料）

现有入口：`inspect_model`, `inspect_keyword_deck`, `list_parts`, `list_nodes`, `inspect_gui_mesh`, `model_info`

缺口：

- model_info（关键字引擎）已输出 Include 树与 Part/材料/截面/集合关联；与 LSPP Keyword Manager 的原生读回对比未做
- 30 万单元 60 s 验收只在私有语料上测过（49 万单元 inspect 21.6 s），记录不在仓库

### P02 关键字卡片读改增删（Include 保真）

状态：partial；版本：v0.5；里程碑：M3；层：T1

把 Part 3 的材料换成 MAT_024 并改屈服应力，保存，Include 文件结构不要动

验收：

- corpus:include_contact 上改一张卡的一个字段，保存后只有该卡所在文件变化，其余文件字节级不变
- 被改文件中未改动的卡逐字节不变（含注释、空行、字段宽度）
- 新增一张卡片插入到指定文件的指定位置，字段宽度符合关键字定义
- 删除一张卡后引用检查报告悬空引用，不静默删除被引用对象
- 含 *PARAMETER 的字段可读出表达式原文与求值结果
- 保存后 LSPP 原生重开，实体计数与编辑前预期一致

现有入口：`update_keyword_fields`, `update_keyword_table_row`, `compose_keyword_deck`, `edit_keywords`

缺口：

- edit_keywords 已覆盖改字段 / 插卡 / 删卡 / PARAMETER，Include 结构与未改字节保持（单元测试）
- 保存后 LSPP 原生重开核对未做（原生侧，见 P11）
- corpus:include_contact 的验收用例依赖语料，CI 中跳过

### P03 材料 / 截面 / Part 创建与关联

状态：partial；版本：v0.5；里程碑：M3；层：T1+T2

新建一个 MAT_015 Johnson-Cook 材料和实体截面，赋给 Part 5

验收：

- 常用材料族 MAT_001/003/015/020/024/098 及 EOS 至少各一个配方，字段名来自关键字定义
- Part 关联修改后引用检查通过，原生重开后 Part Data 读回一致
- 单位制由调用者声明；缺少单位时拒绝生成需要单位的默认值

现有入口：`create_elastic_material`, `update_elastic_material`, `move_elements_to_part`, `edit_keywords`

缺口：

- 六个材料族与两个 EOS 已有引擎配方（edit_keywords 的 add_material / add_eos / add_section），Part 关联 add_part / set_part 已有；尚未登记为 run_recipe 的 T2 配方
- 保存后 LSPP 原生重开核对未做（原生侧，见 P11）

### P04 集合创建

状态：partial；版本：v0.5；里程碑：M3；层：T1

把 z=0 平面上的节点做成节点集；把弹体外表面做成 Segment 集

验收：

- 节点 / 单元 / Part / Segment 集合可由 Selector（ID、Part、盒、球、平面、外表面）生成
- 集合成员与 Selector 独立计算结果逐 ID 一致
- Segment 法向与指定方向一致（随机抽 20 个 segment 核对）
- 保存重开后集合 ID、成员、顺序保持

现有入口：`create_gui_entity_set`, `create_gui_segment_set`, `create_node_set_by_box`, `inspect_gui_entity_sets`, `create_entities`

缺口：

- 不生成 *_GENERATE / *_ADD 集合
- Selector 适配不支持按特征角的外表面和变形构型
- 保存重开核对未做（原生侧）

### P05 边界条件与载荷

状态：partial；版本：v0.5；里程碑：M3；层：T1

底面固支，顶面加 10 MPa 压力，弹体初速度 800 m/s

验收：

- SPC、规定运动、节点力、Segment 压力、重力、初速度、刚性墙、CNRB、无反射边界各有一个 L2 用例
- 曲线（DEFINE_CURVE）与载荷引用正确，单位由调用者声明
- 保存重开后卡片字段与预期一致，引用检查通过

现有入口：`create_gui_spc`, `create_gui_prescribed_motion`, `create_gui_segment_pressure`, `create_gui_nonreflecting_boundary`, `create_gui_nodal_load`, `create_entities`

缺口：

- 九类边界与载荷已有配方（create_entities / add_boundary）；R11 求解核对记录不在仓库
- 保存后 LSPP 原生重开核对未做（原生侧，见 P11）

### P06 接触定义与初始穿透检查

状态：partial；版本：v0.5；里程碑：M3；层：T1+T2

给弹体和靶板加侵蚀面面接触，检查初始穿透

验收：

- AUTOMATIC_SURFACE_TO_SURFACE、AUTOMATIC_SINGLE_SURFACE、ERODING_SURFACE_TO_SURFACE、TIED_SURFACE_TO_SURFACE_OFFSET、AUTOMATIC_NODES_TO_SURFACE 各一个配方
- 主从面可用 Part / Part 集 / Segment 集指定，引用检查通过
- 原生 Contact Check 报告初始穿透：节点 ID、穿透量；人为制造穿透的语料能被检出，无穿透语料报告 0
- 不自动修复；修复动作需显式调用并保留修复前副本

现有入口：`create_entities`

缺口：

- 五类接触配方已有（create_entities / add_contact）；原生 Contact Check 初始穿透报告未接
- 引擎的几何穿透估算 check_contacts 未接成工具

### P07 规则网格生成

状态：partial；版本：v0.6；里程碑：待排期；层：T2

生成一个 50×50×5 mm 的六面体靶板，单元 0.5 mm

验收：

- 板、块、圆柱、球、圆环各一个配方，节点数/单元数/包围盒与参数一致
- Block Mesher 常用流程一个配方

现有入口：`create_shell_plate`, `create_solid_box`, `create_solid_sphere`, `extrude_shell_part`

缺口：

- 壳板只支持 XY 矩形；没有圆柱 / 圆环 / Block Mesher

### P08 网格编辑

状态：partial；版本：v0.5；里程碑：M3；层：T1+T2

把 Part 2 沿 X 平移 10 mm，再关于 YZ 平面镜像复制一份，合并重复节点，统一法向

验收：

- v0.5 范围：平移、旋转、镜像、复制、合并重复节点、法向统一、按范围重编号、删除单元（8 项）各一个 L2 用例
- 每项：选中实体坐标/连接按预期变化，未选实体逐值不变，引用检查通过
- 合并与重编号在超过 30 万单元模型上完成（私有语料）
- 偏置、阵列、Detach、Smooth 走 T2 配方，可在 v0.6 补齐

现有入口：`translate_gui_nodes`, `rotate_gui_nodes`, `set_gui_node_coordinates`, `merge_gui_duplicate_nodes`, `reverse_gui_shell_normals`, `renumber_gui_entities`, `create_gui_nodes`, `create_gui_elements`, `replace_gui_node`, `translate_mesh_nodes`, `rotate_mesh_nodes`, `transform_mesh_deck`, `merge_duplicate_mesh_nodes`, `move_elements_to_part`, `mesh_ops`

缺口：

- mesh_ops 已覆盖平移 / 旋转 / 镜像 / 复制 / 阵列 / 偏置 / 合并重复节点 / 法向统一 / 按范围重编号 / 删除单元
- 30 万单元合并与重编号只在私有语料上测过，记录不在仓库
- GUI 与文件后端的近重复工具仍在（I08 别名期内）

### P09 模型检查

状态：partial；版本：v0.5；里程碑：M3；层：T1

检查这个模型能不能直接提交计算，列出问题

验收：

- 一次调用汇总 Keyword Check、壳/实体/四面体质量、重复节点、未引用对象、悬空引用，每条问题带实体 ID
- 人为注入的 6 类错误全部检出；干净语料报告 0 个错误
- 质量阈值由调用者给定，未给定时只报告数值不下结论
- 只读：不修改模型

现有入口：`check_gui_keywords`, `check_gui_shell_quality`, `check_gui_solid_quality`, `inspect_mesh_quality`, `inspect_gui_mesh_quality`, `validate_model_references`, `check_model`

缺口：

- check_model 汇总引用 / 重复 / 质量 / 坐标舍入 / 自由格式列宽 / 规定运动曲线长度；梁与厚壳质量未覆盖
- 与原生 Keyword Check 的交叉核对未做

### P10 控制与输出卡

状态：partial；版本：v0.5；里程碑：M3；层：T2

终止时间 50 µs，输出 d3plot 每 1 µs，GLSTAT/MATSUM/RCFORC 每 0.1 µs，开启沙漏控制

验收：

- CONTROL_TERMINATION / TIMESTEP / HOURGLASS / ENERGY、DATABASE_BINARY_D3PLOT、DATABASE_ASCII 常用库各有配方
- 参数缺失时拒绝，不填默认物理值
- 生成卡片经 P02 引擎插入，原生重开通过

现有入口：`instantiate_installed_template`, `apply_keyword_filter`, `edit_keywords`

缺口：

- 终止 / 时间步 / 沙漏 / 能量 / d3plot / 34 个 ASCII 库已有引擎配方（edit_keywords 的 set_control / add_hourglass），缺参数时拒绝；尚未登记为 run_recipe 的 T2 配方
- 保存后 LSPP 原生重开核对未做（原生侧，见 P11）

### P11 保存并原生重开验证

状态：partial；版本：v0.5；里程碑：M3；层：T1

保存修改后的模型并确认 LSPP 能正常读回

验收：

- 保存带 Include 的模型：结构保持（同 P02 判据）
- 保存后自动原生重开，核对实体计数、Part 列表与预期一致，失败时返回差异
- 不覆盖输入文件；输出路径在 job 目录或用户显式指定位置

现有入口：`export_keyword`, `checkpoint_gui_session`

缺口：

- 带 Include 的模型拒绝保存

### P12 运动副与刚体连接

状态：partial；版本：v0.5；里程碑：M3；层：T1

在曲柄与机架之间建转动铰并加转动电机，连杆与滑块之间建转动铰，滑块与导轨之间建移动副，检查刚体归属与过约束

验收：

- 九类运动副各一个配方，节点对按 R17 Vol I *CONSTRAINED_JOINT 的规则放置，两侧刚体归属正确，引用检查通过
- 每类运动副的 R11 算例与解析解或官方示例一致，运动学量误差小于 1%
- 检查在公开与本地真实模型上没有误报，能检出节点不重合、两侧刚体不一致、两侧同一刚体、过约束
- 原生重开后 Joint 定义读回一致

现有入口：`create_entities`, `check_model`

缺口：

- 九类运动副（球铰、转动、圆柱、平面、万向、移动、锁定、转动电机、移动电机）由 add_joint 写出；两侧可为刚体 Part（额外节点）、已有节点刚体，或由所选节点新建的节点刚体
- 证据在 docs/decisions/evidence/p12：R11 解析解算例；5 个官方示例删除原运动副后重建，4 个逐值相同、1 个动能差 1e-6；真实模型检查的误报已清零
- 由所选节点新建节点刚体（变形体一侧）只有单元测试，尚无 R11 算例
- 未做：*CONSTRAINED_JOINT_STIFFNESS（限位、摩擦）的创建；齿轮、齿条、滑轮、螺旋、等速、HARMONIC 只登记，不做几何检查；LSPP 原生重开核对（P11）

## 后处理

### Q01 结果概览

状态：partial；版本：v0.5；里程碑：M2；层：T1

这个 d3plot 有多少个状态，时间范围多少，有哪些变量，有没有删除单元

验收：

- 返回状态数、每个状态时间、可用变量（含 HSV 数量）、部件、单元类型、删除单元计数
- 同时列出同目录 binout / ASCII 文件及其包含的库
- LSPP 与 LASSO 两个后端结果一致（状态数、时间数组）

现有入口：`inspect_d3plot_scl`, `inspect_d3plot_database`, `inspect_result_fields`, `inspect_binout`, `inspect_binout_variable`, `inspect_lsreader`, `inspect_dpf_results`

缺口：

- 7 个清点工具并存

### Q02 云图出图

状态：partial；版本：v0.5；里程碑：M2；层：T1

出 0.5 ms 时刻弹体部件的 von Mises 云图，色标 0-1500 MPa，等轴测视角

验收：

- 按时间或状态号出图；时间请求返回实际匹配状态
- 标准变量（应力分量、Mises、有效塑性应变、位移、速度、厚度）在实体与壳上各一个用例
- 壳的上/中/下层可选；平均方式可选，默认 MinMax
- 保留模型标题与 LSPP 原生结果名称，不追加自定义文字
- 图像中色标极值与 Q03 同一量的数据极值一致（容差内）

现有入口：`render_gui_field`, `render_snapshot`

缺口：

- 壳层 / 积分点未认证；只有固定色标上下限

### Q03 场数据提取

状态：partial；版本：v0.5；里程碑：M2；层：T1

把第 20 个状态 Part 3 所有单元的应力六分量导出成 CSV

验收：

- 输出 CSV/NPZ，元数据包含量、分量、单位、状态、时间、层/积分点、坐标系、后端
- 实体与壳各一个用例；LSPP 与 LASSO 结果逐实体一致（容差内）
- 删除单元按 Q04 掩码策略处理并在元数据中注明

现有入口：`extract_native_fields`, `extract_native_stress`, `extract_d3plot_field`, `extract_d3plot_stress`, `extract_nodal_results`, `extract_d3plot_nodal`, `extract_lsreader_nodal`, `export_dpf_result`

缺口：

- 8 个工具按后端各一份；壳层未认证；实体积分点 2-8 原生返回错值被拒绝

### Q04 工程量与失效掩码

状态：partial；版本：v0.5；里程碑：M2；层：T1

计算靶板所有单元的应力三轴度和 Lode 参数，排除已删除单元，找出最大值所在单元

验收：

- Mises、主应力、三轴度、Lode 参数、Lode 角、等效塑性应变在实体与壳上与独立计算一致
- 公式定义（尤其 Lode 的符号约定）写进结果元数据
- 掩码策略 alive / all / deleted 可选；极值附带实体 ID 与状态

现有入口：`compute_stress_invariants`, `extract_native_stress`, `inspect_result_validity`

缺口：

- 只有实体有原生验证；壳单元缺失

### Q05 时程曲线（History）

状态：partial；版本：v0.5；里程碑：M2；层：T1

提取节点 1001 的 Z 位移和单元 500 的 Mises 随时间变化，以及 Part 2 的动能

验收：

- 节点、单元、部件、全局四种模式各一个用例
- 一次请求多个实体，返回多条曲线，每条带实体 ID、分量、单位
- 与 LASSO 读回的同一量一致（容差内）

现有入口：`extract_node_history`

缺口：

- 只有节点；没有单元 / 部件 / 全局；不能批量

### Q06 binout / ASCII 全库曲线

状态：partial；版本：v0.5；里程碑：M2；层：T1

从 binout 取 RCFORC 里接触 2 的合力和 SECFORC 截面 1 的 Z 向力

验收：

- GLSTAT、MATSUM、RCFORC、SECFORC、NODOUT、ELOUT、SLEOUT、NODFOR、SPCFORC、RBDOUT、NCFORC、DEFORC 各一个用例
- 按名称指定分量（不用 UI 编号）；返回单位与原始列名
- MPP 分片 binout 合并后与单机结果一致（corpus:mpp_binout）
- LSPP 与 LASSO 结果一致（容差内）

现有入口：`extract_native_binout_curve`, `extract_native_ascii_curve`, `extract_binout_curve`, `extract_binout_table`, `extract_ascii_curve`

缺口：

- 原生只有 NODOUT / GLSTAT / MATSUM 部分量；ASCII 只接 6 类且要填 UI 分量编号
- MPP 分片 binout 被拒绝

### Q07 曲线运算

状态：partial；版本：v0.5；里程碑：M2；层：T1

力-位移曲线转成工程应力应变，再转真应力应变，SAE 600 滤波

验收：

- 单位换算、相对量、力-位移、工程/真应力应变、微分、积分、重采样、SAE/Butterworth 滤波、FFT、Cross Plot 各有 L1 用例（对解析解）
- 滤波结果与 LSPP XYPlot 同参数滤波对比一致（L2）
- 每次运算把公式与参数写进结果元数据

现有入口：`process_curve`, `convert_history_units`, `combine_history_curves`, `build_tensile_curves`

缺口：

- 缺 SAE / Butterworth 滤波、重采样、FFT、Cross Plot、真应力应变

### Q08 XYPlot 出图

状态：partial；版本：v0.5；里程碑：M2；层：T1

把 3 个工况的力-位移曲线画在一张图上，带图例，导出 PNG 和 CSV

验收：

- 最多 10 条曲线同图；图例、坐标轴标题与范围、对数轴可设
- PNG 与同时导出的 CSV 数值一致
- 批处理上下文可用（不依赖可见 GUI），依据 E5 结论

现有入口：`export_gui_curve_plot`

### Q09 动画导出

状态：partial；版本：v0.5；里程碑：M2；层：T1

导出从 0.1 ms 到 0.8 ms、每隔 2 帧、20 fps 的 Mises 云图动画

验收：

- 状态范围、步长、帧率可设；MP4 与 GIF 两种格式
- 帧数、时间顺序、分辨率与参数一致；文件可解码
- 首、末帧与 Q02 对应状态的静态图一致（感知哈希容差内）

现有入口：`export_gui_animation`, `export_gui_field_animation`, `control_gui_animation`

缺口：

- 只能从第 1 个状态、步长 1 导出；没有 GIF

### Q10 截面力与剖切面

状态：partial；版本：v0.6；里程碑：待排期；层：T2

在 z=10 mm 处切一刀，输出截面上的合力时程和剖面云图

验收：

- 剖切面位置/法向可设；剖面云图一个配方
- 截面合力时程与 SECFORC（同截面定义）一致

现有入口：无

缺口：

- 剖切云图真实模型抓图留待原生环境统一窗口执行

### Q11 测量

状态：partial；版本：v0.6；里程碑：待排期；层：T1+T2

量一下这两个节点的距离、这三个节点的夹角，以及 Part 3 的质量和体积

验收：

- F4 剩余常用项（面积、体积、质量、惯量、点到面距离、部件间隙）各一个用例
- 质量类测量缺少密度或单位时拒绝

现有入口：`measure_gui_geometry`, `measure_parts`

缺口：

- F4 的 21 项中完成 6 项；缺面积、质量、惯量、间隙等

### Q12 能量检查

状态：partial；版本：v0.5；里程碑：M2；层：T1

检查能量是否守恒，沙漏能占比是多少

验收：

- 总能量、动能、内能、沙漏能、滑移能、外功、阻尼能、侵蚀能逐项输出，并给出平衡残差
- 阈值由调用者给定；未给定时只报告比例不下结论
- 按部件（MATSUM）分解

现有入口：`assess_energy_balance`, `native_energy_postprocess`, `check_energy`

缺口：

- 原生 GLSTAT 完整 8 项能量提取与 MATSUM 真实算例跨后端一致性留待原生环境统一执行

## 自动化

### A01 命令栏 Command（单条原生命令）

状态：done；版本：v0.5；里程碑：M1；层：T1

执行一条 LSPP 命令，就像在左下角输入栏里敲一样，并告诉我 LSPP 返回了什么

验收：

- 10 条代表命令（打开、选择、变换、显隐、视图、出图、保存）在 batch 与 session 两种上下文各执行一次，产物核对通过
- 返回 LSPP 回显与报错原文（来自 lspost.msg 本次增量）
- 无效命令明确失败，返回 LSPP 报错原文
- 4.10 回归子集通过

现有入口：`prepare_native_program`, `execute_native_program`, `execute_gui_command`, `run_on_version`

### A02 cfile 命令流

状态：done；版本：v0.5；里程碑：M1；层：T1

运行这个 cfile，把里面的 width 换成 8 再跑一次

验收：

- 多行 cfile 建模 → 保存 → 重开，batch 与 session 各一次
- 数值与字符串参数替换（字符串参数禁止注入路径分隔符以外的命令）
- 中途某行失败时返回行号与 LSPP 报错
- 每个配方登记 runc= 与 c= -nographics 是否可用（来自 I10 矩阵）
- 4.8 / 4.10 / 4.13 回归子集通过

现有入口：`prepare_native_program`, `execute_native_program`

### A03 SCL 脚本

状态：done；版本：v0.5；里程碑：M1；层：T1

运行这个 SCL 脚本，读出所有节点坐标写成 CSV

验收：

- 读写数组并输出 CSV；结果与 A04 的同等 Python 任务一致
- 编译错误明确失败并返回行号
- 4.8 / 4.10 / 4.13 回归子集通过

现有入口：`prepare_native_program`, `execute_native_program`, `probe_scl`

### A04 应用内 Python 脚本

状态：done；版本：v0.5；里程碑：M1；层：T1

用 LSPP 内置 Python 读出每个 Part 的单元数和最大位移

验收：

- DataCenter / LsPrePost 调用；脚本参数传递；多文件依赖包
- Python 异常返回完整栈
- 大数组写 NPZ，返回路径、shape、dtype，不塞进 MCP 响应
- 4.13 全量、4.10 子集通过

现有入口：`prepare_native_program`, `execute_native_program`

### A05 原生宏执行

状态：partial；版本：v0.5；里程碑：M1；层：T1

运行这个 .mac 宏，参数 N1 取 103，拾取的节点用 Part 2 顶面节点

验收：

- 用户 .mac 文件（含 *macro begin/end、parameter 默认值、&name / &{name}、多宏块）在 batch 与 session 各运行一次
- 字符串与数值参数；表达式默认值按 LSPP 语义求值或明确拒绝
- (n/e/p) 拾取参数可由 Selector 结果绑定（拾取绑定验收随 G03 在 M3 完成）
- 不支持的语法（如 interactive 暂停）明确拒绝并给出行号，不静默删除
- 课程 / 教程中至少 5 个真实宏样例跑通

现有入口：`prepare_native_program`

缺口：

- 只支持数值参数；拒绝字符串参数、表达式默认值、interactive 暂停、分号多命令、嵌套宏
- 拾取域只接受正整数 ID，不能用选择结果绑定
- create_native_macro / run_native_macro 实为自定义 JSON 模板，名称与原生宏混淆

### A06 宏安装与快捷键管理

状态：todo；版本：v0.6；里程碑：待排期；层：T1

把这个宏装到 LSPP 宏工具栏，并绑定到 Shift+F3

验收：

- 宏加载到会话宏面板、宏工具栏按钮、Shift+F 快捷键绑定、启动时自动加载
- 修改用户全局配置前备份，可一键恢复；不默默覆盖已有绑定

现有入口：无

### A07 命令录制转配方

状态：partial；版本：v0.5；里程碑：M4；层：T1

我刚在 GUI 里手工做了一遍出图流程，把它变成可以换参数重跑的配方

验收：

- 读取一次 GUI 会话的命令记录，剔除纯视图噪声，生成 cfile 或 .mac 配方
- 未识别命令原样保留并标记 unverified，不丢弃、不阻止回放
- 指定 2 个参数后批处理回放，产物随参数正确变化
- 生成的配方附带一个 L2 用例骨架

现有入口：`start_session_recording`, `stop_session_recording`, `import_command_recording`, `parameterize_workflow`

缺口：

- 只编译 13 种命令；未知命令阻止回放

### A08 配方库

状态：partial；版本：v0.5；里程碑：M1；层：T1

有没有现成的配方能做 Block Mesher 划网格？有就用它

验收：

- recipe.yaml 规范：名称、任务 ID、通道、参数 schema、输出合同、versions_verified、L2 用例
- find_recipe 按关键词 / 任务 ID / 通道检索；run_recipe 校验参数后执行
- M1 至少 5 个；v0.5 发布时至少 30 个，每个都有通过的 L2 用例
- 现有 JSON 模板迁入，旧工具名保留为别名

现有入口：`create_native_macro`, `run_native_macro`, `list_installation_assets`, `describe_installed_template`, `instantiate_installed_template`, `apply_keyword_filter`

缺口：

- M1 五个示范配方已验证；v0.5 发布前仍需至少三十个配方及各自 L2，安装过滤器/模板的全量归并尚未完成

### A09 参数化批量

状态：partial；版本：v0.5；里程碑：M4；层：T1

弹速从 600 到 1000 m/s 每隔 50 跑一组前处理，生成 9 个 k 文件，并汇总结果

验收：

- 50 组参数表，BatchEngine 并行 N 进程执行，单组失败不影响其他组
- 中断后续跑不重复执行已完成组
- 汇总表（CSV）与对比曲线图
- 每组产物与参数的对应关系可追溯

现有入口：`run_workflow_sweep`, `create_workflow`, `run_workflow`, `inspect_workflow`

缺口：

- 只支持 1-20 组顺序执行

### A10 知识检索

状态：partial；版本：v0.5；里程碑：M1；层：T1

LSPP 里给 Segment 集加压力的命令怎么写？*CONTACT_ERODING 的 SFS 字段是什么意思？

验收：

- 可检索命令手册、Scripting API、关键字字段、用户指南章节、配方、KNOWN_ISSUES 六类
- 每条结果带来源、版本、证据等级（文档记载 / 有源码实例 / 本机验证）
- 私有资料索引放在仓库外，由环境变量指定路径
- 20 条典型查询的命中率评测（前 3 条结果含正确答案的比例）记录在案

现有入口：`search_commands`, `search_knowledge`, `search_workflows`, `list_pydyna_keywords`, `describe_pydyna_keyword`

缺口：

- 旧二十题评测受到题面专用词表调优影响，不作为完成依据；已冻结六类二十四题独立留出集，记录未经调优的结果，跨语言检索与完整来源覆盖仍需后续工作

## 通用

### G01 视图控制

状态：partial；版本：v0.5；里程碑：M2；层：T1

换成前视图，放大 2 倍，居中到 Part 3

验收：

- 标准视图、缩放、平移、绕轴旋转、fit、居中到 Selector、命名视图保存 / 恢复
- 同一视图参数两次出图像素一致

现有入口：`set_gui_display`

缺口：

- 缺命名视图保存 / 恢复、居中到选区

### G02 显示控制

状态：partial；版本：v0.6；里程碑：待排期；层：T1+T2

隐藏 Part 1 和 2，Part 3 改成半透明红色，显示单元编号

验收：

- 部件显隐 / 颜色 / 透明度、单元 Blank、实体标签各一个用例
- 显示状态变化不改变模型数据

现有入口：`set_gui_part_visibility`, `set_gui_entity_visibility`, `set_gui_display`

缺口：

- 缺颜色、透明度、标签、节点符号、Shrink

### G03 统一选择器

状态：partial；版本：v0.5；里程碑：M3；层：T1

选出 Part 2 外表面上 z>10 的节点

验收：

- Selector 支持 ID、Part、集合、盒、球、平面、外表面、特征角传播、布尔组合
- 参考坐标与指定状态的变形坐标两种模式
- 同一 Selector 在 keyword 与 d3plot 上解析结果一致（同一网格）
- 选择结果可直接被 P04 / P08 / Q03 / Q05 / A05 使用
- 选择操作不改变显隐状态（回归：pall 会重置 blank 的已知坑）

现有入口：`select_gui_entities`, `select_gui_nodes_by_box`, `select_gui_nodes_by_sphere`, `select_gui_nodes_by_plane`, `select_gui_shell_topology`, `combine_gui_selections`, `save_gui_selection_buffer`, `load_gui_selection_buffer`

缺口：

- 选择逻辑分散在 8 个工具；只在参考坐标；实体外表面传播未认证

### G04 实体识别 Identify

状态：partial；版本：v0.5；里程碑：M2；层：T1

节点 1001 的坐标和它在第 30 个状态的位移是多少？属于哪个 Part？

验收：

- 节点 / 单元 / Part 的 ID、坐标、连接、所属 Part / 材料、指定状态的结果值
- 结果值与 Q03 同一量一致

现有入口：`list_nodes`, `get_element_connectivity`, `inspect_gui_mesh`

## 基础设施

### I01 执行引擎 Engine（BatchEngine 默认 + SessionEngine 可选）

里程碑：M1

状态：partial；验证：L1

证据：[src/ls_prepost_mcp/engine/batch.py](../src/ls_prepost_mcp/engine/batch.py), [src/ls_prepost_mcp/engine/session.py](../src/ls_prepost_mcp/engine/session.py), [tests/test_engines.py](../tests/test_engines.py), [tests/test_engine_native.py](../tests/test_engine_native.py), [docs/decisions/evidence/i01/report.md](../docs/decisions/evidence/i01/report.md), [docs/decisions/evidence/i01-followup/report.md](../docs/decisions/evidence/i01-followup/report.md), [docs/decisions/evidence/i01-staging/report.md](../docs/decisions/evidence/i01-staging/report.md), [docs/decisions/evidence/i01-batch-contract/report.md](../docs/decisions/evidence/i01-batch-contract/report.md), [docs/decisions/evidence/i01-process-lifetime/report.md](../docs/decisions/evidence/i01-process-lifetime/report.md), [docs/decisions/evidence/i01-log-decoding/report.md](../docs/decisions/evidence/i01-log-decoding/report.md)

- 现有 5 个批处理调用方与 GUI 会话统一到 Engine.run(job) -> JobResult
- 删除 gui_session_action 中运行时替换 _native 的做法
- 批处理与会话使用同一套配置隔离与日志读取

### I02 语义合同 core/contracts.py

里程碑：M1

状态：done；验证：L1

证据：[src/ls_prepost_mcp/core/contracts.py](../src/ls_prepost_mcp/core/contracts.py), [tests/test_core_contracts.py](../tests/test_core_contracts.py), [tests/test_workflow_gates.py](../tests/test_workflow_gates.py), [tests/test_reference_workflow.py](../tests/test_reference_workflow.py)

- ModelRef、Selector、FieldSpec、CurveSpec、JobResult、Artifact 以 pydantic 定义
- JobResult.status 只有 succeeded / failed / partial / unverified 四种
- 工作流门槛只读 JobResult

### I03 命令构建器与版本能力表

里程碑：M1

状态：partial；验证：L2

证据：[src/ls_prepost_mcp/native/commands.py](../src/ls_prepost_mcp/native/commands.py), [src/ls_prepost_mcp/native/versions.py](../src/ls_prepost_mcp/native/versions.py), [tests/test_native_commands.py](../tests/test_native_commands.py), [tests/test_version_resources.py](../tests/test_version_resources.py), [docs/decisions/evidence/i03-version-resource/report.md](../docs/decisions/evidence/i03-version-resource/report.md), [docs/decisions/evidence/i03/report.md](../docs/decisions/evidence/i03/report.md), [docs/decisions/evidence/i03-paths/report.md](../docs/decisions/evidence/i03-paths/report.md), [tests/test_engine_native.py](../tests/test_engine_native.py)

- genselect / fringe / anim 等命令只在 native/commands.py 生成，有黄金输出测试
- 版本差异集中在能力表，src 其他位置不出现版本判断

### I04 原生回归框架 pytest -m native

里程碑：M1

状态：partial；验证：待记录

证据：[docs/decisions/evidence/i04/report.md](../docs/decisions/evidence/i04/report.md), [docs/decisions/evidence/i04-window/report.md](../docs/decisions/evidence/i04-window/report.md), [docs/decisions/evidence/i04-identity/report.md](../docs/decisions/evidence/i04-identity/report.md), [tools/native_regression.py](../tools/native_regression.py), [tests/test_public_corpus_native.py](../tests/test_public_corpus_native.py), [tests/corpus/public_cases.json](../tests/corpus/public_cases.json), [tests/test_native_acceptance.py](../tests/test_native_acceptance.py), [tests/test_native_regression.py](../tests/test_native_regression.py), [tests/test_native_remote.py](../tests/test_native_remote.py), [tests/test_native_input_preconditions.py](../tests/test_native_input_preconditions.py)

- 补测从 M0 转入的 13 个 UU 远程格（4.13/4.10 的 runc 五通道共 10 格，以及两版本 nographics 原生宏和 4.13 会话原生宏共 3 格），记录执行、PNG、MP4 结果与用户确认的断开时间窗
- 55 个 tools/run_* 收编为 57 个带 marker 的 pytest 用例，共享 fixture
- 一条命令生成 Markdown 报告；私有语料通过环境变量启用

### I05 知识库索引

里程碑：M1

状态：partial；验证：L1

证据：[src/ls_prepost_mcp/knowledge_index.py](../src/ls_prepost_mcp/knowledge_index.py), [src/ls_prepost_mcp/keyword_documentation.py](../src/ls_prepost_mcp/keyword_documentation.py), [tools/build_knowledge_index.py](../tools/build_knowledge_index.py), [tests/test_knowledge_index.py](../tests/test_knowledge_index.py), [tests/test_keyword_index_coverage.py](../tests/test_keyword_index_coverage.py), [docs/decisions/evidence/i05-catalog/report.md](../docs/decisions/evidence/i05-catalog/report.md)

- 命令表、Scripting API、关键字定义、用户指南章节、配方、KNOWN_ISSUES 建立索引
- 公开部分可入仓库；私有课程资料的索引在仓库外

### I06 文档生成

里程碑：M0

- tools/gen_docs.py 由 tasks.yaml 与 registry 生成 TASKS.md、TOOLS.md、COMPATIBILITY.md、README 能力表
- CI 检查生成物与源数据一致

### I07 raw-preserving 关键字引擎

里程碑：M3

负责人：claude

集成约束：Claude 在 claude/keyword-engine 开发，M3 经 PR 合入 main；代码在 src/ls_prepost_mcp/domain/model/，目标工具在 model_target_tools.py。

状态：done；验证：L1

证据：[src/ls_prepost_mcp/domain/model/deck.py](../src/ls_prepost_mcp/domain/model/deck.py), [tests/test_keyword_engine.py](../tests/test_keyword_engine.py), [tests/test_keyword_engine_formats.py](../tests/test_keyword_engine_formats.py), [tests/test_keyword_engine_parameters.py](../tests/test_keyword_engine_parameters.py), [tests/test_keyword_engine_long.py](../tests/test_keyword_engine_long.py)

- 按块解析、Include / INCLUDE_PATH / PARAMETER 树、定点写回、字节级往返测试
- 字段宽度取自关键字定义，不硬编码

### I08 工具迁移与别名

里程碑：M1

状态：done；验证：L1

证据：[src/ls_prepost_mcp/operation_registry.py](../src/ls_prepost_mcp/operation_registry.py), [src/ls_prepost_mcp/data/operations.json](../src/ls_prepost_mcp/data/operations.json), [tests/test_operation_registry.py](../tests/test_operation_registry.py), [pyproject.toml](../pyproject.toml)

- 全部现有工具逐一映射到 T1 工具 / 配方 / 别名 / 废弃
- 旧名作为别名保留至 v0.6；registry 生成 TOOLS.md

### I09 Agent 场景评测 L3

里程碑：M2-M4

负责人：claude

状态：partial；验证：L1

证据：[tools/run_l3.py](../tools/run_l3.py), [tests/test_l3_harness.py](../tests/test_l3_harness.py), [docs/decisions/evidence/i09/report.md](../docs/decisions/evidence/i09/report.md)

- 20 道自然语言任务（后处理 8、前处理 8、自动化 4），Claude 与 Codex 各跑一遍
- 记录成功率、工具调用次数、失败原因

### I10 执行通道实验与决策

里程碑：M0

状态：done；验证：L2

证据：[docs/decisions/0001-session-transport.md](../docs/decisions/0001-session-transport.md), [docs/decisions/0001-experiment-evidence.json](../docs/decisions/0001-experiment-evidence.json), [tools/experiments/run_remote_probe.py](../tools/experiments/run_remote_probe.py)

- E1-E5 实验记录（见评审方案 4.4）
- 通道矩阵：5 个通道 × (runc= / c= -nographics / session) × 是否可渲染 × 锁屏下是否可用
- ADR：会话传输方式的决定

### I11 回归语料清单

里程碑：M0

- tests/corpus/manifest.yaml 仅登记公开语料 ID 与相对统一根目录的路径；来源 URL、许可、SHA256、特征从外部 public-keyword/manifest.json 和 public-results/manifest.json 读取，覆盖任务由本文件 corpus 引用关联
- LSPP_CORPUS_DIR 指向包含 public-keyword、public-results、local-book 的统一根目录；local-book 作为受限语料只登记 ID 和相对路径，内容及派生数据不提交、不公开；私有 fangzhen/deployed_wings 仍仅登记 ID
- 必备语料：include_contact（含 Include 与接触的 keyword）、shell_d3plot、solid_d3plot、binout_forces（含 RCFORC/SECFORC）、mpp_binout、large_private
- 找不到公开语料的项明确标为缺口
