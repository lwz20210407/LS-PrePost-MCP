# I01：五个批处理入口的 JobResult 回归

2026-10-06，本机 LS-PrePost 4.13 和 4.10 后台运行，各 6 项通过。
执行的是同一份工作树：Git revision `cb5b7691827e3602db5d17459cc6926ccc7d33a7`，含未提交修改；
`git diff HEAD --binary` SHA256 为 `382ec476adfecef0e966a14c2e4439d4413549196ba77344bb9e0754e5675b6d`。
逐项状态、原始报告 SHA256 和实际源码 SHA256 见 [evidence.json](evidence.json)。

| 实测路径 | 4.13 | 4.10 |
|---|---|---|
| Service：读取模型、8 节点计数 | passed | passed |
| SCL inventory：模型计数 | passed | passed |
| Native results：节点场数据导出 | passed | passed |
| Native batch：场量、应力数学、媒体产物检查 | passed | passed |
| Native programs：命令执行与声明的模型计数 | passed | passed |
| 无效命令、进程退出码 0：仍返回 failed 并保留真实诊断 | passed | passed |

五个入口都核对 `engine-result.json` 的 JobResult/v1、任务 ID、操作名与返回清单一致，
引擎状态为 unverified；只有原有领域校验完成后，外部结果才可成功。
测试 fixture 在运行前后核对目录中文件的 SHA256。旧输出格式的 process 字段继续兼容，
内部决策不再读取它的 returncode/timed_out/engine_status。测试使用项目自产小模型，
本次未新增公开案例覆盖，也未测试 GUI、队列或 UU 断开。

复现：配置本机安装路径和自产 fixture 后运行：

```powershell
python -m pytest tests/test_engine_native.py -q -k "five_batch_callers or native_diagnostic_is_visible" --run-native --native-strict --native-executable $exe --native-fixture $fixture --native-output $evidence --basetemp=$scratch
```

I01 保持 partial/L1：重编号与质量检查面板尚未统一，大结果族和 Include 路径限制保留。
