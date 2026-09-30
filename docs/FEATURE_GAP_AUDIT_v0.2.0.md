# v0.2.0 功能与界面缺口盘点

审计日期：2026-10-01。代码基线：tag `v0.2.0` / commit `f6098532840137d5406b00c97b4877cbafdacffb`。

**结论：当前实现了执行框架及若干经过验证的前后处理流程，尚未覆盖 LS-PrePost 大部分常用功能。** 命令目录、PyDYNA 类目录、手册条目、安装资源和反复运行同一组测试，都不能直接计为功能覆盖。

本盘点以官方 2026R1 指南的菜单、工具栏和功能章节为主要目录，并检查了本机 4.13.4 主界面及 4.8/4.10/4.13 安装资源。工具栏可定制，位置和可见按钮因版本、窗口宽度及用户配置而变化；没有声称逐个展开了三个版本的所有菜单和对话框字段。

状态约定：**已验证子集**＝有对应可执行操作及针对性验证；**部分**＝只有部分模式、非原生数据接口或任务内部动作；**未开发**＝没有相应经过验证的自动化流程，即使已有文档或参考命令。下述“已验证”不等于整个功能模块已完成。

## 1. 前处理

| 能力 | v0.2.0 实际可做 | 主要缺口 |
|---|---|---|
| 几何建模 | 无完整 CAD 几何工具链 | 参考点/轴/面、曲线、曲面、实体、布尔、圆角、倒角、几何修复、中面 |
| 规则壳网格 | 原生 XY 矩形板，指定尺寸/划分/ID，保存 | 任意四边形、曲面网格、圆环/球壳/圆柱壳、分区与局部种子 |
| 规则实体网格 | 原生六面体方块网格 | 圆柱/球体、复杂六面体、扫掠与自动四面体 |
| 壳生成实体 | 单个 XY 平面壳部件沿 +Z 拉伸，保留原壳 | 任意方向、面拖动/旋转/偏置、两壳集连接、沿路径扫掠、自动移除源壳 |
| 节点编辑 | 原生指定节点平移；PyDYNA 表格坐标编辑/创建 | 图形拾取、替换、删除、对齐、投影、节点归并、邻接关系保护 |
| 单元编辑 | 原生转移部件；表格层面的单元/连接数据创建和修改 | 图形增删、拆分/合并、重连、方向、法向、复合层、退化单元处理 |
| 网格变换 | 指定节点平移 | 旋转、缩放、镜像、复制阵列及共享节点/ID 一致性 |
| 选择与集合 | 显式 ID、坐标盒选节点并建立节点集 | 部件/材料/表面/拓扑/质量条件选择；单元、面、部件集；布尔组合 |
| 模型组织 | 部件 ID 查询、有限归属修改 | Assembly、GPart、Subsystem、Group、模型合并、重编号、差异比较 |
| 材料/截面/边界/载荷 | MAT_001 专用操作、位移加载壳板模板；通用关键字字段接口 | 通用工程配置流程、材料本构适用性、坐标系统、接触/初始条件关联校验 |
| k 文件 | 新建/导出独立 deck、修改后另存、原生重开 | 完整 include 树打包/重写、参数表达式、二进制 dynain、格式/注释/顺序精确保留 |
| 模型检查 | 部分 ID/引用检查；已开发操作的数量/坐标/归属校验 | Jacobian、长宽比、翘曲、偏斜、负体积、穿透、厚度/质量/单位、完整接触检查与修复 |
| 完整分析模型 | 限定的平面壳板位移加载模板 | 广泛的接触/冲击/成形/多物理流程、求解及工程验收 |

实体方块“网格”不是 Geometry/Solid/Box 的 CAD 实体。PyDYNA 修改字段也不是对应 GUI 编辑模块的完整替代；是否保留拓扑、引用和物理含义需要单独验证。

## 2. 后处理

