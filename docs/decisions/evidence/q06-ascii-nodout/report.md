# Q06：ASCII NODOUT 具名平动曲线

状态为 **partial / L1**。实际最终读测提交为 `cdc1957f78d7736042be025bb4b08cb9ae483552`，运行前后工作树干净，diff 为空。
产品、测试与独立 verifier 的 Git blob、公共源 SHA 和报告 SHA 见 [evidence.json](evidence.json)。没有执行 NODOUT 原生比较，不宣称完成 Q06 全库验收。

| 具名分量 | 原始列标签 | 口径 |
|---|---|---|
| x_displacement / y_displacement / z_displacement | x-disp / y-disp / z-disp | 直接读取，不用坐标相减 |
| x_velocity / y_velocity / z_velocity | x-vel / y-vel / z-vel | 直接读取，不从位移差分 |
| x_acceleration / y_acceleration / z_acceleration | x-accl / y-accl / z-accl | 直接读取，不从速度差分 |

ID 是文件写出的正整数节点号，不是存储位置、legend 顺序或另一个模型的 ID。首个平动表的列位置与调用者筛选顺序保留，后续节点重排按原 ID 对齐。
单位与时间单位由调用者声明，不推断或换算；坐标系为 as written，不做变换。返回与警告明确 **raw/unmasked、alive mask unavailable、deletion validity unknown**，零值不证明节点仍活跃，不从相邻 d3plot 猜测删除状态。

## 支持的记录与拒绝边界

首轮布局为 I10 节点槽位加十二个 E12 平动字段，或 I10 加九个 E12 转动字段。固定边界能正确读取无空格黏连的负数；不以空白 split 补列。
time-step 标签允许观察到的字符间空白，但 step 与 time 独立捕获完整 token；`0 .1`、`1 2`、`1E -3` 不会通过去空白改写成数值。
支持平动单表，或每一平动帧配一个相同步号/时间及节点集合的完整转动表。两种表共享时间是合法物理分组，不当成重复帧；转动字段只校验完整性，不输出为新量。

前言中的普通文本、长标题、纯数字标题和 balanced legend 正确保留语境。完整列头与潜在 I10+9/12×E12 记录形态属于保留语法：无 time 上下文时一律拒绝，不能因为 ID 是负数/空/星号、数值为 NaN/Inf/坏 token 而降成 prose 后跳过。
不保证把与完整保留记录形态相同的内容当作标题。帧内截断、空表、错列头、额外列、重复节点/同类帧、倒序时间、变化节点集、缺转动配对和非有限/下溢均明确失败。

读取复用共享 bounded_lines，预检/哈希及已打开描述符读取阶段均有 256 MiB 字节预算；单行最多16384字符，总记录行最多一百万，转动行也计数。
SHA 前后绑定并记录 job.inputs；增长文件在解析额外内容前拒绝，失败不返回已验证 artifact。不使用 binout、nodout1 或相邻 d3plot 替代输入；ASCII 不接受 branch/shard，新的 NODOUT native_check 不可用。

## public-l1

独立参考扫描整行数值 token 与间隙，不导入生产 parse/COMPONENTS，也不使用生产固定12切片。最终干净提交运行六份已登记输入、九列及全部写出节点/时间，**54条曲线共231,147个值逐值相等**，CSV SHA、源 nodout SHA 与源目录文件清单前后核对通过。

| 已登记公共输入 | 帧 / 节点 | 九列比较值 | 有效性 |
|---|---|---|---|
| result.ansyshelp-ansys-com__doc-assets.4_2_Post_Plot_curve | 121 / 1 | 1089 | 当前有限 L1（cdc1957） |
| result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit | 1001 / 2 | 18018 | 当前有限 L1，非连续节点及九列非零 |
| result.pranavduraisamy__helmet-fit-bayes-opt.bo-runs.run0.drop | 251 / 1 | 2259 | 当前有限 L1（cdc1957） |
| result.pranavduraisamy__helmet-fit-bayes-opt.bo-runs.run0.pendulum | 251 / 1 | 2259 | 当前有限 L1（cdc1957） |
| result.zenodo__18598355.FEMU_Taylor.03_mat_CS_artificial | 669 / 21 | 126441 | 当前有限 L1，非连续节点及非零 x/z 数据 |
| result.zenodo__18598355.FEMU_Taylor.21_mat_JC_real | 429 / 21 | 81081 | 当前有限 L1（cdc1957） |

