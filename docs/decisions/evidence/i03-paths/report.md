# I03-paths 原生历史证据附件

PR #4 路径构建器修复工作树的实测：4.13.4/4.10.1 各一项通过、两项严格 xfail。通过项为 ASCII job 目录中的中文/空格输入文件名；工作目录本身含空格或中文的失败保留为 KI-049。不是 GUI/Movie 通过证据。

本附件从已有本机记录提取，没有新增原生运行。原始路径、原生日志正文和私有数据不入库。

| 日志 | 原记录摘要 |
|---|---|
| review-pr4-path-4.13-final.log | 1 passed, 7 deselected, 2 xfailed in 45.68s |
| review-pr4-path-4.10-final.log | 1 passed, 7 deselected, 2 xfailed in 58.28s |

[证据 JSON](evidence.json) 保存 96 个原文件的相对标识、字节数和 SHA256，以及可提取的状态/计数。

这些历史用例不证明公开 Win32 路径、全部 GUI 验收或未执行的 UU 格已通过；任务缺口仍以 tasks.yaml 为准。
