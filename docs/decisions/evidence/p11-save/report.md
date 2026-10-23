> 当前有效性：本报告是历史实现记录；后续规范化读取改变了路径，不能由它证明当前另存树的原生路径解析。当前产品绑定与真实原路径重开见 [审核02复跑](../p11-raw-review02/report.md)。旧运行与失败记录保留。

# P11：Include 树保真另存与原生重开

新增任务书既定 T1 `save_model(model, expected_counts?, expected_part_ids?)`。
复用 I07 的 `KeywordDeck.save_as` 保留相对目录、注释、换行及未改字节，不通过原生导出将 Include 展平。
先观察输入，再另存到新的 job/deck，自动在新的无图形 LS-PrePost 进程中重开，比较节点数、单元数和
Part ID 列表。显式预期值还须与输入观察一致；不符时返回 observations/differences，不返回 verified 产物。

所有输入文件与候选由现有允许目录规则保护。预检也在引擎访问守卫内执行；源文件 SHA256、源目录清单、
写出文件 SHA256 均在重开后核对。加载到内存与身份快照之间发生的源文件变化同样会被拒绝。
MCP 的预期计数/ID 使用 StrictInt，拒绝布尔、浮点、字符串隐式转换；空白异常诊断不会再次触发合同异常。

## 证据

最终执行逻辑的干净提交是 `c6415c5e0bd4423ab66e3313c12b0b88ff4152e8`；该历史阶段随后只补证据、任务文档和说明；后来的执行路线变动不受此记录覆盖。
八轮运行全部保留于 [evidence.json](evidence.json)，含实际 revision、dirty/diff 口径、测试 Git blob、
可执行文件与配置指纹、进程状态、实体观察和每份公开报告的 UTF-8/LF SHA256。未提交模型、派生模型、
原生日志、配置或私有路径。

| 历史最终运行 | 结果 | 范围 | 当前有效 / 已被取代 |
|---|---|---|---|
| [r413e](r413e-batch-report.md) | 7 passed | 独立模型、注释空 Include、三文件 Include、编辑后保存、公开 Bolt Include、公开控制卡编辑、计数不符负例 | 已被取代 |
| [r410c](r410c-batch-report.md) | 2 passed | 独立模型与注释空 Include；其余 5 项 deselected | 已被取代 |

正例均实际启动两个 `c= ... -nographics` 进程，保存前后实体计数与 Part ID 相同、源树未变；
负例只启动输入观察进程，作业按预期 failed，没有保存产物。公开 `include_contact` 有 1946 节点、
1341 单元、4 个源文件；控制卡编辑只改动一个文件，其余源文件不变，再保存/原生重开通过。

首轮 `ee6a9e0` 为 3 passed / 1 failed，失败的公开案例保留了只有注释的空 Include 备选段。
共享预检将其记作 warning，旧原生策略却拒绝。只读 SCL 最小实验确认 4.13 能读入原始树，
独立关键字引擎与 SCL 同为 1946 节点、1341 单元，源字节和目录清单不变；随后在完整 API 中复验。
只放开普通 `*INCLUDE` 的空段；不放开空的非普通变体、缺文件、越界、网络或放置错误的卡片。

本地相关逻辑回归为 136 passed / 4 skipped；其中四项是未显式启用执行的原生前置条件用例。
测试分别复现过：主干缺少 save_model 目标入口、合法空 Include 被拒绝、预检在守卫外打开外部文件、MCP 将 true
转成 1、空白异常信息引发二次 ValidationError。修复后均有回归覆盖。

## 当前限制

P11 保持 partial。INCLUDE_PATH/TRANSFORM 等变体仍被原生准入拒绝；非 ASCII Include 根路径、
4.10 相对 Include 的 cwd 解析问题尚未解决。4.10 只证明上述子集，4.8 与 GUI 会话未验收。
`save_model` 保存磁盘上的关键字树；旧 `export_keyword` 的独立模型接口保留。
绝对路径 Include 不改写为相对路径，仍按 `external_unchanged` 暴露只读外部依赖；不宣称输出自包含。

适用流程是 `edit_keywords` / `create_entities` / `mesh_ops` 返回编辑树的 `data.main`，再交给 `save_model`。
这份证据证明文件保存及原生读回的实体计数/Part 列表，不替代材料、接触或求解正确性的独立检查。
