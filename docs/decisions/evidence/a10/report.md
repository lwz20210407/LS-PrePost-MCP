# A10 独立留出评测与旧调优集记录

第三轮删除按旧题面定制的九条查询扩展后，冻结的新留出集为 24 题，
覆盖六类且每类四题，前 3 条命中 **12/24**。没有根据本次结果调整词表、
排序、索引内容或预期答案；A10 保持 partial，旧 20/20 不再作为完成依据。

| 类别 | 前 3 条命中 |
|---|---:|
| command | 2/4 |
| api | 4/4 |
| keyword | 1/4 |
| user_guide | 4/4 |
| recipe | 1/4 |
| known_issue | 0/4 |

问题和答案判定在运行评分前冻结；API 名称从来源函数目录确认，未先查看
检索排名。题集 SHA256：`2878eb0b5b7a98e92086dac69358dcfb52865aabeac8ec9e6d6a45226962c9cd`。
使用固定的外部 schema-v2 索引，SHA256：
`926bdbd508ff701a59e63bc266d42c72b82c68370b27c38644cf8ac79d3b9d42`。
该快照含 1250 条命令、68 条 API、195 条关键字字段、288 条指南、15 条配方、
69 条已知问题；字段和来源覆盖有限，缺失覆盖同样计为未命中，未改分母。

实际 Git revision 为 `dc9dbc197c013221eeacbb8652602442676b9ba3`，带本次
未提交修复；运行时 diff SHA256 为
`93bd5b9f463f689968c96d270e946178412856f45bfef793e14c5b8ca5e99dde`。
启用了本机私有 API/指南检索，仓库内只保存题目、文档 ID、来源、版本和结果，
不保存私有正文或索引。[证据 JSON](evidence.json) 的 holdout 记录完整结果。

## 旧二十题调优集（不能证明泛化）

同一题集、同一判断条件：首轮 18/20；补齐保存/PNG 构建器源码示例后 20/20。
前 3 条是否含预定来源位置/字段/文本的检索检查；不等于 Agent 回答忠实性或工程正确性验证。

| 题号 | 类别 | 查询 | 首个正确名次 |
|---|---|---|---:|
| C01 | command | 如何选择节点 | 1 |
| C02 | command | 保存关键字模型 | 1 |
| C03 | command | 导出图片 PNG | 1 |
| C04 | command | 如何切换 state | 1 |
| A05 | api | SCLGetDataCenterInt 返回类型 | 1 |
| A06 | api | get_data 如何取变量 | 1 |
| A07 | api | SCLGetDataCenterFloatArray 数组接口 | 1 |
| A08 | api | SCLCheckIfPartIsActiveU 显隐 | 1 |
| K09 | keyword | *MAT_ELASTIC 弹性模量 | 1 |
| K10 | keyword | *MAT_ELASTIC 泊松比 | 1 |
| K11 | keyword | *MAT_024 屈服应力 | 1 |
| K12 | keyword | *PART 材料编号 | 1 |
| K13 | keyword | *CONTACT_ERODING SFS 接触刚度 | 1 |
| G14 | user_guide | command file | 1 |
| G15 | user_guide | *INCLUDE | 1 |
| R16 | recipe | Block Mesher 盒体 | 1 |
| R17 | recipe | 节点平移配方 | 2 |
| R18 | recipe | SCL 坐标 CSV | 1 |
| I19 | known_issue | 连续 genselect add 是否覆盖 | 1 |
| I20 | known_issue | 工作目录有中文和空格为什么打不开 | 2 |

[证据 JSON](evidence.json) 保留两轮结果、命中文档 ID、来源 ID、版本和证据等级。题集在 tests/data/knowledge_queries.json，SHA256 两轮相同。
索引覆盖六类来源及七个关键字标识的 195 个字段；私有资料须 include_private=true。未复制手册/API 正文和本机路径。
