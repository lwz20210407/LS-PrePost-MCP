# PyDYNA 六个文档板块与迁移合同

基准版本：`ansys-dyna-core==0.12.1`；上游 tag `v0.12.1`，commit `dee72b980fd48e5228d33c29cc0076f86f6b9003`。六个官网入口是文档板块；核心公开功能主要围绕 `keywords` 与 `run`，另有 Deck、字段/表格、验证、变换和绘图基础设施。**研读和接口接入不是“所有功能已移植”的证明。**

## Getting started：安装、模块与代理指导

已核对安装说明、模块页、AI instructions 和初始案例，采用独立 MCP Python 环境与固定 PyDYNA 依赖，不改变 LS-PrePost 嵌入式 Python。

发现安装网页仍写旧 Python 支持范围，而该 tag 的 `pyproject.toml` 指定 `>=3.10,<4`。实际安装应核对发行元数据。官网横幅称 `run` 被移除，但模块页、示例和该 tag 源码均存在 `run_dyna`；被移除的旧 `pre`/`solvers` 路线不得继续套用。

上游代理指导可帮助检索，但本地旧指南里的 `Deck.load`、`Section001/002` 等片段不能凌驾于实际版本 API。当前调用使用 `import_file/export_file`，以运行时字段为准。

来源：[Getting started](https://dyna.docs.pyansys.com/version/stable/getting-started.html)、[tag 元数据](https://github.com/ansys/pydyna/blob/v0.12.1/pyproject.toml)。

## User guide：执行边界与结果路径

区分三个执行层：PyDYNA 创建/修改关键字；LS-PrePost 原生前后处理；LS-DYNA 求解进程。后处理示例中的 DPF 是另一个软件组件，不能因安装了 PyDYNA 就宣称 DPF 服务或全部结果算子可用。

已实现 Deck 构造/修改与原生重开衔接；`run_dyna` 的平台 runner、工作目录、资源参数和失败处理已检查源码，但求解调度与 DPF 工具尚未接入。本仓库当前不会因运行官方案例说明而自动启动求解器。

来源：[User guide](https://dyna.docs.pyansys.com/version/stable/user-guide/index.html)、[local_solver.py](https://github.com/ansys/pydyna/blob/v0.12.1/src/ansys/dyna/core/run/local_solver.py)。

## API reference：通用关键字层

新增工具按实际安装版本检索，不逐个硬编码所有材料卡：

| 工具 | 合同 |
|---|---|
| `list_pydyna_keywords` | 检索已安装关键字类；类存在不等于已通过本项目验证 |
| `describe_pydyna_keyword` | 获取实际属性、默认值、表格列和字段说明；条件容器明确标记 |
| `compose_keyword_deck` | 通过结构化 class/fields/options 构造标量卡、表格卡、序列卡；输出新 deck |
| `update_keyword_fields` | 用标量属性唯一匹配一个关键字，修改后输出副本 |
| `update_keyword_table_row` | 在 NODE/ELEMENT/PART 等表格中按显式列值唯一定位一行，修改后输出副本 |

写入之前运行 PyDYNA 默认验证器，写入之后重新导入，核对显式字段。未知字段和表格列、非有限数值、多行注入、模糊匹配都会失败。表格按列名核对，允许导入器补齐未显式指定的默认列；不把列顺序变化误判为数据变化。

源码适配要点：

- `SectionShell` 等 0.12 的 card-set 类型需要先初始化首个 set，再访问标量代理属性。
- `SetNodeList.nodes` 返回 `SeriesCard`，不能当普通标量或 pandas 表格处理。
- 关键字对象不能同时归属两个 Deck；复制网格时建立新卡并复制 DataFrame。
- TITLE/ID 等选项要显式激活。`apply_lspp_defaults` 只能处理库定义的缺省字段，不能替用户决定材料、单位或边界条件。
- 多层 card-set、参数表达式、复杂 include/transform 尚不属于通用编辑器支持范围。`INCLUDE`/`PARAMETER` 不通过此工具创建。
- 库验证器和重读一致性都不是求解验证；某个关键字类可以检索，不代表其所有条件分支、材料物理或不同求解版本都已验证。

来源：[API reference](https://dyna.docs.pyansys.com/version/stable/api/index.html)、[核心库源码](https://github.com/ansys/pydyna/tree/v0.12.1/src/ansys/dyna/core/lib)。

## Examples：六个源文件逐项解析

已读取该 tag 的六个官方 Python 示例；没有直接运行它们的下载/求解/绘图顶层副作用。

| 官方示例 | 提炼的工作流 | 当前迁移状态 |
|---|---|---|
| Jupyter plotting | NODE/八节点 SOLID、截面、Deck/PyVista 预览 | 通用表格构造、原生方块网格及 LS-PrePost 预览可用；Jupyter/PyVista UI 未接入 |
| Beer can buckling | 隐式控制、Mortar 接触选项、节点载荷、约束表、输出 | 通用关键字构造覆盖数据形态；完整屈曲案例/接触验收未完成 |
| Pendulum | 壳/梁/刚体切换、重力曲线、初速、接触和 include 网格 | 卡片检索/构造/编辑已接入；完整摆锤流程未完成 |
| Pipe | 接触力传感、部件集合、角速度、刚体/可变形部件 | 通用接口可表达部分卡片；实体配置与完整算例未完成 |
| Plate thickness optimization | 厚度变化、求解循环、部件位移范围、目标判定 | 关键字字段修改可用；求解循环、DPF 和优化流程未实现 |
| Taylor bar | MAT_003、实体截面、初速、刚性墙、输出与参数扫描 | 通用关键字层已接入；完整撞击与参数扫描验收未完成 |

发现并避免照搬的问题：Pendulum/Pipe 中 `elfrom` 与实际 `elform` 属性不一致；部分 `run_post()` 为空；Beer can 示例捕获求解失败并继续，不能因此把运行完成当作收敛成功；网格下载、临时目录和资源参数都需要适配本项目的任务目录与结果合同。

来源：[官方 Examples](https://dyna.docs.pyansys.com/version/stable/examples/index.html)、[固定版本示例源码](https://github.com/ansys/pydyna/tree/v0.12.1/examples)。

## Contribute：可维护的扩展

已核对上游许可证、贡献说明、codegen 入口与测试规范。复用方式优先为固定依赖和独立适配器，避免复制数千个生成类后失去版本同步。上游代码采用 MIT；若后续直接移植实现，必须保留相应版权与许可证。

本仓库以合成数据做公开 CI，原生测试显式运行，私有模型和派生结果只留本地。新增适配应附字段/分支失败测试、序列化重读检查及相关原生验收。没有向上游发送 Issue、PR 或消息。

来源：[Contribute](https://dyna.docs.pyansys.com/version/stable/contributing.html)、[贡献文件](https://github.com/ansys/pydyna/blob/v0.12.1/CONTRIBUTING.md)。

## Changelog：版本迁移

重点核对 0.11 的旧模块移除和 AI instructions，以及 0.12 的 SECTION card-set、参数处理、默认值算法、表格卡/条件接触和求解失败行为变化。当前适配固定 0.12.1；升级时先对这些接口做差异与回归检查，再变更依赖。旧版本本地样例需逐项迁移，不能仅替换 import。

来源：[Changelog](https://dyna.docs.pyansys.com/version/stable/changelog.html)。

下一步仍是把上述完整案例与高级 API 分支逐项转成经过验证的工具和 Skill 流程；这份解析不将待实现内容记为已完成。
