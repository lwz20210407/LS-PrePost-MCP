# I04：托管 CI 不可用期间的本地合并关卡

日期：2026-10-06。状态：用户已批准，临时有效。

GitHub Actions 额度恢复前，使用同一待合并提交的本地完整检查作为合并关卡：

- 最小依赖和全依赖 pytest；
- Ruff、lint-imports；
- validate_tasks、gen_docs --check、validate_tool_migration、fetch_corpus --check-registry、check_doc_links。

PR 中登记实际提交号及检查结果，保留审阅和原生证据要求；未执行的托管 CI 仍标为待验证，不写成通过。需要桌面或远程窗口的原生用例仍须单独获得窗口并实测，单元测试不能替代。Draft 和未解决的审阅问题不会因本决定自动解除。

额度恢复后再恢复托管 CI 关卡并补测；期间不重复触发已确认因额度不足而被拒绝的运行。本决定不改变 tasks.yaml 的功能范围、任务状态或里程碑验收标准。