| 能力 | 当前状态 | 尚缺 |
|---|---|---|
| d3plot 查询 | 节点/单元/状态等清单，用户 ID 和时间映射 | d3thdt、d3eigv、Post.db、d3dat、d3hdf5、接口力等完整格式适配 |
| 节点结果 | 原生 SCL 分量和部分 Python/读取器路线 | 更多量、移动坐标系、节点/部件筛选、稳定的全部版本覆盖 |
| 单元应力 | 六分量、原生 Mises 对照、主应力及派生参数 | 各类单元/材料/积分点的普遍验证，明确的局部/全局坐标变换 |
| 三轴度与 Lode | 原生张量上计算，明确两种 Lode 定义，静水状态标为未定义 | 与材料模型内部历史量的对应、路径加权、平均规则和专业判据流程 |
| 应变/塑性应变等 | 部分原生字段；读取器按实际数组切片 | 应变度量、剪应变约定、上下层/积分点、温度/能量等逐量验证 |
| 历史变量 | 可选读取器提取原始存储槽位 | 原生任意 HSV 编号/层语义尚未验证；材料/版本命名映射、hisnames/d3labels 集成 |
| ASCII | 原生 GLSTAT/NODOUT/MATSUM 路线验证；其他有限入口 | ELOUT 及更多数据库、主从面/积分点等复杂选择、全选项覆盖 |
| binout | 原生 NODOUT/GLSTAT；读取器嵌套分支/多变量表 | MPP 分片、更多原生分支、接触/截面/刚体/焊点/气囊专用语义 |
| 曲线计算 | 导出、非均匀时间微分/积分、统计 | 滤波、FFT、插值/重采样、同步、算术组合、通用 XYPlot 操作 |
| 工程曲线 | 尚无完整专用流程 | 力—位移、工程/真实应力应变、虚拟引伸计、能量平衡、准静态判定 |
| 极值与热点 | 全域最小/最大值及 ID；代表点全时程 | 存活实体/部件/材料过滤、自动热点追踪、体积/面积加权平均 |
| 云图 | 原生静态 PNG，状态/视角/分量选择 | 稳定色标、层/平均/坐标系、剖切、图例、变形倍率、相机与可见性控制 |
| 动画/多工况 | 未开发完整流程 | 视频编码、帧采样、统一视角色标、多模型同步和报告 |
| 专业后处理 | 大部分未开发 | 截面力/力矩、轨迹/流线、FLD、损伤/裂纹、碎片、VSG、NVH/声学、多求解器 |

现在可取出数据，不代表已经建立相应工程判据。单位目前是显式标注，不是自动单位换算或量纲验证。全域极值也没有默认排除失效实体或刚体。

## 3. 参数化、命令流、Python、SCL、宏

| 方面 | 已有 | 未开发/未完成 |
|---|---|---|
| 参数化建模 | 工具参数化尺寸/网格/ID/材料；结构化 Deck 构造和字段修改 | 可组合工程模板、依赖表达式、参数约束、重生成、DOE/扫描/优化、参数变化后的引用检查 |
| LS-DYNA 参数 | 仅研究了相关格式，当前通用编辑器拒绝复杂参数文件 | `*PARAMETER`、`*PARAMETER_EXPRESSION` 的解析/保留/求值，参数化 include/transform |
| 安装自带模板 | 发现了 4.13 模板和过滤器 | 模板发现/参数表提取/实例化/重读/回归测试；不能当成已接入 |
| cfile 执行 | 为已支持动作生成并运行自有命令文件，保存日志、任务目录和产物 | 通用受控命令配方、语法/语义检查、嵌套命令文件、断点/恢复、交互切换 |
| 命令参考库 | 1,246 行参考记录、1,063 个不同 Command 值 | 逐条参数模式、版本范围、前置状态、结果验收和失败行为；不是千余项已实现功能 |
| `c=` / `runc=` | 已验证 `c=` 与无图形/图形分路 | `runc=` 的逐版本能力验证；不把新版本入口自动套用到旧版 |
| 原生 Python | `runpython` 桥；DataCenter/LsPrePost 部分调用；运行库探测 | 全 API 映射、任意脚本的受控运行、代码诊断、依赖配置、交互/持久会话、结果写回 |
| 外部 Python | MCP/CLI、NumPy、PyDYNA、LASSO、隔离 LS-Reader | 不是“这些库的全部能力已接入”；求解调度、DPF 和复杂版本分支仍缺 |
| SCL | 模型计数、原生字段、部分 binout | 全函数/枚举覆盖、通用编译诊断、复杂几何/模型 API、原生任意历史变量 |
| 命令录制 | 任务生成 cfile；软件会产生执行日志 | 没有录制用户任意 GUI 操作的开始/停止/保存/清理/参数化工具 |
| 宏 | 参考资料和自有批处理配方 | Macro 对话框、宏定义/参数/库管理、`m=`、录制转宏、宏回放与版本迁移 |
| 热键/交互控制 | 未专门包装 | Shift+F-key 命令文件、interactive/resume/skip/endskip、暂停时间及快捷键配置 |
| 自然语言流程 | Skill 能组合当前工具，并识别部分边界 | 完整任务规划、对象持续标识、事务/回滚、预览/确认节点、模型级验收及失败恢复 |

