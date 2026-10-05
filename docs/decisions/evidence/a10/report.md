# A10 固定二十题检索评测

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
