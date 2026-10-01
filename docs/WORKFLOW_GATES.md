# 工作流执行结果与质量门槛

本批对应顶层设计 T01 的 OperationResult 部分、T02 与 A05。模型/SelectionSpec/FieldSpec/单位合同的统一仍未完成。本页描述已经实现的工作流行为。

## 执行和检查分开

原生检查发现错误，仍可能返回 `status=succeeded`，因为软件确实完成了检查。工作流现在保留这份原始结果，并单独生成 `OperationOutcome` 与门槛报告。

| 信息 | 含义 |
|---|---|
| `execution_status` / `execution_accepted` | 是否完成该工具规定的执行阶段；准备程序只能接受 `prepared`，一般工具必须 `succeeded` |
| `stage` | preparation 或 execution；准备好脚本不等于已执行脚本 |
| `check_status` | passed、failed、not_applicable、missing、invalid 或 not_reported |
| `check_path` | 实际读取的检查结论字段；没有结论不能猜成通过 |
| `backend` / `scope` | 保留操作自己报告的后端与范围；缺失时为 null，不凭工具名猜测 |

默认自动门槛覆盖：原生壳质量、原生 Keyword Check、GUI 网格几何质量、文件网格几何质量、PyDYNA 引用检查。只有明确的布尔 `true` 通过；`false`、`null`、缺失或字符串/数字冒充布尔均停止。其他工具默认只检查其执行状态，需要工程阈值时添加显式 checks。

## 每一步的质量策略

`quality_policy` 默认为 `auto`，旧 schema 1 配方也采用该行为。这是有意收紧：过去被忽略的不合格检查，现在会停止旧配方。

- `auto`：上述已映射检查工具必须通过；普通操作不能由“未报告质量”推断物理有效。
- `require_pass`：必须有已映射且通过的检查结论，否则停止。
- `report_only`：允许该步骤保留不合格/不适用的检查发现，继续收集报告；**不绕过执行失败，也不绕过显式 checks**。

例如 Keyword Check 有意保留未引用集合时，可设置 `report_only`，再用显式阈值控制 error、undefine、warning、unref 的允许值。不能为了跑完流程自动添加这个策略。

## 显式 checks

```json
{
  "id": "keyword_check",
  "action": "check_gui_keywords",
  "arguments": {},
  "quality_policy": "report_only",
  "checks": [
    {"path": ["verification", "totals", "error"], "operator": "eq", "value": 0},
    {"path": ["verification", "totals", "warning"], "operator": "le", "value": {"$param": "max_warnings"}}
  ]
}
```

每个 path 指向**当前步骤**的原始结果，使用字符串键或非负数组索引。支持 `eq/ne/lt/le/gt/ge` 及无 value 的 `is_true/is_false/is_null/not_null`。比较值为有限 JSON 标量，可用 `$param`；没有 eval/Python 表达式。最多 32 条条件、路径最多 16 层。

缺失字段不等于 null；数值比较不把布尔值当作 0/1；字符串不自动转换为数字；NaN/Infinity 不通过。所有条件阈值先解析、检查，再打开初始模型或执行第一个操作。

已有 `parameterize_workflow` 增加可选 `section="checks"`，例如 `path=[0,"value"]` 参数化第一条检查的阈值；默认仍为 arguments。原来的参数调用方式保持兼容。

## 失败证据与恢复边界

无论成功还是停止，都保存 `steps.json`（原始结果）、`outcomes.json`（统一执行/检查语义）、`gates.json`（策略、实际值、比较值与失败原因）。失败结果包含：

- `completed_steps`：已经完成且门槛通过的步骤；不再把失败步骤计入完成数。
- `attempted_steps`、`failed_step`、`failure_phase`、`skipped_steps`。
- 已返回的 `baseline_checkpoints` 及原始报告/产物路径。

工作流不会自动重放、自动回滚、删除报告或改写原检查结果。工具抛出异常、返回缺失/未知状态或非法 JSON 时保留可读取的失败记录，并停止后续步骤。完整断点续跑与状态恢复仍属于后续工作。

## 可复用配方与验证

- [可见 GUI 检查后保存](../examples/workflows/visible_gui_quality_gate.json)：原生壳质量→Keyword Check→检查点。需用户给定单位与质量阈值；未重新声称本批做过完整 GUI 验收。
- [能量筛查后输出指定能量之和](../examples/workflows/energy_screening_gate.json)：检查定义行、未定义比例、超限、HG 是否提供，再组合已提供的 KE/IE/HG。这不是完整能量守恒或准静态认证。

可复现的文件后端验收：

```shell
python tools/run_workflow_gate_acceptance.py --workspace <explicit-task-output-directory>
```

脚本只创建新的合成数据，使用真实 PyDYNA/几何检查与曲线计算，不启动 LS-PrePost。已通过五种结果：好网格继续编辑；退化网格阻止编辑；正常能量继续；KE/IE 超限停止；IE 为零导致未定义比值时停止。原输入不改写。原生结果结构的门槛行为另有隔离测试；本轮新 GUI 端到端验收仍待补，不能用逻辑测试代替。

2026-10-01 本批 142 项自动测试通过；sdist/wheel 构建成功，wheel 在独立环境安装后通过真实 MCP stdio 工具发现、合法配方创建和非法断言拒绝检查。构建出的 0.4.0 开发包不等于正式版本发布；三条主流程的剩余退出标准仍需完成。