任务日志记录了“本工具执行过什么”，不等于通用宏录制系统。批量提取多个已有结果，也不等于参数化建模或优化。

## 4. 顶部菜单及子菜单

基准主菜单：File、Misc.、View、Geometry、FEM、Application、Explorer、Settings、Help。以下按功能拆开，菜单位置不作为新的独立能力重复计数。

### 4.1 File

| 菜单项/子项 | 当前范围 |
|---|---|
| New / Exit | 任务进程内部使用；没有持久 GUI 会话管理工具 |
| Open → Keyword、Binary Plot | k/key 与 d3plot 子集可用；Binary Plot 里的模态等格式未完整接入 |
| Open → Keyword+D3plot | 未开发联读和同一模型的结果关联流程 |
| Open → Time History、Post.db、Project、Interface Force、Solutions、D3hdf5、D3dat | 未开发 |
| Open → Command File | 自有受控 cfile 可执行；任意已有会话文件的管理/回放未完成 |
| Open → IGES、STEP、Nastran/PCH、其他 CAD | 未开发；部分 CAD 还依赖 translator |
| Import → Keyword/其他网格、占位假人、IGES/STEP、dynain、Universal、STL、OBJ、External Results | 未开发通用合并、ID 冲突处理和格式转换 |
| Recent / Update | 未包装；没有持续增长 d3plot 的刷新管理 |
| Save / Save As → Keyword | 输出新独立 k 文件可用；不是原地覆盖任意源文件 |
| Save Active Keyword | 未开发活动/可见实体范围保存 |
| Save Project/Config/Post.db/Geometry/OBJ/Solution、Keyword+Project | 未开发完整保存链 |
| Run LS-DYNA | 未开发求解启动/监控工具 |
| Print | PNG 子集；打印对话框、各种矢量/栅格格式及版式未覆盖 |
| Movie / Save and Exit | 未开发完整工作流 |

### 4.2 Misc.

| 子功能 | 状态 |
|---|---|
| Model Info | 部分：模型数量/ID 等；完整软件模型信息未包装 |
| Memory Info | 未开发 |
| Message Info | 部分：任务日志；没有完整关键字报错定位/修复系统 |
| Ruler、Keyword Title | 没有专用原生工具；部分关键字字段可通过数据接口修改 |
| Start/Stop Recording Commands、Macro Interface、Manage Command File | 未开发通用录制/宏管理 |
| Execute System Call | 未作为 MCP 工具开放 |
| Keyword File Separate、D3hsp View | 未开发 |
| Moldflow、Moldex3D、ViewFactor、Bottom Dead Center | 未开发专业流程 |

### 4.3 View

当前只有输出图片时的固定视角、居中及原生 fringe 子集。以下大多没有独立受控接口：

- 全屏；背景形式/颜色；几何/单元着色、线框、特征线与边线。
- 全部几何/单元、参考几何、点、曲线、曲面和网格显示开关。
- 工具栏显隐、文字/图标方式、字体大小。
- 局部单元轴、梁棱柱与快速梁显示、平滑着色/平滑色带。
- 失效节点/单元显示、仅失效单元、忽略失效标记。
- 屏幕结果、消息记录开关、中间节点、仅 A 轴方向、固定原始坐标不更新。

