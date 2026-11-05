# P03：MCP迁移元数据后的真实主机来源刷新

本轮仍是 **P03 partial/L1/no native**。实际clean `7fb814cf0575b0bb5c55a2ee419d33ff9732e780` 上，原四专属文件60/60通过，含full/compact stdio两个配方调用；source before/after稳定。没有把旧02b或typed-write1ba运行换成新revision。

| 上下文 | 实际验证 | 有效性 |
|---|---|---|
| 原02b | 原主机60项及首次wheel/98题检索 | 历史对象原样保留 |
| typed-write1ba | 新后台deck后的60项及wheel778549B | 历史对象原样保留 |
| 当前7fb | 原四文件60项、新wheel778992B、提取目录真实执行source-doc pin；迁移入口另31项有重叠控制 | 当前登记产品来源有效；不累计成native样本 |

新wheel SHA256为 `5ddcaba7d2f0202a163ada3c4f4d3123fa932e2501fcdbcaa2f074c56f5c38ca`。仅offline构建、解压，不向共享环境安装。新Python进程核provider/Service/registry/server/compact均确实来自提取目录；九候选存在，source-document产生的pin实际创建Elastic成功，keyword/backend与native=false保持，输入字节不变，full迁移元数据及compact describe也实际核对。

来源口径明确分开：原producer/capture/wheelproof显式选择的21项及其SHA原样保留。收编时另从**同次真实7fb完整before/after source_files**归档已测 operations.json：raw before/after一致，Git7fb/current对象一致，原immutable wheel对应成员原字节/规范LF匹配。总归档为 **explicit21 + archived data1 = 22**，标 `post_capture_archival_from_actual_full_snapshot`；没有把后测伪作当时测量，没有换revision或再跑60。22个来源身份也不代表这些模块每个功能都测过。

原 [P03初次上下文](../p03-model-recipes/report.md)、[typed-write上下文](../p03-typed-writes-refresh/report.md) 和所有A10对象原字节保持，current指针仅选择本新文件。原11个检索产品Git blob未变；source-doc pin互认只调用同一来源生成逻辑，不是从已回收SQLite查询。没有重建索引、重放原98题、修改题目/答案/排名或增加私有来源。

运行命令为 `python -B -m pytest tests/test_model_recipes.py tests/test_model_recipe_knowledge.py tests/test_model_recipe_pins.py tests/test_model_recipes_mcp.py -q -p no:cacheprovider --junitxml <外部输出> --basetemp <新外部目录>`。使用显式worktree src/root PYTHONPATH及已有D共享环境；wheel为 `uv build --offline --wheel --python <已有解释器> --out-dir <外部目录>`，复用D cache，未建新环境。

原生Part Data ID/字段/关联回读及材料物理校准仍未完成，本轮不运行LSPP/solver/GUI，不改变P03验收、release或完成状态。内部根复核不充当用户安排的独立外审。实际source/test/wheel/归档与历史对象身份见 [evidence.json](evidence.json)。
