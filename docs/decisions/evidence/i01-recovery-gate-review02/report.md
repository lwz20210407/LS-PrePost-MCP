# I01 review02 恢复响应门槛（待原生窗口）

本项只有离线验证，不是原生通过；PR 在补验前保持 Draft，I01 保持 partial/L1。

宿主准备异常不证明先前 Apply 已结束。恢复前检查拥有进程的输入桌面、窗口启用状态，
发送无命令语义的 WM_NULL（2秒有界），再检查同一拥有窗口和进程身份。
失败或不确定保留 active_request 和检查点，不派发回读、不重放 Apply。
响应成功仅允许终止这个未派发请求；模型仍 uncertain/dirty，requires_host_validation=true。
已退出进程不接触 Win32。最新 recovery-probe.json 每次覆盖本任务旧探测记录，
避免 busy→重试成功后仍显示过时的 blocked；原始宿主失败记录保持不变。

## 证据边界

[evidence.json](evidence.json) 登记 L1 命令、干净提交及产品身份。
新增回归在原始 0563045 和修复前主干复现；ctypes 替身只验证只读消息与窗口响应合同。
不以这些替身证明 Win32 的实际时序、忙碌 Apply 或后台模型线程的静止状态。

| 测试 | 状态 | 有效性 |
|---|---|---|
| 未确认响应时保留请求、可重试、不重放、进程身份重核 | 离线测试 | L1 |
| WM_NULL 只读消息、超时/禁用/窗口变化 | ctypes 替身 | L1 |
| tests/test_recovery_probe_native.py | 已准备，未运行 | 待 GUI 窗口 |
| 真正忙碌 Apply / 后台变更竞态 | 未验证 | 明确 gap |

待用户安排窗口后，在干净头执行（分别指定4.13/4.10可执行文件）：

```powershell
$env:LSPP_ALLOW_GUI='1'
$env:LSPP_ENGINE_EXECUTABLE='<selected executable>'
python -m pytest tests/test_recovery_probe_native.py -m native --run-native --native-strict --native-gui --native-output '<external scratch>/i01-recovery-gui'
```

只启动并关闭该测试拥有的 GUI；正常打开后做响应探测，再注入不发送 Apply 的宿主异常，
检查真实会话恢复路径仍 uncertain。本用例即使通过，也不认证后台 Apply 已停止。