“截图里出现了网格/色带”不能算已实现这些显示控制。

### 4.4 Geometry 及其全部主要功能族

| 展开分组 | 功能族 | 当前状态 |
|---|---|---|
| Reference Geometry | 点、轴、面、坐标系、参考几何编辑 | 未开发原生几何流程 |
| Curve | 点、直线、圆/圆弧、椭圆/椭圆弧、B-spline、螺旋、组合、断开/合并、桥接、平滑、中间线、变形、圆角、草图、转换、抛物线/双曲线、函数、多边形、拟合 | 未开发 |
| Surface | 平面、圆柱/圆锥/球/环/椭球面、填充、拉伸/旋转/扫掠/放样、N 边面、补面、桥接/组合、点/网格拟合、中面、变形、基本面拟合、断面 | 未开发 |
| Solid | CAD 方块、圆柱、锥、球、环、拉伸/旋转/扫掠/放样、圆角、倒角、拔模、加厚、楔、布尔、棱柱、组合 | 未开发；不能用网格工具冒充 |
| Geometry Tools | 删除/隐藏、延伸、求交、偏置、投影、换面/搜索、缝合、裁剪、变换、反向、复制、几何管理、修复、拓扑简化、ID/测量、实体分解、文字对象、沿路径阵列 | 未开发 |

### 4.5 FEM → Element and Mesh

| 展开功能 | 当前状态 |
|---|---|
| Shape Mesher → Box Solid | 已验证子集：规则六面体方块 |
| Shape Mesher → 4N Shell | 部分：仅 XY 矩形板，不是任意四角曲面 |
| Shape Mesher → Box Shell、Sphere Solid/Shell、Cylinder Solid/Shell、Circle Shell | 未开发 |
| Auto Mesher、Solid Mesher | 未开发 |
| Block Mesher → 创建、参数、隐藏/删除、读写、移点、分布、旋转、投影、信息 | 未开发 |
| N-Line Mesher → 多边界线壳、沿线扫掠 | 未开发 |
| 2D/Tetrahedral Mesher、表面重划分 | 未开发 |
| Blank Mesher → 四点/矩形/曲线/细化 | 未开发专用流程 |
| Bulk Fluid | 未开发 |
| Element Generation → Beam | 沿边/曲线、节点拖动/旋转、壳对角线等未开发 |
| Element Generation → Shell | 边拖动/旋转/延伸、面集、补孔、黏聚壳未开发 |
| Element Generation → Solid/Shell Drag | 已验证限定子集：单个平面壳沿 +Z |
| Element Generation → 其他 Solid | 实体面拖动/偏置/旋转、壳偏置/旋转/厚度、两壳集、壳扫掠、四面体/六面体转换、黏聚实体未开发 |
| Node Edit → Create/Modify | 部分：PyDYNA 数据创建/修改和原生平移；不含完整交互编辑 |
| Node Edit → Replace/Delete/Align | 未开发 |
| Element Edit → Create/Modify | 部分：关键字表格层数据操作；不含完整拓扑编辑 |
| Element Edit → Check/Delete/Split/Merge/Direction/Composite | 未开发 |
| 2D/3D NURBS、Mass Trim、Spot Welding、SPH、Discrete Sphere | 未开发 |
| Multi-solver Mesh、Result Mapping、Point Cloud to Mesh | 未开发 |

### 4.6 FEM → Model and Part

| 展开功能 | 当前状态 |
|---|---|
| Assembly/SelPart、GPart、装配比较 | 仅部分部件查询；装配组织和选择管理未开发 |
| Keyword Manager → Search/Edit | 部分：PyDYNA 类/字段检索、唯一匹配修改；并非完整原生 Keyword Manager |
| Create Entity → 材料、截面、节点、单元、集合、曲线、边界/载荷/输出等 | 通用数据层及限定壳板流程部分实现；各专用建模对话框没有逐项完成 |
| Create Entity → 气囊、连接/约束、接触、阻尼、EOS、初始条件等 | 类可检索/部分字段可表达，不算工程工作流已验证 |
| Display Entity/Preview | 未开发完整实体显示和预览控制 |
| RefCheck/Attach | 部分库级引用检查；原生 Reference/Attach 未接入 |
| Renumber | 未开发全引用重编号 |
| Section Plane → 构造/选项/压溃/测量/交线/力/保存 | 未开发 |
| Subsystem、Group、Model Selection/Compare | 未开发 |
| Views | 图片固定视角子集；视图保存/恢复/相机管理未开发 |
| Part Color/Transparency、Appearance、Annotation、Split Window、Explode、Lighting | 未开发 |
| Part Data | 转移部件和部分关键字数据修改；完整属性/关联编辑未开发 |
| Reflect Model、Trace Light、Connector | 未开发 |

