# P02/I07：named numeric 写入准入与内存原子性

本修复只在已有 `FieldInfo.kind` 的 named setter 校验数值，并把新行标识的验证前移；不重新解码关键字、不改布局、provider、物理公式或任务验收。P02仍partial。

旧 main `dba51d0` 上，`edit_keywords` 将 Part.mid 的字符串 `"1.5"`、`"NaN"` 写入并返回 succeeded；引用扫描不能代替字段类型准入。直接 setter 的空行 ID 还会在修改内存后才抛 ValueError。

实现提交 `eeff496c168cf5f02afee66e76bb97adc5d2744f`：整数字段复用 `exact_integer`，浮点文本沿用既有 `parse_number`，参数沿用 `resolve_field`；全部校验在修改前发生。
整数文本要求可选符号和ASCII数字；小数/科学记法的**字符串**不作为整数字面量接受。整数值的数值标量（如JSON数字2.0）、signed/前导零整数文本及求值为整数的参数保持支持。浮点字段保留Fortran D/隐含指数与有限实数标量；布尔、数组、复数和非有限值拒绝。普通空白默认值、文本标题和API控制标志保持原路径。

| 检查 | 实际结果 | 范围与有效性 |
|---|---|---|
| 旧dba51，仓库外新测试 | 23 failed / 22 passed | 有效夹具；包含准入收紧策略、旧有合法控制和原子性断言，不是23个独立缺陷 |
| 新typed-write首轮 | 45 passed | WIP初测后Ruff整理了import顺序；此轮不冒称逐字节等于eeff，clean45后来包含在peer56中 |
| 完整有限模型 | 601 passed / 1 skipped | 源实现WIP；其中旧active门禁仍对父HEAD，不当作新源码证据 |
| clean eeff内部有限peer | 56 passed | 45已有+11独立控制；不是独立外审或原生数量 |
| clean eeff公共标题oracle | 15 passed / 3 capture | 16个Part；非native；8产品blob在组合1246源相同 |
| clean组合1246 | 254 passed；三装配离线通过 | 继承P12 be0和main15921；1/11/4 Joint，仅host创建/检查，无新native |

各命令重叠，不累加为覆盖数。初版单元夹具遗漏Part的row参数产生的35失败日志，以及最初T1探针误用fields字典产生的KeyError，明确作废；都不作为代码缺陷或有效红例。

本修复也有明确行为收紧：过去raw字符串绕过类型检查的表示不再由named整数setter接受。未被本次typed入口覆盖的未知布局或显式raw操作，不据此声称已作完整语义验证。

当前新源P11/P12/P04原生来源刷新仍待完成，旧捕获保留原revision，不重绑为新代码。完成新的实际运行、七项检查和精确PR头五项CI后才能集成；没有升级任何任务为done。
