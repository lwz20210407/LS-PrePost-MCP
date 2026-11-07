# G04 keyword 三角壳实体识别

状态：partial / L1。当前有效范围仅为此处记录的主机代码与测试；不是新的 LSPP 原生对照。

`query_entities` 曾把合法 Tri3 的第四连接槽 `0` 或空白当成真实缺失节点，导致单元与 Part 查询失败。现在只在 keyword 路线复用共享几何规则，输出四槽连接，第四槽重复第三节点，并在 Tri3 行注明 `connectivity_representation` 是规范化表示而非原卡片。源卡片与 Include 树字节不变。四边形与 d3plot 路线不改。

独立手写预期：节点 11=(0,0,0)、22=(3,0,0)、33=(0,3,0)，单元 41 属于 Part 7 / Section 2 / Material 3；四槽应为 `[11,22,33,33]`，Part 节点数为 3，包围盒为 `[[0,0,0],[3,3,0]]`。真实 N1–N3 缺失或非零 N4=99 仍失败。

| 运行 | 实际 revision / 状态 | 结果 | 当前有效 / 已被取代 |
|---|---|---|---|
| 修前基线 | 2911adeec75a1f504976d66f8a7bdd999ca29d3a / clean | 同一测试文件选定27项：8失败、19通过；新增metadata3项与SDK缺席1项明确未选 | 保留：真实缺陷基线，不是当前通过证据 |
| 作者WIP | 2911adeec75a1f504976d66f8a7bdd999ca29d3a / dirty | 46通过、1跳过；完整source文件与后续65db提交相同，仅测后测量 | 已被取代：当前通过依据为下一行的干净重验 |
| 干净提交重验 | 65db8315240e5e953bd4f5b4117de3c364e14410 / clean | 46通过、1跳过，紧邻前后source身份完全相同 | 当前有效：记录产品blob范围内的主机合同 |
| SDK缺席模拟 | 作者WIP，同字节产品 | 1通过、30明确跳过；真实请求返回Unsupported且data为空，无Ansys模块加载 | 当前有效：有限依赖控制，不是完整最小依赖环境 |

干净重验命令（使用项目锁定的 Python 3.11，并显式设置本工作树 `src` 和根目录为 `PYTHONPATH`）：

```text
python -B -m pytest tests/test_entity_keyword_triangles.py tests/test_entity_query.py tests/test_entity_sparse_index.py -q --basetemp <outside-checkout>/pytest -o cache_dir=<outside-checkout>/cache --junitxml=<outside-checkout>/junit.xml
```

新增测试逐例禁止 `Service._native` 派发并确认零调用；无原生、GUI、求解器或性能运行。历史 G04 / I01 / Q05 原生记录保留其实际旧 revision，不因此变成当前全覆盖证据。BEAM/TSHELL、完整结果 Selector、材料映射等验收仍有缺口；任务不改为 done。报告与 JSON 已随仓库保存，私有日志只保留摘要哈希，不发布本机路径或语料。

测试：[独立三角形回归](../../../../tests/test_entity_keyword_triangles.py)；实现：[实体识别](../../../../src/ls_prepost_mcp/entity_query.py)。