### 4.7 FEM → Element Tools

| 展开功能 | 当前状态 |
|---|---|
| Identify / Find | 部分：通过 ID 查询节点/单元连接；图形定位、标签和结果识别未包装 |
| Blank | 未开发实体/部件隐藏与恢复 |
| Move/Copy | 部分：单元转部件；复制、部件复制和复制引用未做 |
| Offset | 未开发 |
| Transform | 部分：节点平移；旋转/缩放/镜像/复制未做 |
| Normals → Shell/Tshell/Reverse/Align/Segment | 未开发 |
| Detach、Duplicate Nodes | 未开发 |
| Measure | 部分原生命令值；通用距离/角度/面积/质量/重心/惯量语义未完成 |
| Morph → 网格笼、内部节点、约束、展开、曲线驱动等 | 未开发 |
| Smooth、Part Trim、Part Travel、EdgeFace、Regionalize | 未开发 |

### 4.8 FEM → Post

| 展开功能 | 当前状态 |
|---|---|
| Fringe Component | 已有部分原生字段与云图；更多分量、坐标、层和平均未完整接入 |
| Fringe Range | 未开发色标范围、离散等级、极值标签与跨模型统一色标 |
| History | 节点/部分单元时程子集；全类型、层/局部系、筛选和专用指标仍缺 |
| XYPlot | 原生导出和外部简单数学处理；交互曲线管理/完整运算未开发 |
| ASCII | GLSTAT/NODOUT/MATSUM 等子集；不是所有数据库和选项 |
| BinOut | NODOUT/GLSTAT 原生子集；其他分支、MPP、接触主从面/积分点选择不完整 |
| Follow → 点/面跟随 | 未开发 |
| Trace → 节点/点/流线/部件/重心/曲线/流动曲线 | 未开发 |
| State → Select | 可按状态提取/出图；没有持久 GUI 状态管理 |
| State → Inactive/Delete/MultiState | 未开发 |
| Particle → 基本信息/速度分布/Fringe/Vector | 未开发 |
| Chain Model、FLD、CGAT、Bottom Dead Center、Cracks | 未开发 |
| Output | k/CSV/PNG 等有限产物；dynain/映射/附加信息等完整输出未开发 |
| General/Post Settings | 位移倍率、反射、厚度比例、坐标、裂宽和专业常数等未开发 |
| Vector | 数值向量提取不等于矢量图；通用矢量可视化未开发 |

### 4.9 Application / Explorer / Settings / Help

| 入口与子功能 | 状态 |
|---|---|
| Occupant Safety → 气囊折叠、DynFold、假人定位、座椅变形、滑车、安全带拟合 | 未开发 |
| Metal Forming → 工具/坯料网格、检查/偏置、多工序、多翻边、成形后处理 | 未开发完整流程 |
| Model Checking → Keyword Check、Contact Check 等 | 未开发原生模块；部分库级引用检查不能代替 |
| Tools → Media、Curve Generation、J integral、Welding | 未开发专业模块；普通 DefineCurve 创建不等于材料曲线生成 |
| NVH → 模态、FRF、稳态、随机振动、响应谱、BEM/FEM 声学、面板贡献 | 未开发 |
| 3D Graph | 未开发 |
| Run SCL | 部分：工具内部脚本；不是完整交互脚本管理器 |
| Battery Packaging → Cell、Randle Circuit、Tabs、等势连接 | 未开发 |
| Wear、Fragment、Virtual Strain Gauge、Plastics | 未开发 |
| Explorer → Solution、Subset、Post、MS Post、Pre | 未开发树/属性驱动的交互工作流 |
| Solution 模块 → Structure、Drop Test、DUALCESE、ISPG、NVH、SPG-Drilling、S-ALE 等 | 未开发模块级模板流程；个别关键字可表达不算已完成 |
| Settings → 当前子系统/工作目录 | 工作目录由任务内部控制；GUI 子系统/全局设置管理未做 |
| Settings → General/Post/Configuration | 没有全面配置编辑、快照、恢复和跨版本迁移 |
| Settings → Toolbar Manager、Favor、透明工具栏 | 未开发配置管理 |
| Help → Documentation/Tutorial/Old-to-New/Release Notes/About | 已有部分资料检索/环境探测；不等于软件内完整 Help 自动化 |

