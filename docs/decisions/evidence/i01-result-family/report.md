# I01 结果族读取防护（2026-11-05）

I01、Q01、Q05 保持 **partial / L1**。本轮统一允许目录检查、SDK 候选预测、流式身份快照和业务结束后的复核，不改变结果数学、不增加工具、不提升 done。两份 4.13 梁样例的原生数值对照只在该局部范围属于 L2；内部 Codex 交叉复核不是独立外部审阅。
机器摘要、实际修订、源/测试 blob、输入与报告 SHA256 见 [evidence.json](evidence.json)。原始本机路径、供应商输出及日志保留本地，不入公开仓库。

## 问题和行为

LASSO 2.0.4 把 basename 插入 `(<basename>)[0-9]+$` 发现续文件；原有字面前缀收集可能漏掉实际读入对象。例如 `model.d3plot` 会匹配 `modelXd3plot02`。部分 legacy/标量/实体入口还只复核主文件或旧固定列表，续文件改变可能仍返回成功。

中央 planner 先执行现有允许根、设备/网络与链接守卫，再 stat SDK 将探测的目录项。危险运算符 `^$*+?{}[]\|()` 在目录枚举前拒绝，不编译用户正则；常见点号 basename 用固定宽、线性单字符通配预测已锁定 SDK，随后与字面数字续文件集合比较，不一致就拒绝。控制字符目录项在守卫后、metadata stat 前拒绝，包括 Python `$` 特殊处理的末尾 LF。普通子目录、普通文件、安全字面名及含方括号的父目录继续支持；父目录传给 `os.listdir`，不参与 glob。

guarded SDK factory 和共享 snapshot 覆盖 legacy metadata/nodal、普通 field、tensor、history、entity 与 full/compact 注册入口。输入成员、解析目标、元数据和 SHA 在实际读入前固定，在导出、CSV 回读、artifact 验收等业务收尾后复核；改变即 failed，不把验证成功的 artifact 发布出去。上下文中的更窄 guard、active 同源与 provided snapshot 都取约束并集，异常后恢复 ContextVar。

自有 SHA 使用无缓冲读取，预算为初始 `st_size` 加最多 1 字节增长探测；打开 fd 后先 `fstat` 核对身份，再读内容，并拒绝增长、截断或 stat/open 替换。没有给非原生结果统一加上原生的 2 GiB 限制。

原生 beam 保留既有 1000 states /1000 files /2 GiB 和显式 default、4.13 resource 条件。预算预览只通过内部受限 reader 读取 timesteps，核对成员及 stat 身份，不产生业务结果；普通强读取不能隐式复用这个弱身份。预算通过后才取得全 SHA，并与实际读出的预览时间表比较。

## 修订和实测记录

| 记录 | 实际修订 | 结果 | 有效性 |
|---|---|---|---|
| 旧 main 的新增小回归 | `4365c4355bc1d6501079e24c05521b8d3534c6cd` | 6 failed，产品未改，仅注入未跟踪测试 | 历史真实红例 |
| 首版 I01 自有 hash 反例 | `fa5a00a`（完整值在 JSON） | 2 failed；初始 128 bytes 读到 192，且替换先触内容 | 历史 WIP 红例，不冒称已合 main 缺陷 |
| 精确产品头内部复核 | `e5c3e26750a98ed97690efcdd1ad42c3f8b58056` | 109 项及另 16 个小控制通过 | 对登记产品 blob 有效；统计重叠，不累加 |
| 同头扩大相关矩阵 | 同上 | 246 passed /6 skipped | 相关测试，不是全仓；跳过不算通过 |
| 第一次公开标题对照 | 同上 | 15 passed、3 捕获，Parts 为 2/7/7 | 原样保留 |
| 两份 4.13 headless beam | 同上 | 2 passed /0 skipped、26 行 | 局部原生 L2，不外推 |
| 新依赖存在性门禁 | `f31b06eb047ed3d97d58b2c8e1ab23424951997c` | 旧 active 证据漏 family.py 时 1 failed | 测试仪表修正；旧 JSON 未改来凑绿 |
| 新清洁测试头公开标题对照 | 同上 | 再次 15 passed、3 新捕获 | 对登记产品 blob 有效，不覆盖第一次记录 |

