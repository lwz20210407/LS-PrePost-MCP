# I04：原生报告自动绑定执行版本

2026-10-06，框架报告现在直接包含启动时的实际 Git revision、工作树 dirty 状态、
`git diff HEAD --binary` SHA256 和源码快照 SHA256。详细逐文件指纹仍在外部
execution-context.json；单独取出 report.md / report.json 时也能识别对应版本。

[原生冒烟证据](evidence.json)：LS-PrePost 4.13 的 Service 后台读取用例 1 passed。
实际 revision 为 `de9abceb80a7602febdffeaaefda03e636cdaa90`，工作树有未提交修改，
diff SHA256 为 `a57ce2b36ed9d39f1230d1a0a9b0083edf78d7ea7920f3a12ed726fe0fc6079c`。
首轮因错误的相对 fixture 参数在原生启动前失败；改为绝对路径后通过，首轮状态也保留。
通过轮次退出时产生 pytest cache 目录创建权限警告，不影响原生作业和报告落盘。

离线回归覆盖 staged + unstaged 合并 diff、未跟踪源码指纹、嵌套非 checkout、
Git 超时，以及 remote evidence_only 在报告中继续保留各通道失败状态。
该冒烟只验证报告绑定和模型读取；I04 保持 partial，GUI/UU 矩阵仍待补测。

Git 不可用时字段明确为空，不猜测 PR 头。diff 不含 untracked 文件，因此同时记录
源码快照；报告中的身份是启动时快照，不是对运行期间外部修改的监控。

## 第六轮复核：可复算范围

历史 a57ce2b… 补丁只含当时已跟踪的修改；新测试 test_native_evidence_identity.py
当时未跟踪，只有 source_files 记录其指纹。可复算命令：

```powershell
git diff --diff-filter=M de9abce fb701f2 --binary -- . ':!docs' ':!tasks.yaml'
```

本轮开始，框架明确固定 quotepath、前缀、颜色、diff 算法、重命名和外部转换选项，
在仓库外报告目录保存原始 working-tree.patch。execution-context.json 和 report.json
记录完整命令、HEAD 基线及范围：包含所有已跟踪 staged/unstaged 修改，无路径排除；
未跟踪源码只计入 source_files。私有路径可能出现在补丁里，补丁不提交仓库。
Git 不可用的源码副本仍生成报告，revision/diff 显示 unavailable。
