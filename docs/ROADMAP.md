# 路线图

任务、范围和进度唯一来源：[tasks.yaml](../tasks.yaml)。此页列出原文退出标准；任务状态见 [TASKS](TASKS.md)。M0 不改变用户任务状态。

## M0 止血与准备

任务：准备阶段，不交付用户功能

基础设施：I06, I10, I11

退出标准：

- tasks.yaml 入库，校验脚本进 CI，docs/TASKS.md 由它生成
- docs 顶层不超过 12 份，其余 git mv 到 docs/archive/2026-10/；README 改为说明书结构
- KNOWN_ISSUES.md 收齐全部原生坑，每条注明来源文档
- uv run pytest 通过（不装可选依赖时相关测试 skip 而非 fail）；validate_model_references 合同 bug 修复并有回归测试
- E1-E5 实验与批处理通道矩阵有记录，会话传输决策写入 ADR
- tests/corpus/manifest.yaml 建立，全部现有工具（138 服务 + 4 知识）的迁移映射表完成
- SKILL.md 改为"意图 → 工具"路由表（不超过 150 行），更新日志式内容移入 CHANGELOG
- M0 不新增任何 MCP 工具或功能

## M1 底座

任务：A01, A02, A03, A04, A05, A08, A10

基础设施：I01, I02, I03, I04, I05, I08

退出标准：

- 现有手动原生验收（tools/run_*）全部迁入 pytest -m native 并在新引擎上通过
- 五个通道统一到 run_script，batch/session 两种上下文都有 L2 用例
- 至少 5 个示范配方；search_docs 可查命令 / API / 关键字字段
- import-linter 生效，src 中不再有函数内 from .service import

## M2 后处理任务包

任务：Q01, Q02, Q03, Q04, Q05, Q06, Q07, Q08, Q09, Q12, G01, G04

基础设施：I09

退出标准：

- 本里程碑任务全部 done
- L3 后处理 8 题至少 7 题成功

## M3 前处理任务包

任务：P01, P02, P03, P04, P05, P06, P08, P09, P10, P11, G03

基础设施：I07

退出标准：

- 本里程碑任务全部 done
- L3 前处理 8 题至少 6 题成功

## M4 自动化与发布

任务：A07, A09

基础设施：I09

退出标准：

- v0.5 全部任务 done
- L3 20 题至少 16 题成功
- 干净环境按 README / INSTALL 步骤可装好并跑通示例
- Skill 完整重写：路由表 + 每类任务 SOP（必填参数、工具、验证方法、何时拒答）