另两份输入仅做**正确拒绝的负例检查**，不能合成“公共8/8功能成功”：node997 的 header-only 文件无可读曲线；MLP 的隐式指数 `-1.5000-345` 属于合法输出可能使用的数值表示，但转换为 float64 会下溢，当前产品明确拒绝，不静默变0。
后者是本产品数值表示/支持范围限制，不记作源数据错误或用户模型缺陷；更多数值格式仍是 gap。

复跑时复用已有项目环境、从本工作树运行，并显式绑定 PYTHONPATH。以下 Windows 命令中的目录均为占位，输出必须全新且位于仓库外：

```powershell
$env:PYTHONPATH = "<worktree>\src;<worktree>"
python -B tools/verify_ascii_nodout_corpus.py --corpus "<已登记corpus>" --output "<全新仓库外目录>"
# 相关集合运行时不设置 LSPP_CORPUS_DIR；公共核对由上一条独立执行。
python -B -m pytest tests/test_ascii_nodout_parser.py tests/test_ascii_nodout_database.py tests/test_ascii_nodout_corpus.py tests/test_results_target_tools.py tests/test_ascii_glstat_database.py tests/test_ascii_matsum_database.py tests/test_ascii_record_lexer.py tests/test_glstat_reader_policy_compatibility.py -q
# 两个真实限制负例：
$env:LSPP_CORPUS_DIR = "<已登记corpus>"
python -B -m pytest tests/test_ascii_nodout_corpus.py -q -k explicit_no_data
```

## 历史与检查

| 独立范围 / 命令 | 结果 | 有效性 |
|---|---|---|
| 原 main2acfd72 九个新增 API 正例 | 9 failed，尚不接受 ASCII nodout | 历史红例，测试新增未提交，产品基线未改 |
| 纯记录核心 | 112 passed | 历史开发检查 |
| 首轮真实包装及相关集合 | 346 passed / 1 skipped | 历史开发检查 |
| 数字 header WIP（source ed16080b…） | 3红 / 1control | 已修 P1；数字内部空白不再拼接 |
| 前言标题 WIP（source1869affe…） | 4红 / 3control | 已修上下文误拒；包含根报告的三标题 |
| orphan WIP（source159bd006…） | 68红 / 8control | 已修 P1；形态识别与数值有效性分开 |
| 最终 clean cdc1957 相关集合 | 436 passed / 9 skipped | 当前有限本地检查；8个公共opt-in格另行执行，1个既有skip |
| 最终真实负例 | 2 passed | 只证明正确拒绝，不是功能正例 |

这些命令/子集重叠，计数**不得相加**。初轮六份公共正例属于修复前 WIP，只保留历史，不冒充最终干净提交或无 P1。
最终内部 Codex 子代理对精确 clean 提交复核，无剩余已报告 P0/P1；这不是用户安排的外部独立审阅，也不是 CI 全绿声明。
Ruff、import contracts、validate_tasks、gen_docs --check、迁移、corpus registry 和链接七项检查通过。

## 原生与其余 gap

具名 ASCII 原生映射尚未可靠确认，旧 numeric UI 常量和 binout 枚举不当作本库 ASCII 原生证据；没有开启 LS-PrePost、GUI、solver 或全量 REA。
更多物理布局、部分转动/节点集合、坐标与转动输出、其他版本及原生比较仍为 gap。Q06 保持 partial。
本分支未改 GLSTAT/MATSUM/共享 raw scanner 的产品 blob；已有读取/合同测试回归通过，但未重跑其原生，也未将历史 L2 重新绑定本提交。
仓库只收字段白名单、源身份与报告 SHA，原生日志、私有路径、原始公共语料正文和本机上下文留在本地。
