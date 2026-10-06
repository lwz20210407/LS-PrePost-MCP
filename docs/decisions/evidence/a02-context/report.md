# A02：保存后会话来源核验

历史原生运行：2026-10-06 03:59（北京时间），LS-PrePost 4.13.4 可见会话。
`program_bundle_acceptance.native` 通过，耗时 32.27 秒；覆盖嵌套 cfile
建模、单命令保存、SCL/Python 依赖包及录制回放。原始报告位于外部 g6 目录。

实际运行 Git revision 为 `dc9dbc197c013221eeacbb8652602442676b9ba3`，
带未提交的集成修复（含本次 gui_programs 上下文修复）。该次没有记录
完整工作区补丁哈希，因此这是历史集成证据，不是本 PR 提交头的原生验证。
源脚本、验收输出和报告哈希见 [evidence.json](evidence.json)。

本次离线回归直接调用 execute_prepared，核对真实产物内容和原生回读
来源判定：允许空 keyword 会话建模、声明输出的单命令另存为；拒绝
外部来源、产物缺失或损坏、多 keyword 输出、计数不符、结果会话及
未显式授权的已有模型 cfile 上下文替换。失败时保留原来源并标记 uncertain。
这些回归使用模拟的会话传输，不替代原生验证。本轮未启动 GUI。
