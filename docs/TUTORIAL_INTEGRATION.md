# 图文、代码、视频到可执行功能

检索不只限手册。来源按“发现 → 阅读/观看 → 原生复现 → MCP/Skill → 回归”推进；只找到链接不能登记为已吸收。软件版本、参数、选择范围、输出含义和失败条件都需要复核。公开视频和厂商样例不复制到本仓库；第三方代码未确认许可前仅作接口参考。

| 来源 | 形式 | 本轮实际进度 | 对应开发 |
|---|---|---|---|
| [官方 Mini/Extended/Animated Tutorials](https://lsdyna.ansys.com/knowledge-base/ls-prepost/tutorials/) | 图文与演示 | 分类入口已核对，按模块选取具体案例 | Mesh、Element Tools、Post 验收池 |
| [官方入门与显式/隐式教程集](https://lsdyna.ansys.com/introduction-ls-dyna-ls-prepost-for-explicit-and-implicit-analysis/) | 工况教程 | 目录已核对，尚未全部复现 | 拉伸、冲击盒、预紧等完整流程 |
| [原作者 Entity Selection Tips](https://www.youtube.com/watch?v=VcBN-EtX-nc) / [作者页面](https://unpopmechanics.com/ls-prepost-tutorial-selection-tips/) | 视频 | 读取全程字幕并检查 12 个时间点画面；尚未全部在 4.13 复现 | 传播、路径、邻近选择、缓存、集合 |
| [AISOL 基础教学合集](https://www.bilibili.com/video/BV1kg8WzZENv/) | 中文视频 | 已找到课程章节，尚未逐段观看 | 网格编辑、模型修补与 Post |
| [官方 XYPlot Mini Tutorial](https://lsdyna.ansys.com/mini-tutorial-page-1-xyplot/) | 图文 | 已读具体交叉绘图步骤 | 原生曲线窗口交叉图、方向/轴控制 |
| [LS-OPT 支持站的 LS-PrePost 参数化](https://www.lsoptsupport.com/examples/lsopt2010/howtos/integrating-pre-processor/ls-prepost) | 图文与 cfile | 已读参数文件、圆柱网格及输出示例 | 原生参数命令/包含文件；圆柱网格 |
| [yannikmayerm/FE-Simulations](https://github.com/yannikmayerm/FE-Simulations) | cfile | 读取指定旋转/重编号片段；未声明许可，不复制源码 | 对照 renumber 语法和版本相关编号 |
| [runtosolve/LSDYNA.jl](https://github.com/runtosolve/LSDYNA.jl) | 代码与 cfile 测试 | 读取 extrusion 测试中的命令片段 | 拉伸/合并操作参考 |
| [UMAT_2scale_LSDYNA](https://github.com/DataAnalyticsEngineering/UMAT_2scale_LSDYNA) | Python/SCL/cfile | 读取模型生成工具的选择与集合片段；许可需逐文件确认 | 区域选择、节点/面集合 |

## 已审阅的视频片段如何落到开发

原作者视频使用较旧 LS-PrePost；不能照搬其控件坐标或模型限定编号。1:50–3:40 的字幕和画面说明传播选择需要明确目标实体及角度，平面与曲面案例应分别验收；3:40–4:28 展示路径选择；4:28–5:45 的邻近选择还会涉及参照部件，必须核对最终选区；5:45–6:25 展示缓存保存/加载；后续展示节点与面集合的创建、修改。这些均已加入选择模块任务，尚不等于全部完成。

视频画面来自可公开访问的同源转载，字幕来自原视频，时长均约 8:30；证据与转录只留本地。公开说明引用原作者链接，且区分讲解与画面证据。

## 覆盖的组织方式

优先五个主模块：选择工具、Model、Mesh、Element Tools、Post。逐项登记子面板、操作与选项、所需输入、原生命令/接口、MCP 工具、版本、成功/失败验收。相同 Node Edit/Element Edit 从不同菜单进入时记录导航别名，不重复计算功能数量。几何建模及从几何划网格仍按用户要求后排。
