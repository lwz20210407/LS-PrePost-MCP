# P10 控制/输出：有限来源归档（partial / L1）

Native实际revision `0162fdc1da3d132d32b8aa8fda309b5a26742ba5` / snapshot `58263a3aa8229e8279a6fdea4c36bd35571f86618dc79d7e86e81b027975aab6`（clean669）。Host实际revision `80e122e2d493c16aaacd56c45b2045315e03f1ee` / snapshot `a2f334834377fd26986905af3fd29adaa1b15e68e6e8e7f79b1b846643b9d963`，108项通过；其48项产品来源不混称Native43产品/51总来源。Wheel另属 `80e122e2d493c16aaacd56c45b2045315e03f1ee`。各上下文分别保存，不改绑旧Native到新host/wheel revision。

两版均实际新pin run_recipe(model:control-output@...)→save_model实际saved root重开→ordinary export；每版三个真实job。八卡只核调用者显式字段、原几何/材料/引用与源字节。所有其它native值、raw token/raw行另作完整观察，不将blank泛化为0，不从actual回填expected。

| Version | Actual source | Comparison SHA256 | Job UUIDs | 有效性 |
|---|---|---|---|---|
| 4.13 | `0162fdc1da3d132d32b8aa8fda309b5a26742ba5` | `1bb050b2910057d1dec63434e24f4cf3fb389e79bbbf5a678da51da0649648d3` | b61101a824604a038d608204f605e9d1, ab1d8736d44f43f08e73a1f8b89f8c8d, a400bd47f94a4331ada8bd8d76cfb72a  | 登记关键来源当前不变；有限定义字段保留 |
| 4.10 | `0162fdc1da3d132d32b8aa8fda309b5a26742ba5` | `07b8ee2803a5d40b02fe6b40f6cd26f8d5ab7b65857595098a6fdde9659ebc3e` | 5807bf3d983741a4ba628c687c08fbed, 28db5609428b42b99d598a8dbd48b4fb, ff77cc740e5c44d6b916c85466d4b0c3  | 登记关键来源当前不变；有限定义字段保留 |

Lease proof SHA256 `0d1856d78110e4d506c0f71c644940cceb3edb59464aaee8c3f6d921b3fae19e`；有效内部独立账核采用V2，V1无效stat断言保留为旧审计尝试，不当产品失败。每job核inspect_model/inspect_model/export_keyword、argv0/manifest executable path/stat、私有cfg完整source SHA和Windows Job记录。大exe per-job SHA为null时只称stat identity；完整SHA来自外层前后链，不声称连续监控进程内字节。Child OS创建未独立观测，host起止不冒充OS时间。

真实回归采用clean21978及保留的外部current-test overlay（确有test SHA）的两个失败；最早06b无test SHA记录不补造，不将本次Native/host重新绑定到旧版本。wheel首次collector取单个TextContent失败与同包R2修正分开保留，未改原proof/log；如果后续新source重建wheel，则另列实际新上下文。

结果仅有限定义字段保留；typed_control_recognition仍unverified、physical_response=not_run。无R11/GUI，整体验收不完成；provider/recipe metadata维持L1，任务保持partial，原接受标准/版本不改。A10检索/索引另由独立证据负责，本报告不宣称其结果不变。


后续仅测试兼容修复：首轮CI 7da0242 的Ubuntu 3.11为4640过/1失败，minimal为3415过/11失败，另外三任务因fail-fast取消，均未算绿。十个依赖PyDYNA的执行用例现局部声明SDK，44个发现/参数/旧pin用例保持无SDK执行；actual clean0d8有SDK54过，孤立SDK缺席模拟44过/10跳过（不是完整最小环境）。A08全目录测试两处显式取limit50，保留5/6断言、默认limit20/排序和警告；b2a独立模块59过/2跳过。原80e的108项host及0162 Native来源不重绑，没有新Native或索引建库，最终完整矩阵由PR新头CI决定。
