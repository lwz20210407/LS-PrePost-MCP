# 开发与集成看板

2026-10-18 用户确认恢复开发，由 Codex 独立负责实现、测试、审阅和 PR 集成。旧四方分工及持续 AO 派发暂停执行，是否恢复由用户决定；不自动重启其他 AI 或定时任务。任务范围、验收、版本及完成状态仍只取自 [tasks.yaml](../tasks.yaml)。

## 当前工作

截至 2026-11-07，按交接继续 Codex 内部多 Agent 并行；外部四 AI/AO 仍暂停。先收尾 I05/Q05/Q06，根代理统一共享文档和集成、原生 LSPP 串行。REA 仅在具体原生逻辑不明时按需使用，不恢复全量队列。

| 跟踪任务 | 当前状态与交付 |
|---|---|
| G03 / P09 | actual clean2911修合法Tri3三点质心与普通BEAM基础端点质量；集成110项、SDK缺席11过45跳、旧壳/实体完整报告两组字节等价。两版八MeshOp32job和默认31job按当前源真实刷新，新context保actual2911，旧8ffc及其它历史原值保留；A10 12产品/27输入不变无新索引/98题；仍partial，详见[G03/P09报告](decisions/evidence/g03-p09-regressions/report.md) |
| P10 / A10 | #176最终ba03五CI全绿merge main ebb2817，main push亦成功；8ffc选择范围共享源变更后相关默认源验证实际刷新，A10 12产品/27输入不变不重建索引或冒领98新查询；仍partial |
| P06 身份 | #174精确d8d五项CI通过已合main06b8；旧51c5真实28红、overlay3红、bcfa UserDict2红与clean85的87项/内部4控制原值保留。几何接线后actual cleanb757原执行集87项与35关键来源真刷新，新context不重绑旧记录；P06仍partial/L1 |
| P06 几何 / 依赖来源 | #175五项CI通过已合main21978，check_model只读contact_geometry opt-in已接，预算/覆盖缺口不充零，native_verified=false；actual cleanb757独立geometry host90/39来源、P03原60/显式24、身份87/35及offline wheel785079B/221成员/9旧refs与原Elastic pin通过，各host角色重叠不累计。P05两版6job、P12两版18job按当前43来源真刷新，typed/物理/原生Contact Check不升级；五份新context/报告独立于原40/41，待精确PR头正式CI |
| Q01 / Q05 | #129 已退回 partial；#130 已修 Part 标题/PID 口径；#136 已修删除标记并补非零节点的 4.13/4.10 对照。广泛结果覆盖与独立审阅仍待补 |
| I01 / P02 / P11 / I02 | #131–#134 已修访问点守卫、搜索路径另存、必需检查失败的总状态、真实另存树原生重开；保留首轮失败及旧证据 |
| A10 / I05 | #137 已限制去重概念数；#139 已在精确头五项 CI 通过后自审合入查询端拆词和证据复跑。真实 API 来源与检索质量仍有缺口 |
| Q03 / Q04 | #138 已在精确头五项 CI 通过后自审合入，修显式壳存储点、计数/坐标/容差，4.13/4.10 各八项对照已登记；Q03 保持 partial |
| P02 表达式 | #135 Draft 保留。R11 在控制算例上同样启动超时；用户要求先做其他项，求解器侧证据待验，不重试阻塞开发 |
| I04 | #147 已修合法变体分类并完成15例定点复跑：3例修复通过、11个合法变体读入成功但产品往返失败、010参数仍失败；台账48/13/39混合历史与新运行，不代表全批新头通过 |
| Q05 / Q07 历史 | #149/#150/#153 已合入；SAE 原生兼容 profile 已登记，默认 J211 不改。Q05/Q07仍partial |
| Q07 本轮 | #154 已合入9c3c614，PR/main五项CI全绿；4.13/4.10各20原生通过，默认14组数值逐位保持。任务仍partial |
| I05 / A10 | #155零命中诊断已五项CI全绿合入；#159四冻结题集公开复跑14/20、22/30、15/24、13/24，根逐条重查引用/分数一致；补产品漂移与通用词形门禁，缺API来源与独立留出仍partial，#159精确头五项CI全绿已合入 |
| Q05 | #156时程及#161限定4.13/default的beam轴力native_check均五项CI全绿合入；正式两样本26条力/时间差0、身份守卫通过；版本策略归统一能力表，仍partial |
| Q06 | #160与#163已在各精确头五CI全绿后合入，#163进入49cd217；NODOUT九平动列6公共231147值、raw/unknown life与来源门禁已有，未原生仍L1；eroded_he有限审计不足以命名映射，保留gap |
| I01 结果族 | #162已在6212430精确头五项CI全绿后合入d946f1e；raw路径分类及P11来源过期已修，a20两版P11/beam/标题真重跑，原门禁保留；仍partial |
| P04 | #168已合；#175 CI指出旧operations来源过期后actual clean342b显式13来源、单4.13一个headless job真复验，四owned节点/三sets membership成立、ADD order false；PROGRAM/SOURCE/动作未改。新context独立选择，旧1289/01a/950/d139及b757五context不改；controller/child OS创建未观测、host时间不冒充OS时间，private input与global passive分开，仍partial |
| P12 | #165已合；#171 actual3da/9b3显式41含loads的两版六case/18job真复验后切active；1289原40后验补档及旧be0等对象原值保留；strict R1/格式分列，typed Joint识别与运动学仍未证，partial |
| P05 | #171 无损身份/原子性/Include上下文恢复已修；actual3da/9b3九类单文件在两版各3job通过，strict59、37文档写出规则与6受限观察分列，剩差0；原8e failed3与analysis-only保留。P05六+P12十八共24实际job私有配置输入/源/目录守卫及内部逐账复核通过，typed/物理/R11未证，partial；待精确五CI |
| P02 / I07 / P11 | #166已合；#169 named setter修复源码eeff，actual1289/611d unified65已完成：P11双版46+P12双版18+P04单1，批准只读private input保持、globals仅passive，旧身份不改绑。标题eeff15/3同八源不重跑；已按精确5d/正式42022286623五SUCCESS合main9301，未升级done |
| P03 / A10 | #170精确ab252/run42015075528五SUCCESS已合main15ac：六MAT/两EOS+JC/EOS/solid/Part一次事务已接model: keyword/L1 candidate，发现/索引内容版本pin关闭首轮漂移P1；clean02b专属60项、内部有限peer/wheel实际提取与stdio控制通过。唯一公开索引原98题真实重放，root同库逐条核对一致；相关260/2skip、七checks过，另修portable来源门禁后20项过，PR/main来源按实际记录保留；原生PartData/物理验收仍gap，保持partial，不派AO；169后台deck变更后actual1ba原60 host/stdio与新offline wheel778549B真刷新，旧02b/98结果留存，不重复已回收全索引 |
| I08 / P03来源 | #172补客户端迁移元数据，142兼容名/21现行名、默认full163/compact3及签名路由保持；合main9301后的clean7fb原60 host/stdio、新wheel778992B及迁移相关31真通过。原21显式来源及proof不改，registry数据从同次实际完整before/after归档，22口径经root核对；旧02b/1ba/98对象留存，无新索引或native。待相关门禁及精确五CI，不改完成等级 |
| I06 | #167独立历史hash口径P2已在精确689f764/正式41981372125五SUCCESS后合入main dba51d；旧raw SHA/原run/active指针不改，另记GitLF身份。P04新来源门禁与受限证据在本分支收尾，不夹无关P2 |

