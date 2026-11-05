# P04：节点集合组合与身份修复

本记录为 **partial / L1**，实际产品提交 `d1397647b8f1385c406fcf8d95a2f18c819d5362`，公共回放与单次诊断均在干净工作树/空diff执行。
节点 LIST、GENERATE、GENERATE_INCREMENT、ADD 复用现有 AST、字段、引用、Selector、接触消费者与定义比较；不新增第二套整文件解析器，不将子集合SID当节点ID。
产品/测试/producer Git blob、输入及报告SHA见 [evidence.json](evidence.json)。

## L1行为与范围

LIST保持写出顺序；ADD按可达共享图解析前向/嵌套引用，去重且检查cycle/重复SID/缺子集合；Selector继续其排序唯一投影。
plain GENERATE按已定义节点号筛选闭区间，编号有洞及端点不是现有节点号均可作为limit；依据官方R11 Vol I39-22的语义摘要。手册26-27供相关列表/生成卡对照；厂商原文/图片不入库。
Increment含洞及反向的语义尚未独立核实，明确Unsupported，不记作求解器输入缺陷。
巨大数值跨度不逐整数展开，按现有节点索引筛选；重复范围、共享图边数与输出受工作预算约束。

节点SID/成员输入使用共享exact_integer，拒绝布尔及有损小数；保留合法int、integral-float和整数文本。
读/写/删SID匹配按实际Node AST块精确比较，字段名大小写及glob不能退回浮点近似；混合匹配中的非Node集合保留既有规则。
Node定义成员、range limit及ADD operand离散比较不使用物理float容差；DA等连续属性容差仍保留。
接触读取/创建、load与member edit共享Node语义；缺节点为明确语义拒绝。失败事务不写模型、不改变原Include树字节/结构；参数成员/范围仍是明确gap。

## public-l1

已登记 `include_contact`，四个源文件共273975字节、1946个节点。原始树SHA/字节及目录清单前后不变。
在独立Python已存节点号过滤oracle下创建四个定义：反序端点LIST、plain GENERATE、无孔两点Increment、ADD。生成及组合选择12个成员，与手写范围/原节点号oracle逐ID一致，AST另存重载及operands精确读回通过。
这不是原生成员或保存重开后的原生顺序/ID验收。

| 检查 | 范围 | 结果 | 有效性 |
|---|---|---|---|
| 公共Include回放 | 4源文件/1946节点/4新定义/12生成成员 | 字节、目录、ID及AST重载核对通过 | 当前有限L1（d139） |
| 相关模型测试 | 单独515 passed / 1 skipped命令 | 通过，跳过不算通过 | 当前本地范围（d139） |
| 内部peer终验 | 106相关及有限独立SID/图/事务控制 | 原三组及大小写/glob绕过关闭，源码前后稳定 | 当前内部审阅，不是外部done门槛 |

515/1、peer106及旧442/460等命令集合重叠，**不得相加**。
复跑已有producer，复用项目环境，在本工作树显式设置PYTHONPATH，输出必须全新且在仓库外：

```powershell
$env:PYTHONPATH = "<worktree>\src;<worktree>"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -B tools/verify_node_set_composition.py --case include_contact --corpus "<已登记corpus>" --output "<全新仓库外目录>"
python -B -m pytest tests/test_node_set_composition.py tests/test_node_set_review_boundaries.py tests/test_selector_identity_exact.py -q
```

## 真实红例与修复

| 历史范围 | 结果 | 有效性 |
|---|---|---|
| 原main2e706的接触ADD/无关Generate/定义比较三例 | 3 failed | 历史红例；产品为旧头，新增测试非clean测试checkout |
| Selector布尔身份 | 6 failed / 3兼容control | 已修，未把True转为实体1 |
| 8ad范围/consumer/离散比较复审 | 16 failed / 1物理属性control | 已修；当时另有四行文档WIP，不能称全树clean |
| 7d大小写/glob SID读写绕过 | 16 failed / 3control，另补完整读/写/删矩阵 | 已修，helper按实际Node块统一，不散落修补 |

修复包括非零odd range尾/超过卡宽字段不静默丢弃，CSV每卡的0padding不与下一卡串对；Node contact/member路径先做无损身份规范化；缺节点不再落入IndexError；大整数SID/NodeID/离散limit不被相对float容差合并。
所有原始失败、输入与源码状态保留本地；仓库只登记对应摘要和SHA，内部审阅不是用户安排的独立外审。

## 单次原生诊断：执行已发生，成员意义未确认

干净d139、4.13资源身份明确的headless进程实际执行一次 `ids_inset` / `DataCenter.Type.NODE`，returncode=0、node_count=4；输入/程序/配置三守卫通过，结束无live native。
raw记录如下，未改type、未转换、未重试：

| 请求SID | 手写预期用户ID | 原始返回值 | 与预期用户ID一致 |
|---|---|---|---|
| 101 | [37,121] | [4,2] | false |
| 202 | [11,37,89] | [1,2,3] | false |
| 303 | [11,37,89,121] | [1,2,3,4] | false |

这些值的返回含义尚未独立确认，不能猜成内部索引或用户ID再映射。进程/文件/count成功不等于成员验证成功；本轮**不计L2**，原生成员及保存重开后ID/成员/顺序完整验收仍是gap。
程序、配置、输入、producer/script/raw报告SHA与PID在evidence中白名单记录，原生日志/手册/本机绝对路径留本地。

## 其余gap

其他集合族的紧凑表示、特征角外表面、变形构型、Increment有洞/反向、参数化成员/范围、i10紧凑创建及更广布局尚未完成；本提交不改变release/完整验收，也不将P04改done。