## 5. 右侧工具栏及展开分组

这些入口大部分是顶层菜单的另一种展示，不重复计算为另一份功能。

| 工具栏分组 | 展开内容与缺口 |
|---|---|
| RefGeo | 参考点/轴/面/坐标系及编辑：未开发 |
| Curve / Surf / Solid | 上述 Geometry 三组：全部缺少成熟原生流程 |
| GeoTol | 几何删除/隐藏、延伸、求交、偏置、投影、缝合、裁剪、变换、修复等：未开发 |
| Mesh | Shape/Auto/Solid/Block/N-Line/Tetra/Blank/BulkF/ElGen/NodeEdit/ElemEdit/NURBS 等：只有少数网格子集已验证 |
| Model | SelPart/Keyword/Create/PartData/Display/RefCheck/Renumber/Section/Subsystem/Group/View/Color/Appear/Annotation/Split/Explode/Light 等：少量查询和数据编辑，其余缺口明显 |
| EleTol | Ident/Find/Blank/MoveCopy/Offset/Transform/Normal/Detach/DupNode/Measure/Morph/Smooth/Trim/Travel 等：平移、转部件和查询子集 |
| Post | FriComp/Range/History/XYPlot/ASCII/Binout/Follow/Trace/State/Particle/Chain/Output/Vector/FLD 等：数值提取子集，控制和专业流程大量未做 |
| MS Post / MS | ICFD、MS-ASCII、LSO 等：未开发 |
| Metal Forming Pre | 坯料/工具网格、变换/偏置、法向、重复节点、成形设置/废料裁剪等：未开发领域闭环 |
| Metal Forming Post | FLD、滑移痕迹、网格分析、边缘流入、剖面、曲线和成形输出等：未开发领域闭环 |
| MdChk | 本机可见的 Model Checking 入口：尚未包装 |
| Favor1/Favor2/自定义或透明工具栏 | 当前软件配置决定内容；没有工具栏配置/功能发现/迁移工具 |

菜单按钮可见、可点击，和 MCP 可以稳定完成它对应的工程操作，是两个不同层次。

## 6. 底部工具栏及折叠选项

| 功能/展开选项 | v0.2.0 |
|---|---|
| Display Option → 标题、图例、极值、时间、坐标三轴、背景/网格颜色、性能统计 | 未开发逐项设置 |
| Hidden/Shade/View/Wireframe Element | 未开发可控切换 |
| Feature Line / Edge Line / Grid Point | 未开发；特征角等参数也未开放 |
| Mesh On/Off | 未开发独立接口 |
| Shrink | 未开发收缩倍率与模式 |
| Post Fringe Mode → 云图/等值线/等值面 | 只做云图子集；等值线/等值面及切换未开发 |
| Unreferenced Nodes | 未开发显隐与清理流程 |
| Geometry shaded with/without edges / wireframe | 未开发 |
| Shift/Ctrl 模拟操作 | 未开发 |
| Auto Center | 出图过程内部使用；没有持久会话视图接口 |
| Zoom In / Zoom Out | 未开发视口缩放管理 |
| Pick Rotation Center | 未开发 |
| View Coordinate | 未开发观察坐标系管理 |
| View Direction → 上/下/前/后/左/右 | 固定方向出图可用；实时视口操作/保存恢复未开发 |
| Rotation Angle / Rotate X-Y-Z | 未开发 |
| Perspective / Parallel | 未开发 |
| Clear All / Activate All | 在部分命令配方内部有清选动作；没有通用选择/激活状态工具 |
| Background | 未开发可控配色 |
| Animation Toolbar → 播放/停止/正反向/循环/首末帧/步长 | 未开发完整动画控制与导出 |
| Assembly and Select Part / Restore Part | 未开发通用显隐、恢复和选择管理 |
| Plot Manage | 未开发图窗/曲线/布局管理 |
| Window Relocate | 未开发 |
| 本机显示的 Home 及自定义附加图标 | 只确认界面可见；具体配置和动作未作为已开发能力登记 |

