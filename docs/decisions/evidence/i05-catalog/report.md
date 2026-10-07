# I05：完整提供者目录构建与读回

2026-10-06，直接调用已合入包内的 Claude keyword_docs 公开接口，没有修改其实现。
实际 Git revision 为 `9651d02c687f68a2698e1c258cddfb3ea5c4795a`，运行时有未提交修改；
`git diff HEAD --binary` SHA256 为 `53b252788f2b154be939a4bd2095d008cbea2780ab3a3c0b966d12b8d127bdba`。
源码、索引指纹、目录覆盖和读回结果见 [evidence.json](evidence.json)。

## 发现与修复

旧代码用 `*ALE_BURN_SWITCH_MMG` 实际复现 conflicting field identities。
完整目录中 34 个关键字的旧 locator 冲突：32 个为同卡同名不同列位，2 个为完全重复记录。
后两者为 *MAT_217_ANIS 与 *MAT_ANISOTROPIC_ELASTIC_PHASE_CHANGE 的卡 8 字段 xp2；
索引身份原先未包含列位。
修复后 locator 纳入 offset/width，同槽矛盾定义仍拒绝，完全相同记录去重。
数据库结构维持 schema_version=2；旧索引继续可读，重建才获得新的字段身份。

## 实际结果

- 提供者目录：3171 个关键字标识全部遍历，无提供者异常。
- 原始字段：66902 条；2 条完全重复去重后，数据库保留 66900 条，覆盖 3133 个有字段的标识。
- SQLite integrity_check=ok；孤立字段、重复槽位均为 0。
- 四组重复字段经 keyword_fields 检索保留各列位，另验证 MAT_ELASTIC 的 E 字段查询。
- 加入本机已有的私有 API、用户指南后，六类数量为：命令 1250、API 68、关键字字段 66900、
  指南 288、配方 15、已知问题 76；逐类检索有结果、有来源/版本/证据等级，默认私有过滤有效。

38 个目录标识没有返回命名字段，完整名单在 evidence.json 的 without_fields 中。
其中须区分无字段指令和未提供的布局；本轮不把它们计为字段覆盖通过，也不修改 Claude 的提供者。
I05 保持 partial。六类冒烟不是 A10 留出集质量评测，未使用留出题调参。
这次没有执行 LS-DYNA/LS-PrePost；字段来源和提供者记载的 solver_status 不等同于本次原生实测。

索引、手册原文及派生文本保留在仓库外。仓库仅附汇总、公共字段列位和指纹；未使用 local-book。

## 2026-10-07：38 个空字段项分类（Cursor）

基线 `e41cf65`，未提交改动 `git diff HEAD --binary` SHA256 为
`6a80db9d887f20b01e950fffb4e217318c5e9c00e9d7d723d8f1f900aa9bc52c`（计算时只含源码、测试与评审数据，
不含本报告、证据文件和 tasks.yaml）；各源文件指纹与构建读回见
[fieldless-review.json](fieldless-review.json)。提供者仍只读，没有执行 LS-DYNA/LS-PrePost。

- 适配层按提供者返回的卡片类型记录空字段原因（无卡片、无命名字段、自由文本、SeriesCard 未给布局、
  生成式 CardSet 布局为空），这一步只看提供者，不看手册。
- 对照本机私有 R17 关键字手册索引逐项复核，仓库内只登记结论标签与依据类别
  （`src/ls_prepost_mcp/data/keyword_fieldless_review.json`），不含手册原文、页码或派生文本。
- 结论：23 项无数据卡（提供者正确）；1 项自由文本（*COMMENT）；10 项手册有字段而提供者未给布局；
  4 项手册无独立章节，无法判定。10 项缺失布局属于 Claude 的 keyword_docs 提供者，本任务不修改、不复制。
- 38 项现在作为公开的关键字级文档入索引，并写入 `keyword_without_fields` 表；
  全目录 3171 个标识都可检索（66900 字段 + 38 关键字文档），schema_version 仍为 2。
- 六类管线复验中 API 类只用一行合成私有夹具检查外部来源路径，不是 Scripting API 内容；
  真实私有 API/用户指南在新头上的复验需要用户提供本机来源路径。

## 第六轮复核

历史 53b25278… 补丁包含源码/测试/工具，排除 docs、tasks.yaml，不包含未跟踪文件。
复算命令：`git diff 9651d02 d6f64fa --binary -- . ':!docs' ':!tasks.yaml'`。
重挂分支只 cherry-pick d6f64fa，不包含 Draft #26 的面板改动。
新增重复字段回归确认完全相同的两个输入只生成一条字段和一条 keyword 文档。
