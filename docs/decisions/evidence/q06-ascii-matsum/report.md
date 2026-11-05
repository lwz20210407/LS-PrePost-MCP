# Q06：ASCII MATSUM 具名能量曲线

状态为 **partial / L1**。本记录只覆盖 ASCII MATSUM 的五个具名能量列；没有 MATSUM 原生对照，不宣称完成 Q06 的全库、MPP/SMP 或 LSPP/LASSO 一致性验收。
最终读测产品提交为 `85ff7a308f3e7872e3abfb0e41e1de991f7d81ef`，运行前后工作树干净；产品与测试的 Git blob、源 SHA 和报告摘要见 [evidence.json](evidence.json)。

| 分量名 | 文件原始标签 | 口径 |
|---|---|---|
| internal_energy | inten | 按原文数值读取 |
| kinetic_energy | kinen | 按原文数值读取 |
| hourglass_energy | hgeng | 包含后续行，不填零 |
| eroded_internal_energy | eroded_ie | 缺项为 unknown，拒绝本次提取 |
| eroded_kinetic_energy | eroded_ke | 缺项为 unknown，拒绝本次提取 |

复用 `energy_readers` 的同一材料记录循环，Q06 是薄适配；Q12 默认 nullable 字典、替换解码和缺项行为保留。
ID 取文件明确写出的正整数 `mat.#`，不以记录序号、材料 MID 或标题位置替代。列顺序沿用首个时间块的写出顺序；后续块改换排列仍按写出 ID 对齐，调用者筛选顺序及原始存储列索引保留。
`units=source_energy`、`time_units=source_time` 仅为调用者声明，不猜测或换算单位。

Q06 要求每块部件集合一致、时间严格递增、核心 inten/kinen/hgeng 及请求列完整。缺项、截断、重复、非有限数、下溢或损坏赋值明确失败；写出的零保留为零。正常 prose/legend 不冒充字段。
已识别的 time、mat.# 和能量标签要求完整赋值身份；缺等号、缺数值、多头、重复或损坏标签不会被忽略后仍输出已验证 CSV。
实际输入在预检、SHA 及读取阶段分别受预算限制：Q06 为 256 MiB、单行 16384 字符和最多一百万部件行；共享读行器在每行前后检查已打开描述符的大小与原始字节位置。Q12 默认不获得总量预算。
源 SHA 前后绑定并写入 job.inputs，读取期间改变则 failed 且返回 artifacts 为空；不读取相邻 binout，不对 ASCII 应用 branch/shard，也不启用新的 native_check。

## public-l1

独立参考按文字赋值 token 读取 time、mat.# 和五个原始标签，不调用生产解析器的正则或映射。最终干净提交运行完整工具与 CSV 核对，三份输入 **49,460 个值逐值相等**，输入 SHA 与源目录文件清单前后不变。

| 已登记公共输入 | 帧数 / 部件数 | 五列比较数 | 结果 | 有效性 |
|---|---|---|---|---|
| result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit / matsum | 1001 / 7 | 35035 | 全值相等，非连续 ID 保留 | 当前有限 L1（85ff7a3） |
| result.praveenvenky110395__LS-DYNA-Crimping-Simulation.results / matsum | 131 / 22 | 14410 | 全值相等，包含非零沙漏能 | 当前有限 L1（85ff7a3） |
| result.node997__dyna_pladebuk.Plade_300_150_4.BB / matsum | 1 / 3 | 15 | 写出零与缺项区分；单帧不作原生曲线鉴别 | 当前有限 L1（85ff7a3） |

使用既有已登记 corpus，无下载或语料正文入库。Windows 可复跑命令如下；`python` 选用已有项目环境，输出必须是新的仓库外目录：

```powershell
$env:LSPP_CORPUS_DIR = "<已登记corpus根>"
$env:PYTHONPATH = "<worktree>\src;<worktree>"
python -B tools/verify_ascii_matsum_corpus.py --corpus "$env:LSPP_CORPUS_DIR" --output "<全新仓库外目录>"
python -B -m pytest tests/test_ascii_matsum_database.py tests/test_ascii_glstat_database.py tests/test_ascii_record_lexer.py tests/test_glstat_reader_policy_compatibility.py tests/test_energy_tools.py tests/test_energy_validity.py tests/test_results_target_tools.py -q
```

## 回归与历史

| 独立命令 / 范围 | 记录结果 | 有效性 |
|---|---|---|
| a8b059f 上七个新增功能正例 | 7 failed，ASCII MATSUM 尚不支持 | 历史红例，测试新增未提交、产品基线未改 |
| 首版相关测试 | 153 passed / 1 skipped | 历史开发检查 |
| 首次公共/相关用例 | 165 passed / 1 skipped | 历史开发检查 |
| 首次 main 合并后的扩展集合 | 198 passed / 1 skipped | 历史开发检查 |
| 首轮边界修复集合 | 193 passed / 1 skipped | 历史开发检查 |
| 009d717 上内部审阅的四类语法及 MATSUM 增长 | 5 failed；另 GLSTAT 增长 1 failed | 历史缺陷，旧正例不代表无 P1 |
| 57e0df1 上七类标签×六种语法及额外赋值 | 16 failed / 27 passed | 历史缺陷，保留原记录 |
| 85ff7a3 完整相关集合 | 255 passed / 1 skipped | 当前有限本地检查 |

以上集合重叠，**不得相加**。中间 grammar WIP 曾误拒 Timeless 等标题，四个失败正例及修复也保留本地；该 WIP 不冒充干净产品提交。
空行增长探针仅用 200 字节预算和少量追加文本；旧实现到末尾哈希才失败，修复后解析器消费额外行前即拒绝。未生成大文件。
Q12 的八组合成与三份公共输入，共十一组完整返回/异常结果，与抽取前 JSON SHA 一致。
009d717 的四个 GLSTAT 函数 AST/三个依赖 blob 不变证明仅属该历史阶段；后续共享读行预算确实变更，不能把旧证明套在新提交上。

本轮内部 Codex 子代理只读复核关闭了已报告的 P0/P1；这不是用户安排的外部独立审阅，也不是 CI 通过声明。质量检查包括 Ruff、import contracts、任务、文档生成、迁移、corpus registry 与链接检查。

## 限制与原生范围

`eroded_he` 在真实文件中存在，但共享 Q12 映射尚未覆盖；本入口明确拒绝 eroded_hourglass_energy，不将其返回为零。total_energy、mass、momentum、rigid-body velocity 均未新增。
辅助字段 x-mom/y-mom/z-mom、x-rbv/y-rbv/z-rbv、+mass、eroded_he 只用于支持布局的赋值身份检查，不作为新增测量列或物理推断。

此提交另跑既有两个 GLSTAT 4.13 headless 用例，目的仅为共享依赖回归；完整 101 帧、固定容差与输入/配置/二进制/目录守卫记录在 [GLSTAT 报告](../q06-ascii-glstat/report.md)。
**它们不是 MATSUM 原生证据**。MATSUM 原生具名比较、更多布局/版本和 Q06 其余完整验收仍为 gap。
原生日志、私有路径、原始语料及详细本机执行上下文留本地，仓库只收编字段白名单、源身份和报告 SHA。

根代理复核：在干净8ef0334文档头、相同85ff7a3产品blob上，重新跑230项解析/词法/GLSTAT/Q12相关测试全部通过，并再次实际核对三份公共输入的全部49460值，源SHA与目录不变；没有新增原生运行。
