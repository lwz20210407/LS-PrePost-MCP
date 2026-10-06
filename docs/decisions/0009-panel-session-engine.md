# I01：面板操作进入会话引擎

日期：2026-10-06。状态：实现与离线回归已就绪，原生验收待授权窗口；I01 保持 partial。

重编号和质量检查此前在 SessionEngine 捕获日志、登记请求之前操作 Win32 面板。
控件操作抛错时，可能已经改变模型，却没有对应的引擎结果。

现在 Sessions.dispatch 的内部准备回调在 SessionEngine 的 submit 阶段执行：
先建立独立请求、登记 active_request、捕获日志，再执行面板操作与原生 cfile。
完成仍依靠原生 complete.json、任务 ID 和已有领域校验。回调抛错时保留 unverified
及待核对请求，不重发点击，不生成成功回执，不启动后台实例。

重编号的面板/选择阶段与应用阶段各有自己的关联请求；壳/实体质量检查的面板设置
进入对应检查请求。读取控件值、核对拓扑/坐标/映射、保存重开等领域校验继续保留。
队列会话在这些工具进行快照、检查点或选择变更之前明确拒绝面板操作。
内部回调不暴露为 MCP 参数，不新增按钮级工具，不改变 I02 合同或 run_recipe 签名。

## 集中待测清单

以下 6 项均未实测，使用自产模型，LS-PrePost 4.13，可见桌面保持解锁约 20 分钟。
每项覆盖启动、打开、操作验证、关联 engine-result.json、保存重开、PNG 与关闭，
并检查原始输入字节不变。

| 用例 | 状态 |
|---|---|
| 节点重编号 | pending |
| 壳单元重编号 | pending |
| 部件重编号 | pending |
| 原生 Keyword Check | pending |
| 壳质量检查 | pending |
| Hex8 实体质量及失败单元 ID 捕获 | pending |

入口：[test_public_panel_actions_have_correlated_engine_evidence](../../tests/test_engine_native.py)。
运行必须同时有 `--run-native --native-gui`、`LSPP_ALLOW_GUI=1` 和用户授权窗口；
此批不需要 UU 断开。通过后另附真实 revision/diff 指纹证据，不能用离线测试代替。