Q01/Q05 及其他任务今后改为 done 前，须按用户安排完成独立审阅和原生证据抽查。当前不派发 AO 任务。

## 2026-10-22 遗留 PR 处理结果

用户 2026-10-22 让 Claude 处理积压：小的修完合入，有 P0 的关闭。

| PR | 任务 | 结果 |
|---|---|---|
| #26 | I01 面板引擎 | Claude 修 P1（迟到 Apply 须宿主校验、I01 退回 L1），Codex 审阅后合入 |
| #84 | Q01 | Claude 修 P1（头字段走共享 lasso_backend、读取前约束同族文件和 binout 分片），Q01 保持 partial，合入 |
| #93 | A10 | Claude 修 P1（英文词干截断、显式 *KEYWORD 排序），留出集独立性未获证明，A10 保持 partial，合入 |
| #82 | Q04 | Claude 修三轮（1 起算 state、部件筛选、掩码筛行、公式与 Lode 约定、无删除数据时拒绝依赖删除状态的掩码），合入 |
| #57、#90、#98 | Q10/Q12、Q03、G04 | 有未解决 P0，关闭不合，分支保留；问题已登记到对应任务 gaps（#107） |
| #73、#101 | I06、Q12 | 已在 10-22 之前关闭 |

未修的审阅 P2 已登记到 Q01、Q04、A10、I01 的 gaps。#108（Codex，Q12）已在五项 CI 通过后合入 main；能量检查保留 partial，后续原生对照仍按任务缺口推进。

2026-10-22 用户补充确认：阶段汇报后直接继续下一项，不把单个 PR 合入当作停止点；当前接续 Q07 相对曲线和 Q01 已登记审阅缺口。

## 完成及集成要求

- 修 bug 先证明回归在未修版本失败；本地运行相关测试，CI 完成 Ubuntu/Windows × Python 3.11/3.12 与最小依赖检查。
- 逐条处理遗留 P0/P1；自审如实标为 Codex 自审，不冒充 Claude 或独立第三方审阅。
- 只用 merge 同步主干。CI 后主干出现重叠文件改动时，重新同步并验证。
- headless 原生串行执行，记录 revision、dirty 状态、输入及产物身份；GUI/UU 没有新窗口时保留待测。
- 公开仓库不提交受限语料、私有路径、安装手册、原生日志或凭据；复用共享环境，不建每任务环境。

P08 当前：selector-only范围缺陷已修并有干净旧源2红/新源2绿。actual8ffc两版本各8用例/32真实headless job完成 typed geometry + keyword references 核对，32全部源/配置/指定偏好/namespace守卫通过；>300000私有性能仍待，状态partial。共享操作模块的31默认Native兼容检查也已实际通过，不拿旧记录更新SHA；新current来源独立归档，旧帧原值保留。
