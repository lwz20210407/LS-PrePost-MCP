# 后处理：执行范围与结果含义

原生 SCL 与读取器提取现共享 [结果选择/取值位置合同](RESULT_CONTRACTS.md)，随任务和结果保留 `field_spec`。这区分原生层、默认选择器与读取器存储轴，不会自动建立跨后端积分点等价或推断量纲。

## 原生工作流

优先用 `extract_native_fields`、`extract_native_stress`、`extract_native_ascii_curve` 和 `extract_native_binout_curve`。这些工具实际启动 LS-PrePost，使用 SCL/DataCenter、SCLBinout 或 ASCII/XYPlot。输入先复制到独立任务目录；软件打开副本。

| 工具 | 当前范围 | 选择与限制 |
|---|---|---|
| `extract_native_fields` | 节点位移、速度、加速度；单元应力、应变、等效塑性应变、主应力等白名单字段 | 显式用户 ID、1-based 状态；层/积分点按实体合同验证。原生实体积分点2–8已因取值错误而阻断；壳层和读取器存储轴不可混称。字段是否保存取决于数据库 |
| `extract_native_stress` | 六分量、原生 Mises，以及主应力、三轴度、Lode 派生量 | 原生 SCL 取值；Python 计算张量不变量，并与原生 Mises 对照；不做空间平均 |
| `extract_native_ascii_curve` | GLSTAT、NODOUT、MATSUM、SPCFORC、SECFORC、RBDOUT 的单曲线接口 | 使用原生对话框分量编号；实机验证范围见能力记录；RCFORC 主从面选择尚未开放 |
| `extract_native_binout_curve` | NODOUT 位移/速度/加速度/坐标分量；GLSTAT 能量 | 当前仅完整单文件；不支持 MPP 分片集 |
| `native_postprocess_case` | 多字段全时程、极值与实体 ID、代表点历程、ASCII 曲线、应力云图 | 当前验收配置 4.13；图像单独走已验证 Python 桥；每类实体取首/中/末三个记录，极值扫描全域；不是逐单元完整场导出 |

批处理驱动 `tools/run_native_acceptance.py` 接受显式私有 inventory JSON、输出目录、安装路径和单位标签。逐组运行，清除本轮创建的输入副本，保留结果及失败日志。不要把私有 inventory、原始文件、CSV、截图和报告上传到公开仓库。

`succeeded` 表示约定的导出/一致性检查通过。它不表示全部求解量已保存、物理模型正确或所有 LS-PrePost 功能都受支持。支持该参数的字段/应力工具中，兼容默认 `validity_policy=raw` 保留原始实体，显式 `alive` 才使用已验证的标准壳/实体物理删除过滤；参见[逐状态有效性](RESULT_VALIDITY.md)。不能把一条工具的过滤能力外推给所有后处理入口。

## 张量与 Lode 约定

输入顺序为 `xx, yy, zz, xy, yz, xz`，拉应力为正，剪应力是张量分量。令 `s = σ − trace(σ)I/3`：

- `mean_stress = trace(σ)/3`，`pressure = −mean_stress`。
- `J2 = s:s/2`，`J3 = det(s)`，`von_mises = sqrt(3 J2)`。
- `triaxiality = mean_stress/von_mises`；单轴拉伸为 `+1/3`。
- `xi = (3√3/2) J3/J2^(3/2)`，`theta = acos(clamp(xi,−1,1))/3`。
- `lode_angle_parameter = 1−6 theta/π`；单轴拉伸 `+1`，压缩 `−1`。
- `lode_parameter = (2σ2−σ1−σ3)/(σ1−σ3)`，其中 `σ1≥σ2≥σ3`；单轴拉伸 `−1`，压缩 `+1`。

两个参数的定义不同，不能混称或自动套用某个材料模型的断裂曲面。相对偏应力低于阈值时，三轴度及 Lode 量输出 `null`；CSV 用空字段并保留 `deviatoric_defined` 标志。静水应力状态不能伪装成纯剪切。应先选择积分点/壳层，再计算不变量；“先平均张量再求不变量”与“先求不变量再平均”不同。

2026-10-04界面审计注意：4.13.4 Fringe Component → Misc 列出的 `lode parameter` 带上述主应力比值的负号，`lode parameter-alt` 列为 `(27/2)*(J3/vm^3)`。因此本工具明确定义的 `lode_parameter` 不能直接宣称等于界面同名项，`lode_angle_parameter` 也不能冒充 native alt。此次截图只确认界面公式文字，尚未新增这两项的原生数值对照验收；保持现有公开数学定义，不静默改符号。

返回值保留原始应力分量、主应力、最大剪应力、J2/J3、压力、三轴度、Lode 角（弧度/度）和两种明确命名的参数。`compute_stress_invariants` 也可直接处理给定张量，便于合成解析解测试。

## 可选读取器和曲线计算

- `inspect_result_fields` 查询实际文件在指定状态的字段、维度和 ID 样本。`extract_d3plot_field` 支持节点、实体/壳/厚壳/梁、部件及全局标量切片；剩余每个轴必须给出 1-based 索引。支持已保存的历史变量、应变、温度、能量、梁力/矩等，返回原始存储含义。
- `extract_d3plot_stress` 提供 LASSO 张量导出；刚体壳没有应力记录时，依据部件材料类型映射非刚体壳 ID，禁止直接按完整单元数组位置取值。
- 历史变量槽位不是统一材料含义。结合材料型号、求解版本、输出控制及 `hisnames.xml/d3labels.xml` 解释。未输出的数据无法事后补算；原生任意历史变量路由仍在开发。
- `inspect_binout_variable` 与 `extract_binout_table` 支持嵌套分支、多变量、显式实体 ID；维度不匹配时拒绝猜测。
- `extract_ascii_curve` 只解析显式数值列及 Fortran D 指数，不能代替原生 GLSTAT/NODOUT 分块文件读取。
- `process_curve` 对非均匀时间序列微分、梯形积分和统计；要求时间严格递增，不混合多个实体，不自动滤波，显式返回导数/积分单位关系。

## 后续优先建设

1. 原生历史变量编号与层选择、ELOUT/RCFORC 的明确实体/主从面选择，以及 MPP binout 分片。
2. 已有标准壳/实体MDLOPT2过滤之外的有效性类型、材料条件，局部坐标系和壳层统一，热点自动追踪。
3. 已有力—位移、工程曲线、单位换算和基础能量筛查之外的区域/随动虚拟引伸计与完整预算；必须由用户提供截面积、标距、单位和测量位置。
4. 加权平均、截面合力/力矩、接触力、路径和截面结果，避免把简单节点平均当体积/面积加权。
5. 已有单曲线PNG、固定色标云图与两种动画路线之外的多曲线/多工况比较及通用报告；参见[NATIVE_MEDIA](NATIVE_MEDIA.md)与[FIELD_MOVIES](FIELD_MOVIES.md)，不能将媒体导出整体列作未实现。

接口依据：[官方 SCL/API 手册](https://ftp.lstc.com/anonymous/outgoing/lsprepost/SCLexamples/lsppscripting_05Jun2024.pdf)、[官方历史变量说明](https://lsdyna.ansys.com/history-variables-for-certain-material-models/)、[LASSO 数组说明](https://open-lasso-python.github.io/lasso-python/dyna/ArrayType/)。具体使用仍以安装版本的接口和实机验证为准。
