# I04 原生历史证据附件

历史 I04 记录：三个 file 验收不启动 LSPP；program_acceptance.batch 为真实 LSPP 批处理程序验收。原始报告未记录 Git revision，仅附原始文件 SHA256，不写成当前 PR 头重跑。

本附件从已有本机记录提取，没有新增原生运行。原始路径、原生日志正文和私有数据不入库。

| 日志 | 原记录摘要 |
|---|---|
| i04-native-program.log | 1 passed, 56 deselected in 126.55s (0:02:06) |

| 来源组 | 用例 | 当时报告状态 |
|---|---|---|
| i04-file-acceptance-2 | tests/test_native_acceptance.py::test_legacy_acceptance[engineering_unit_acceptance.file] | passed |
| i04-file-acceptance-2 | tests/test_native_acceptance.py::test_legacy_acceptance[parameter_study_acceptance.file] | passed |
| i04-file-acceptance-2 | tests/test_native_acceptance.py::test_legacy_acceptance[workflow_gate_acceptance.file] | passed |
| i04-native-program | tests/test_native_acceptance.py::test_legacy_acceptance[program_acceptance.batch] | passed |

[证据 JSON](evidence.json) 保存 185 个原文件的相对标识、字节数和 SHA256，以及可提取的状态/计数。

这些历史用例不证明公开 Win32 路径、全部 GUI 验收或未执行的 UU 格已通过；任务缺口仍以 tasks.yaml 为准。
