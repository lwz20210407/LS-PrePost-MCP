# I02：FieldSpec 语义适配层与等价测试报告

## 任务背景与边界说明

在 [tasks.yaml](../../../../tasks.yaml) 中，I02 登记的未完成缺口为：
> `M2：core.FieldSpec 与旧 field_contracts.FieldSpec 的适配层及等价测试尚未落地`

本任务在独立分支 `antigravity/I02-fieldspec-adapter` 上落地了双向适配层 `src/ls_prepost_mcp/field_contract_adapter.py`，并在 `tests/test_field_contract_adapter.py` 中实现了完整的等价性检验与负例守卫测试。

严格遵循所有权与隔离边界：
1. `src/ls_prepost_mcp/core/contracts.py` 与 `src/ls_prepost_mcp/field_contracts.py` 保持**严格只读**，未改动任何字段定义、默认值、校验逻辑或签名。
2. 现有基于 `field_contracts.FieldSpec` 的 7 个底层模块与服务入口均保持不动，不强行替换或扩大迁移范围。
3. 适配层置于顶层包模块 `ls_prepost_mcp.field_contract_adapter`，完全遵守 import-linter 架构分层守则（3 kept, 0 broken）。

## “同名不同义”核心语义对照

`core.contracts.FieldSpec` 与 `field_contracts.FieldSpec` 共享部分属性名（`backend`、`units`、`sampling`、`frame`、`averaging`、`validity`），但二者承担不同层次的工程语义：

| 维度 | `core.contracts.FieldSpec`（领域请求合同） | `field_contracts.FieldSpec`（执行与出处描述合同） |
|---|---|---|
| **定位** | 高层领域请求意图（声明式、面向用户/MCP 工具、解耦底层求解器） | 底层执行描述与结果出处（可执行字段键、绑定具体后端实现） |
| **字段键** | `quantity`（如 stress）与标准分量元组 `components`（如 xx, yy, zz） | 底层展开的具体字段名列表 `fields`（如 stress_x, element_shell_stress） |
| **实体选择** | 结构化选择器 `Selector`（支持代数、几何 Box/Sphere/Plane 与 PartSelection） | 明确具体的用户整数 ID 列表 `ResultSelection.entity_ids` |
| **时态/状态** | 离散状态 `StateIndices` 或物理时间 `PhysicalTime`（支持 nearest/exact 匹配） | 显式 1-based 整数状态元组 `ResultSelection.states` |
| **采样机制** | 判别联合 `Sampling`（NativeDefault, NativeLayer, NativePoint, StoredPoint, Unlayered） | `SamplingSpec`（绑定底层 SCL 命令选择器或 reader 存储切片，标明 cross_backend_equivalence="not_inferred"） |
| **坐标系/变换** | 枚举 `frame: global/material/local` 及 `coordinate_system_id` | 文本化描述 `frame` 及可选的 `transformations` 标签列表 |

## 关键不变性与严格隔离守则

适配层实现了以下关键物理语义与工程守则：

1. **跨后端采样绝不推断等价**：
   - 严禁将 reader 存储层号（如 LASSO 槽位 1）等同于原生层号（如 SCL 的 MID 或 1）。
   - 在 `assert_field_spec_equivalence` 与 `describe_field_spec_mapping` 中，强制核验 `cross_backend_equivalence == "not_inferred"`。
   - `lsprepost` 后端拒绝传入 `StoredPoint`；非 `lsprepost` 后端拒绝传入 `NativeLayer` / `NativePoint`。
2. **KI-049 原生实体积分点限制守卫**：
   - 针对 LS-PrePost 4.13 SCL 对实体单元积分点 2..8 会发生错误回退的问题，原生适配严格拦截并拒绝，不允许通过隐式转换伪造等价性。
3. **缺失上下文的显式拒绝**：
   - 当 `core.FieldSpec` 的 `Selector` 为几何选区（`BoxSelection`, `SphereSelection` 等）或非 ID 选区时，若未提供已解析的实体上下文 `resolved_entity_ids`，适配器抛出明确的 `ValueError`，说明缺失实体解析上下文。
   - 当 `core.FieldSpec.at` 为连续物理时间 `PhysicalTime` 时，若未提供离散状态映射 `resolved_states`，抛出明确的 `ValueError`，说明缺失时间状态解析上下文。
   - 对非全局域（如 node, shell），`NoSelection` 无法合法构造 `ResultSelection`，明确抛出错误拒绝。
4. **用户 ID 与状态无损保留**：
   - 用户整数 ID 与 1-based 状态数组按原有顺序完全保真传递，不进行浮点、布尔或字符串弱类型隐式强制转换。

## 验证与测试证据

在 `tests/test_field_contract_adapter.py` 中落地 18 项测试用例，覆盖：
- 壳单元原生层（inner, mid, outer）的双向适配与全字段映射。
- 实体单元原生默认采样及积分点 1 映射。
- 节点位移、速度、加速度等向量场量映射。
- LASSO / LSReader 存储积分点映射及出处描述。
- 局部坐标系及 `coordinate_system_id` 上下文保留。
- 跨后端采样等价推断拒绝。
- KI-049 实体单元积分点 2..8 的显式拦截。
- 缺失解析上下文（几何选区、物理时间、非全局空选区）的显式拒绝。
- 状态化 `FieldContractAdapter` 与外部解析回调。
- 双向往返转换与 `describe_field_spec_mapping` 审计字典结构完整性。

全套 18 项新测试及既有 57 项合同测试全部通过。