底部命令输入框和最后命令显示区也没有作为持久会话接口接入。现有命令执行发生在工具创建的任务进程中。

## 7. 本地安装资源检查

| 版本 | 本轮只读发现 | 对开发的实际意义 |
|---|---|---|
| 4.8 | 安装资源、材料 XML、版本说明及成形相关目录 | 可补旧版命令/界面差异；未据此认定所有功能兼容 |
| 4.10 | Document/Tutor CHM；成形参数压缩文件 | CHM 已定位，但本轮系统解包未产出可用目录，未声称已完整解读；成形参数包已读取 |
| 4.13 | 材料 XML、成形参数包、41 个关键字过滤器、7 个模板包 | 模板包括显式设置、三维冲击、轴对称材料试验和 SALE；尚未接入模板参数化引擎 |

4.13 主程序可读 PE 资源类型包括图标、版本和 manifest，本次没有发现可直接解析的 RT_MENU 资源。因此不能把二进制字符串/资源数量当作完整菜单定义或公开 API。

模板采用关键字参数和表达式，并包含模型配置依赖；当前编辑器恰好尚未支持这类参数文件的完整重写，这是明确缺口。安装资源与手册原文留在本地，不复制到公开仓库。

## 8. 推荐开发顺序

1. **常用前处理闭环**：选择器、球/圆柱等形状网格、节点/单元增删改、旋转/复制/镜像、重复节点/法向/质量检查、集合、部件/材料/截面关联、include 树保存与重开。
2. **后处理语义闭环**：原生 HSV、ELOUT/RCFORC/MPP、失效/部件过滤、层/坐标/平均、力—位移/应力—应变、截面量、统一色标和动画。
3. **参数化与录制闭环**：录制捕获、命令清理、ID/路径/变量参数化、模板参数表、参数依赖、重生成、回放差异验证及失败恢复。
4. **Python/SCL API 适配**：建立逐函数/逐版本契约与真实测试，不仅保留执行入口；逐步覆盖复杂数据查询、编辑与结果写回。
5. **领域应用**：先选用户常用方向，再建设成形、碰撞、碎片/VSG、NVH、多求解器等完整案例，避免只有菜单入口没有工程验收。

每一项的完成依据应是：可追溯来源 → 明确参数/状态 → 可执行适配 → 边界测试 → 对应版本实机验证 → 可检查产物 → Skill 工作流。没有明确、稳定的功能分母前，不给出“覆盖百分比”。

## 依据

- [官方 2026R1 指南](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lsdyna_prepost.html)：第3–4章菜单/工具栏，第5–9章功能，第10章命令。
- [File](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_pd-file.html)、[Misc](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_pd-misc.html)、[View](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_pd-view.html)。
- [Geometry](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_pd-geometry.html)、[FEM](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_pd-fem.html)、[Application](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_pd-application.html)、[Explorer](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_pd_explorer.html)、[Settings](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_pd-settings.html)。
- [右侧工具栏](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_toolbar_right.html)、[底部工具栏](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_toolbar_bottom.html)。
- 本仓库 v0.2.0 的 `server.py`、`service.py`、`embedded.py`、`pre_tools.py`、`post_tools.py`、`keyword_tools.py`、相关适配器与测试；详见[实现验证](VERIFICATION.md)。
- 本机空白界面核查与安装资源清单为私有审计证据，不包含公开的工程算例数据。
