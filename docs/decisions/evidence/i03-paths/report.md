# I03 剩余路径构建与 SCL 编码回归

16 处调用（10 个模块）迁入 import_keyword、open_xydata、save_xypair、
modelcheck_report；SCL 写入使用同一 UTF-8、LF、无 BOM 写入器；合入新 main
后新增的 selection.scl 写入也已迁入，共十处。
保留嵌入式 Python 3.6 语法，AST 守卫阻止在业务模块重新拼接这些命令。

4.13.4 与 4.10.1 各三项后台原生用例通过：

- 导入节点后保存、重开，独立核对新增节点 ID 1001 及坐标 (7,8,9)。
- XY 数据读入与导出，逐项比较三个曲线点。
- UTF-8 中文注释和 CRLF 输入经 SCL 写入器后，以原生执行结果确认节点计数。

实际 revision 与运行时 git diff SHA256 见 [evidence.json](evidence.json)。
原始补丁和原生日志保留在外部 i03paths-n1；未运行 GUI/UU。
GUI 模型检查等调用的命令字符串回归已覆盖，窗口内原生复核仍为 I03 gap。

合入 main 9e55e9b 后再次运行相同后台用例，两版仍各三项通过。
实际 HEAD 为 07ea5794d2a7178e069e45fd3816f5debaf1a666，带未提交合并，
diff SHA256 为 87e67606a8f2ba4dc90d35f5f31f8d6c3c3e4c0aa1a3d5adf591078e0e0449bc；
新增记录位于 evidence.json 的 review_runs，既有 96 条记录不变。

---

# I03-paths 原生历史证据附件

PR #4 路径构建器修复工作树的实测：4.13.4/4.10.1 各一项通过、两项严格 xfail。通过项为 ASCII job 目录中的中文/空格输入文件名；工作目录本身含空格或中文的失败保留为 KI-049。不是 GUI/Movie 通过证据。

本附件从已有本机记录提取，没有新增原生运行。原始路径、原生日志正文和私有数据不入库。

| 日志 | 原记录摘要 |
|---|---|
| review-pr4-path-4.13-final.log | 1 passed, 7 deselected, 2 xfailed in 45.68s |
| review-pr4-path-4.10-final.log | 1 passed, 7 deselected, 2 xfailed in 58.28s |

[证据 JSON](evidence.json) 保存 96 个原文件的相对标识、字节数和 SHA256，以及可提取的状态/计数。

这些历史用例不证明公开 Win32 路径、全部 GUI 验收或未执行的 UU 格已通过；任务缺口仍以 tasks.yaml 为准。