旧 main 六条回归实际覆盖：额外 SDK 候选未拒绝；两条 legacy metadata 在 admission 前进入 SDK；legacy nodal 在续文件改字节/新增成员后仍成功；legacy metadata 在续文件变动后仍成功。旧输出的 DID NOT RAISE、提前调用 SDK 和 succeeded/failed 差异已保留日志摘要 SHA。

内部审阅中另修复五项 **WIP** 问题：weak 到 strong 的隐式复用、active 同源内层 guard、provided snapshot 丢失当前 guard、nodal artifact verifier 的尾部 scope，以及原始用户正则回溯。最终精确头通过 8 格 guard 组合、4 格 SDK 期间更窄策略、正常/异常恢复、普通目录、父目录方括号、点号候选差异及真实 1001-state 路径不 SHA/force/job 等控制。没有把 WIP 尝试当成已发布缺陷或独立外部验收。

## 原生与标题对照

| 公开来源 | 选中数据 | 数值最大绝对误差 | 时间最大绝对误差 | 身份检查 | 有效性 |
|---|---|---:|---:|---|---|
| `result.open-lasso-python__lasso-python.test.test_data.d3plot_beamip` | 1 beam ×2 states | 0 | 0 | 5 内部 +4 外部均真 | e5 产品局部参考 |
| `result.ansys__example-data.result_files.d3plot_beam` | 2 beams ×12 states | 0 | 0 | 5 内部 +4 外部均真 | e5 产品局部参考 |

使用既有固定容差，无放宽：时间 `rtol=1e-6, atol=0`；数值 `rtol=2e-5, atol=1e-6*max(abs(reference curve))`，全零曲线没有单位尺度 floor。force/frame 为 as stored，binding-default ipt 语义未独立识别，自定义单位标签仍未验证、没有换算。两例均无 GUI、无 solver；启动前后确认没有 LS-PrePost 主进程，lease 已释放。

原生执行严格属于 e5，源/测试身份按 **该真实执行修订** 的 Git 对象登记；31 个产品文件表示 native 调用链及相关改动的来源身份，不表示这 31 个模块的所有功能都测试过。f31 只增加测试门禁，产品 `src` blob 与 e5 全同，因此不为仪表变动重复 native。raw report、执行上下文及每例输出的 SHA 保留；依赖 Python 源文件的额外审计发生在原生结束后的未改共享环境，不冒充另一次启动证明。

两次三份标题对照都由公开配对 keyword 的 PART/PART_CONTACT 通过 KeywordDeck 独立取标题，不再 zip 结果标题 ID 自证。数组读取置于公共根 access.confined，真实依赖 family.py 已在两次产品路径中。f31 新门禁要求 active 证据明确列该依赖；共享 q01/q05 当前记录由根代理用新实跑白名单整合，不在本文件重写旧结果。

## 复跑和限制

固定锁定依赖，`PYTHONPATH` 指向当前 worktree 的 src 和根目录。缓存、报告和 native output 使用新的仓库外目录，不复制语料或新建环境。登记命令中的 `<...>` 为调用者配置值，不是本机路径。

```text
python -B -m pytest tests/test_result_family_confinement.py tests/test_beam_native_check.py tests/test_field_metrics.py::test_input_validation_and_refusals -q
LSPP_CORPUS_DIR=<configured-public-corpus>
LSPP_TITLE_EVIDENCE_DIR=<fresh-external-title-output>
python -B -m pytest tests/test_part_title_identity_review02.py tests/test_part_title_keyword_oracle.py -q
python -B -m pytest tests/test_beam_native_check_native.py --run-native --native-strict --native-executable <verified-4.13-executable> --native-output <fresh-external-native-output> -q
```

原生需显式授权与单一 lease，前置标题对照通过及清洁头核对；不自动启动 GUI 或 solver。Ruff、lint-imports、validate_tasks、gen_docs --check、validate_tool_migration、fetch_corpus --check-registry、check_doc_links 已通过。

同一业务 scope 的多次 SDK 构造共享一份身份快照，一般需要两次全族 SHA。既有 metadata 预读/特殊路径可能额外 hash；因此大族仍有明确 IO 成本，不能用尺寸/mtime 冒充内容身份。每个自有 hash 有初始尺寸读取边界，但第三方 SDK 本身没有新增统一的时间/内存总预算；不声称防御任意 OS 级并发篡改。无关越界链接也拒绝，因为 SDK 在匹配前会探测目录项。其他版本、梁公式及 UI/队列场景的覆盖限制继续保留，整体仍为 partial。
