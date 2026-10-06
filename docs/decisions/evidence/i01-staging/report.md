# I01 第三轮修复的批处理证据

实际 Git revision：`c5e599da28d09b2a8cd60e6b138fed1480d79c71`，工作树包含
尚未提交的 main 合并及本次修复。最终复测 r3i01n2 的 `git diff HEAD --binary`
SHA256 为 `777209691c8f1932dc31c76633361f733b8fa71d020055e9addcb109e940418c`，
在运行两版本前记录并在运行后核对。原始补丁和日志留本地；
[evidence.json](evidence.json) 的 review_runs 附版本、用例结果和报告哈希。

| 版本 | 通过 | 严格 xfail | 范围 |
|---|---:|---:|---|
| 4.13.4 | 3 | 2 | ASCII/空格 job 的 PNG、保存、重开；ASCII Include 读取及源目录不变 |
| 4.10.1 | 2 | 3 | ASCII/空格 job 的 PNG、保存、重开 |

缺口：两版中文 job 目录及中文 Include 根路径失败，4.10 相对 Include
仍从 job cwd 查找。Include 用例先断言源目录文件列表与字节不变，再按
确切诊断确认预期失败；其他异常仍失败。此轮没有 GUI 或 UU 验证。

首次实验 r3i01n1 的失败记录同时保留，diff SHA256 为
`27faec74ae35170f6412dd02fd9a60b49dfcea7841270074285f3af3e6cc0a4a`。
强制低暂存阈值的小型真实 d3plot 原地回退在两版均访问冲突；该回退
已移除，产品对超过 1000 文件或 2 GiB 的结果明确拒绝，并保留 I01 gap。
没有声称测试过实际 2 GiB 模型。

旧版 3595d11 和 p2/c991f9d 记录缺少当时的 diff 身份，不作为本次修复头
证据；其历史记录仍保留在 JSON 中。工作目录 `.` 仅供 BatchEngine 使用，
GUI/队列继续用绝对目录。
