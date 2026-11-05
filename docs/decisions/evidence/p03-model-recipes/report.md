# P03 主机侧材料配方注册（L1，partial）

此轮补齐既有材料/EOS 引擎在 `run_recipe` 的 T2 注册，保持 P03 原验收、v0.5/M3 和 **partial**。没有运行 LS-PrePost 或求解器；不把通用 P11 保存证据当作这些新配方的原生 Part Data 回读。实际 source、测试、失败和打包身份见 [evidence.json](evidence.json)。

## 功能与使用

`find_recipe(task_id="P03", channel="keyword", include_candidates=True)` 返回候选；默认发现仍只列原来已证原生条目。候选明确为 `backend=keyword / L1 / candidate`，原生版本列表为空。调用方应将返回的 `reference`（`model:id@<source-version>`）传给 `run_recipe`，固定这次发现的配方、参数 schema、manifest/provider/core/验证合同。来源改变时拒绝旧引用；不带 pin 的 `model:id` 继续作为**显式 latest** 兼容入口，结果元数据标明该选择。没有增加 T1 工具或修改 `run_recipe` 参数签名。

| 裸 ID | 关键词/流程 | 本轮级别 | 有效性 |
|---|---|---|---|
| model:mat-001-elastic | MAT_ELASTIC / MAT_001 | L1 host | 当前实现 |
| model:mat-003-plastic-kinematic | MAT_PLASTIC_KINEMATIC / MAT_003 | L1 host | 当前实现 |
| model:mat-015-johnson-cook | MAT_JOHNSON_COOK / MAT_015 | L1 host | 当前实现 |
| model:mat-020-rigid | MAT_RIGID / MAT_020 | L1 host | 当前实现 |
| model:mat-024-piecewise-linear-plasticity | MAT_PIECEWISE_LINEAR_PLASTICITY / MAT_024 | L1 host | 当前实现 |
| model:mat-098-simplified-johnson-cook | MAT_SIMPLIFIED_JOHNSON_COOK / MAT_098 | L1 host | 当前实现 |
| model:eos-linear-polynomial | EOS_LINEAR_POLYNOMIAL | L1 host | 当前实现 |
| model:eos-gruneisen | EOS_GRUNEISEN | L1 host | 当前实现 |
| model:johnson-cook-solid-part | 材料、EOS、solid section、Part add/set 一次四操作 | L1 host | 当前实现 |

简单材料参数为 `units`、严格整数 `mid`、`params`，可选 `title`；EOS 用 `eosid`。参数 schema 不含物理 default，单位只由调用方声明，不推断或换算。可选字段仍使用既有关键词引擎/LS-DYNA 默认语义。最终曲线引用、MAT_024 的 SIGY/LCSS、多项式 EOS 非零系数等检查也由原引擎完成，没有另写 keyword 解析器。

复合配方需要 `mid/eosid/secid/pid`、`material/eos/section` 参数对象和 `part_action`。`set` 修改既有 Part，拒绝会被忽略的 `part_title`；`add` 必须给标题。它调用**一次** `edit_keywords`，任何后续操作失败都不发布前面定义的 `.k` 或成功 artifact。输入的 Include 树及原字节保持；不会逐步写完材料后再尝试关联。

这些配方拒绝 GUI session、d3plot 和 runc，执行依赖项目的 `pydyna` extra。缺 SDK 时离线发现和知识来源仍可用；不自动安装依赖，不伪装成 embedded Python/native channel。

## 实际验证与边界

| 记录 | 实际来源/结果 | 角色 | 有效性 |
|---|---|---|---|
| 初始公共 API 反例 | be324 产品代码上两例失败：无 P03 发现、model: 落入旧路径解析；新测试已加入，不声称测试 checkout 干净 | 缺口复现 | 历史，已修 |
| 首轮漂移反例 | b51 上五例失败；同发现引用可在定义改族后仍执行，缺 index pin | P1 复现 | 历史，已修 |
| 精确 L1 测试 | clean `02b1a9d4220c1df564e813d99eb91eefab4b0490`，60/60 passed，原四专属测试文件 | 真实 host/API/atomic/source-pin | 当前产品 blob 有效 |
| 内部有限复核 | clean6533，10 项通过，含 LF/CRLF 相同 pin、旧合同拒绝及 wheel-style 控制 | 内部 Codex peer，非独立外部 done 审阅 | 当前相同产品 blob 有效 |
| 打包 | clean6533 离线 wheel 778,095 bytes；provider+manifest 在包内 | 不安装共享 runtime | 当前相同产品 blob 有效 |
| 提取包 | 新 Python 进程断言 provider/service 实际来自提取目录，pinned host recipe 成功 | 防旧 editable 源假阳性 | 当前相同产品 blob 有效 |
| 真实 MCP | full/compact stdio 均发现九候选、使用返回 pin 成功创建 Elastic，2 passed | 无 native 请求；与其他子集重叠 | 当前相同产品 blob 有效 |

六材料、两 EOS 均实际经过 `Service.run_recipe`。复合用例使用现有 [pre03 手写 oracle](../../../../tests/l3/scenarios/pre/pre03_jc_material.yaml) 的 mm-t-s 数值：Part 2 使用 MID3/EOS1/SEC2，Part 1 保持，Include mesh 及原两文件字节不变。单位、未知字段、非有限值、bool/小数/字符串 ID、引用字段和晚期 Part 失败均有拒绝控制。

字段快照只取锁定 ansys-dyna-core 0.12.1 的公开 FieldSchema 类型事实，共121项；运行前核对 provider 版本/字段类型。**121 项事实不是121种参数组合的行为验证**，产品身份清单也不表示每个模块的全部功能都测过。没有复制私有手册、用户材料标定数据、安装包或原生日志到仓库。

## 检索来源

九个候选真实进入 `repository_documents`，标 public/MIT/keyword/L1/pinned reference；默认 find 排除候选不等于索引隐藏它们。独有新公开索引只建一份，原四套共98题保持所有题面/答案 blob，结果及 root 同库逐条引用/分数复查见 [A10 新重放](../a10-model-recipes-refresh/report.md)。没有为成绩修改排名或词表。

## 未完成

文档及 active A10 收编后的最终相关命令（配方/知识/原材料核心/当前证据）为260 passed / 2 skipped；Ruff、import-linter、任务/生成文档/迁移/语料注册/链接七项检查通过。此数与上表子集重叠，不能累计成额外样本或 native 通过数。完整四组合和最小依赖以本 PR 的精确 Ready 头 CI 为准。

证据收编阶段的进程内可选 SDK 缺席控制为43 passed / 15 skipped（配方、知识、pin 三文件）；过期 pin 的三个拒绝用例无需 SDK，已取消不必要的 skip 并真实执行。另11项 pin/证据门禁通过。这是测试仪表收口，不改产品源码，也不将旧 clean02b 的60项记录重新绑定到新测试文件。

原生重开后的 Part Data ID/字段/关联回读、材料物理校准、更多可选参数组合及版本覆盖仍未完成。此轮不提升 P03 为 done，不继承旧卡片的 R11 历史结果作为新 T2 流程 L2。
