# 后处理界面与代码差距：实机审计增补

2026-10-05；代码对照基线 `e24257c`。这是正在进行的全界面审计的一部分，**不是后处理完整清单，也不是新增功能验收**。36 项首版门槛、工具数和测试数均不能作为 LS-PrePost 常用功能覆盖率。

后续代码增量：现有 `export_gui_curve_plot` 已扩展原生多曲线叠图、明确图例、独立X网格/不同点数、逐曲线数值导出与换源回放；4.13.4三曲线合成验收及PNG目视核对通过，见[NATIVE_MEDIA](NATIVE_MEDIA.md#native-multi-curve-overlays-2026-10-05)。下表是较早截图时点，不应继续把基本叠图列为完全未实现；任意曲线运算、样式、分页/多窗口管理和全部数据库仍待补。

Binout后续增量：`extract_native_binout_curve` 已增加MATSUM映射与显式当前GUI执行路径；11类量的101时刻原生/独立读取器核对、缺量/缺ID拒绝、双曲线输出及换ID回放通过。下表“原生工具拒绝MATSUM”属于旧基线；部件求和、完整分支目录和其它数据库仍未由本批覆盖。详见[后处理范围](POSTPROCESSING.md)。

## 证据与边界

- Windows LS-PrePost 2026 R1 **4.13.4 / 17Dec2025**，可见主窗口最大化。曲线窗口曾最大化；打开原生 Print 对话框时窗口恢复大小，单独记录，不冒称全程最大化。
- 本地审计截图编号127–178：History、两条自建四点曲线的 XYPlot 面板，以及公开 Binout 的真实分支。过渡画面、不相干前景截图不算成功证据。原图与运行日志仅留在本地审计目录。
- Binout 来源：[saudbinayed/binout](https://github.com/saudbinayed/binout/tree/345d6997514059baf0c4e1f0608dafef9c43ee7d/LS-DYNA-sample)，固定提交、MIT，81,205,008 字节；本地清单记录 Git blob 与 SHA-256。未执行上游脚本。其实际分支为 `elout`、`glstat`、`matsum`、`ncforc`、`nodout`，不能照抄 README 将 NCFORC 写为 RCFORC。
- 背景 d3plot 是另一份公开 LASSO 示例；此次 Binout 审计不使用背景模型选点或高亮来证明 ID 对齐。后续实体联动验收必须加载匹配模型并核对文件身份。
- 仅打开面板、看到字段不证明变量有有效数值，也不证明运算或导出正确。此轮未新增任何发布门槛通过项。

## 差距对照

| 操作族 | 本次原生证据 | 现有实现边界 | 后续闭环需要补什么 |
|---|---|---|---|
| History | 127–146：Global/Nodal/Element/IntPt/Part/R-Nodal/Scalar/VolFail；实体类型、局部轴、层与取值选项 | 有节点/单元场和部分历史提取；不能由六应力工具推定所有 History 模式覆盖 | 按数据库能力发现实体/变量；层、积分点、坐标系、聚合语义明确；相对、路径、部件求和各自验收。Scalar 本样例缺输入，条件未满足 |
| 原生 Binout GLSTAT | 168–169：包含删除能量、能量比、滑移、阻尼、速度、步长等字段 | `native_results.native_binout` 仅5项能量：动能、内能、总能、外功、沙漏能 | 扩展明确量名及其单位，包含/排除删除能量的口径不得混用；与原生导出逐点对照 |
| 原生 Binout NODOUT | 174–175：平移、转动及合成量，HIC/CSI/BrIC入口 | 同一函数仅坐标/位移/速度/加速度的XYZ，共12项，单实体 | 转动与合成量、多节点输出；物理单位和时间轴检查。损伤评估类指标独立、非默认处理 |
| 原生 Binout MATSUM | 170：两个部件、Sum Mats、能量/动量/刚体运动等 | 原生 Binout工具拒绝该分支；外部 LASSO 有明确ID的数组读取 | 原生多部件读取/求和，区分可加量与派生比值；不可把逐部件比值直接求和 |
| 原生 Binout NCFORC | 171–173：master_1/slave_1、节点ID、压力、坐标、三向力和合力 | 原生 Binout工具拒绝；`extract_binout_table` 可处理满足形状约束的嵌套数组，但不等于原生已验收 | 接触侧、接口号、节点ID明确；区分矢量求和后的模与各节点力模之和；原生曲线及数值往返 |
| 原生 Binout ELOUT/shell | 176–178：单元ID、IP-1及Stress/Strain/Muscle/History/Force-Moment类别入口 | 原生 Binout工具拒绝；通用 LASSO table要求一维固定ID及二维时间/实体数组，不支持任意IP轴 | 逐状态ID、积分点、变量族与缺失记录合同。该样例读取器 `ids` 是时间×实体，不能reshape后当固定ID；此样例一个IP不证明多IP通过 |
| 多曲线与运算 | 147–159：两曲线载入；Oper枚举37项，包括积分/微分、组合、FFT/IFFT、表达式、拟合、插值等 | `export_gui_curve_plot` 是CSV两列→单曲线PNG；`process_curve` 是外部数值微分/积分/摘要 | 稳定曲线句柄、原生运算、跨窗叠图、时间轴对齐、往返数字校验。数学旁路与原生执行分开记录 |
| 曲线滤波 | 156–157：none/sae/bw/fir100/cos、时间单位、频率、点平均、Force zero start | 没有据此完成整套原生滤波封装 | 明确方法/采样间隔/频率/端点处理，保留原始曲线，用户显式选择；不能默认滤波或强制清零 |
| 曲线数据保存 | 160–161：Curve/Keep/XY pairs、单/多X轴CSV、XML、WAV；区间/插值/裁剪 | 已有CSV产物及单曲线往返；不是面板完整覆盖 | 首先多曲线CSV的时间列语义、裁剪和导出后校验；其他格式逐项按需求验收 |
| 曲线出图 | 163–164：13种扩展名、RGB/HD、纸张/分辨率、背景/Gamma等 | `gui_media.export_gui_curve_plot` 当前仅单曲线PNG、短ASCII标签 | 多曲线图例/轴尺度、明确版式参数、常用矢量格式；格式列出来不代表均可成功导出 |
| Animate折叠区 | 165：Pick Part、Dist. to BDC、Draw Depth | 已有两条动画导出路线；不包含此测量流程 | BDC/拉深测量独立记录为条件化操作；普通动画仍需状态范围、步长、相机/色标一致性验收 |

## 开发依赖候选，尚未替代整体路线

先继续完成其他Post、Model/Entity、选择与公共视图面板审计，再冻结下一批。已有证据支持的后处理依赖顺序是：

1. **数据库与曲线身份合同**：来源文件、分支、实体类型/用户ID、逐状态ID、IP、坐标系、单位与原始/派生标识。
2. **原生多数据库历程闭环**：MATSUM、NCFORC、ELOUT等，不只增加分支字符串；每项须选实体→抽取→导出→读回比较。
3. **多曲线对象与处理闭环**：叠图、组合、对齐和常用运算，保留来源与原始数据，再接参数化复用。
4. **出图与模板**：从单曲线PNG扩到多曲线及常用矢量输出；保留模型标题和原生结果名称，云图默认MinMax平均不变。

前处理Entity/选择、网格、自动化仍在总路线内，不因本次后处理取证而降为次要目标。

## 后续手册核对入口

以下链接来自已记录官方目录，是继续逐项核对的入口；本文件不声称对应整章已精读或全部实现：

- [FEM Post：History、XYPlot、ASCII、BinOut等](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug-fem-post.html)
- [XY PlotWindow](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_gentools_xyplot_window.html)
- [New XYPlot Frame](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/lsdyna_prepost/lspp_ug_gentools_newxyplot.html)

代码定位：`src/ls_prepost_mcp/native_results.py:223`、`post_tools.py:62/316`、`gui_media.py:45`、`service.py:483`。记录的是实际接口边界，非由工具名称推测覆盖。

## 新公开案例揭示的发布阻断项

2026-10-05，连续打开普通、梁/实体、复材/SPH三套官方d3plot后，尝试在同一会话打开复材案例 `input.k`：

- 原生日志在 `open keyword` 后报告 `Invalid entity ID! ** Prog Error`，窗口标题仍为之前的d3plot。
- `open_in_gui_session` 却返回 `succeeded`，统计仍为2957节点、3005单元、3状态；后续视图/节点分页同样不足以证明新k文件已载入。
- 本地初始烟雾报告的 `passed_inventory` 已被独立复核撤销为 `failed_stale_model_not_accepted`。保留原始请求/响应/日志，并将该测试会话标为 `uncertain`，禁止继续信任其模型归属。

这不证明k文件本身无效，也未证明是哪一种卡片导致原生错误。需要分别复现新会话读取、结果→关键字切换、复材/SPH数据条件。首先修复**读取失败不能回报旧模型成功**的合同，再恢复该项验收。

`B0-03`“执行结果、质量门槛及失败停止”据此从passed退回partial；已有网格质量门槛证据保留。首版台账由26/36变为25/36，分母不变。这仍不是软件功能覆盖率。

独立LASSO2.0.4读取鸟撞结果还出现 `n_shell_vars != n_shell_vars_computed: 260 != 314` 和壳塑性应变张量reshape错误。节点/状态数匹配仅支持库存核对，**不支持复材场数组正确性结论**。后续旁路读取必须暴露读取器警告，不能以成功构造读取对象宣称所有变量可用。

首次测试运行目录过深还导致请求JSON临时文件无法创建；缩短同一任务内运行目录后恢复。未改变Windows长路径策略，保留为可诊断性与路径预算缺口。

后续对照：同一鸟撞 `input.k` 在**新建的纯关键字会话**中正常读取2957节点、3005单元、1状态；延迟3秒重新读取一致，日志有 `Finished reading model`。因此不能将前述失败归罪于输入文件本身；结果→关键字切换和多模型归属须优先隔离。这一对照未修复误报问题，也不恢复B0-03通过状态。

## Follow / Trace / Output / Vector 增补（截图180–193）

上述误报已增加主机侧防护并通过新一轮4.13.4可见GUI正反例：新关键字、关键字→结果正常；结果→关键字报错被拒绝，来源和代际不推进，原始文件不变。即时/延迟恢复逻辑同步修复，548项测试通过。完整模型列表及replace/attach/activate语义仍未闭环，**B0-03不因此恢复passed**；详见[会话校验边界](GUI_WORKFLOWS.md#会话配置与可见性)。

| 原生操作 | 实际观察 | 明确缺口或验证要求 |
|---|---|---|
| Follow Point / Plane | 点跟随按XYZ；平面由三节点及Part/全模定义；有模型选择列表 | `set_gui_display` 的固定相机不等于动态参考系跟随；需模型身份、引用节点退化检查、随状态更新与复位 |
| Trace | Node、Streamline、Point、Part、CG、Curve、Flow Curve入口；已展开除Point外各主要模式 | 节点历程CSV不能代表轨迹对象、曲线导出或BPM卡片生成已实现；选区消费者随模式切换为节点/Part/单元/几何边 |
| Streamline | 已展开Points/Plane种子位置、法向、数量和间距 | Display/ActiveBox子项尚待拍；未有对应流场数据验收，不把面板可打开算流线成功 |
| Part Trace | 状态列表显示State0..21，而该数据库共22状态 | 公共状态仍1-based；不能直接抄界面序号到API，也不能只凭这一列表推断所有原生命令的编号规则 |
| Output | Keyword/Dynain等13种格式；节点坐标/位移/速度、单元/节点结果、壳塑性应变/厚度、质心体积、ID与范围控制 | `export_keyword` 不等价于导出指定变形状态、历史量或全过程传递；需状态、作用域、量定义与目标格式分别验收 |
| Vector | 壳法向、位移/速度/加速度、主应力/应变及面内主量、热流、结构强度、历史方向余弦、穿透等12个选项 | 数值向量提取不等价于原生矢量图；箭头尺度、范围、作用域、主方向与IP尚无完整typed闭环 |
| ASCII | 面板类型列表有60项；顶层File菜单较短列表不是全集 | 当前原生ASCII工具仅6数据库；需要实数据逐类验证，而非把任意数字文本读取器当求解器数据库解析器 |

原生界面已显示存在不代表当前模型写出了相应变量。手册已核对Post中的Follow/Trace说明，坐标系切换和HistVar标签的模型依赖也需纳入验收。所有修改模型、应用场数据和实际写出仍须单独验证。
