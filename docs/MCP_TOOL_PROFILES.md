# MCP 工具暴露模式

默认 `LSPP_TOOL_PROFILE=full` 保持既有 MCP/CLI 接口。配置 `LSPP_TOOL_PROFILE=compact` 并重启 MCP 服务后，仅暴露：

1. `lspp_find_operations(query, domain, offset, limit)`：按现有模块/文字分页发现操作，不一次发送全部参数定义。
2. `lspp_describe_operation(operation, execution, session_id)`：返回选定操作的严格 JSON Schema 和明确路由。
3. `lspp_run_operation(operation, arguments, execution, session_id, preview)`：拒绝未知参数/类型错误，调用原来的操作及结果合同。

两种模式连接同一个 Service，实现能力没有增加或减少。工具发现不证明原生版本支持。对所有底层动作仍应查看 `list_capabilities`；精简模式可通过 `lspp_run_operation` 的 `direct` 执行该知识查询。

`execution="direct"` 明确选择原操作，包括文件/读取器/数学处理或会话生命周期；生命周期操作的 `session_id` 放在其自身 `arguments` 中。`execution="gui"` 指定当前受管会话，复用工作流路由；原生动作的模型路径由会话提供，调用者不得再塞入另一个模型路径。会话不存在、已退出、未就绪或请求未完成时拒绝，不自动切到后台新实例。无法在 GUI 路由使用的动作必须明确选择其实际后端。

示例：

```json
{"operation":"create_shell_plate","execution":"gui","session_id":"<owned-session>","arguments":{"nx":10,"ny":10,"size":[20.0,20.0],"units":"mm"},"preview":true}
```

`preview=true` 只验证组合/参数 schema，不启动软件，不确认原生支持、数值语义或模型状态。不应把 `status=planned` 当作完成。真正执行仍受原工具的版本、类型、规模及工程检查约束。

精简模式用按需 schema 避免首次暴露全量描述，代价是通常增加发现/描述调用。旧工作流与原子工具名称保留；不强制将调用者迁移到新的 16 个名称。完整/精简模式的 stdio 发现、知识查询、非法参数拒绝和 GUI 无隐式 fallback 都有回归覆盖。实际 LLM 任务选择准确率尚未建立评测，不给出虚构提升比例。

在 `9685513` 基线用同一 `model_dump` + `json.dumps` 序列化测得：full 为 127 个工具、81,290 字节；compact 为 3 个工具、2,086 字节。该比较只覆盖当时的首次工具列表，后续参数扩展或按需返回的 schema 会改变实际大小；不是 tokenizer 测量或调用准确率指标。
