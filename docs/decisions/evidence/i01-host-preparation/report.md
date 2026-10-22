# I01 宿主准备失败的终结与恢复（2026-10-23）

修复 P2-26b：`_before_submit` 抛出异常后，不会执行后续 transport.submit，
所以没有这个请求的原生 complete.json。原先 recover 永久报告等待原生回执。

现在异常路径写出独立的 host-preparation-failed.json，包含请求 job_id、
phase=host_preparation、dispatch_submitted=false 和非空 error。它是宿主失败记录，
不是原生成功回执，不创建或冒充 complete.json。

恢复时校验请求与记录的 job_id、原请求确有 host_preparation、失败阶段、
发送标志和 error。有效记录终结 active_request，记录 failed / replayed=false，
保留会话 uncertain（进程已退出则 exited）、关键词模型 dirty、旧可信检查点，
并明确 requires_host_validation。Apply 可能已发生部分副作用，不能因此判模型验证通过。

只有准备回调抛异常才写此记录。transport.submit 本身失败时，发送可能已到达原生进程，
继续保留 outstanding request 等待相关回执；不得把它误判为“尚未发送”。
宿主失败也不能被旁边一个成功 complete.json 提升为通过，恢复不会重放面板或命令。

## L1 回归

修正测试夹具的 bridge_protocol=4 后，main `2828cdb` 上反例为 **8 failed / 1 passed**；
通过项是必须保留的“发送可能已到达原生进程”路径。首次夹具版本在能力检查之前失败，
已更正并保留原日志，没有把夹具错误归为产品缺陷。

随后增加“无宿主准备的请求不可使用此记录”及“成功回执不能覆盖宿主失败”两项。

```text
python -m pytest tests/test_sessions_workflows.py tests/test_session_selection_identity.py tests/test_script_session_log_contract.py tests/test_engines.py tests/test_gui_mesh.py tests/test_gui_quality.py tests/test_gui_selection_renumber.py tests/test_gui_solid_quality.py -q
132 passed
```

覆盖空异常消息、存活/退出进程、记录错 ID/阶段/发送标志/错误消息、重复 recover 不重放，
旧检查点不前移，以及原生发送失败仍需等待的控制组。全为离线受控传输，不运行 GUI，
不新增原生 L2 声明；I01 保持 partial/L1，既有原生缺口保留。

P2-26c 同时补齐两个工具层离线用例：实际调用 renumber_gui_entities / check_gui_shell_quality、
_gui_mesh_edit、Sessions.dispatch 和 SessionEngine，仅替代初始快照与 Win32 传输边界。
在 Renumber 的 Apply 与质量面板准备处断言引擎正在运行、active_request 已登记、
request.host_preparation=true，然后故意中止。两例都产生关联的宿主失败记录和 uncertain
事务结果；不把受控传输等同于真实 GUI 验收。
