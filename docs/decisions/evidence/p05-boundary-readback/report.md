# P05：边界身份安全与单文件定义回读

P05 保持 **partial**。L2 仅指本页自有单文件的关键字定义保存、实际重开及导出读回；typed 原生边界对象识别仍 unverified，物理响应/R11 未运行，不证明所有目标、选项、Include 或真实模型。

实际运行源码为 `3da18f1f924ac499aa66dc49675d25280a855f54`，dirty=false/empty diff，完整 source snapshot 为 `9b3c446eaa5b40995cc2e8fd73cf49e2fd52afba748a682191fa9605ccc71137`。显式 41 个关键源码、producer、手写 fixture、测试与锁文件另列 Git blob 和当时 raw SHA；这不是全功能覆盖百分比。

| 版本 | 九类定义 | 真实 headless job | 严格差异条目 | 文档写出规则 | 受限观察记录 | 剩余差异 | 有效性 |
|---|---:|---:|---:|---:|---:|---:|---|
| 4.13 | 9 | 3 | 59 | 37 | 6 | 0 | 当前有效，具名构建校准范围 |
| 4.10 | 9 | 3 | 59 | 37 | 6 | 0 | 当前有效，同规则迁移核对 |

59 条严格比较条目不是 59 个独立物理缺陷；其中其它字段/卡片形态 42 条、墙关键字键/正文映射 17 条。37 条文档写出规则与 6 个受限观察记录也不是逐条相加覆盖 59 的计数：新增整卡与墙映射是结构规则。source / native_expected / actual 三投影及全部严格差异均保留，不能称原生导出字节与源完全相同。

## 手工预置的九类定义

| 类别 | 独立预置的主要值 |
|---|---|
| SPC | NodeSet101，CID0，x/z/rz 固支 |
| 规定运动 | rigid Part20，DOF2/VAD0，LCID701，SF0.125 |
| 节点力 | NodeSet102，DOF3，LCID701，SF-7.5 |
| Segment 压力 | SegmentSet201，LCID702，SF2500 |
| 重力 | LOAD_BODY_Z，LCID701，SF-9.81 |
| 初速度 | PartSet301，STYP1，速度(0.25,0.5,-1.25)，OMEGA0 |
| 刚性墙 | NSID0=all nodes，尾点z=-2/头点z=-1，摩擦0.2 |
| CNRB | PID30 / NodeSet103，成员89、121 |
| 无反射 | SegmentSet202，AD0/AS0 |

原始夹具含16个非连续用户节点ID、2实体单元、Part10/20、手写集合与曲线；701点为(0,0)/(0.5,0.5)/(1,1)，新702为(0,0)/(1,2)。单位仅调用者声明 m-s-kg-Pa，没有换算或量纲认证。全部边界字段、依赖头/属性、成员/点及几何/Part关联通过现有 KeywordDeck named fields 核对；期望不从创建结果或原生输出自动补齐。

路线为已有 `Service.create_entities → save_model → export_keyword`。save_model 的两次 native observation 保留真实另存根目录重开证明；普通 export 的暂存单文件与 saved 文件逐字节相同。没有 raw-tree 目的白名单绕过、第二执行引擎或 typed 识别证明。

## 表示变化的依据与限制

官方本机 R11 Vol I PDF SHA 为 `3f1cf3cc8c8222ad059459aca2c452f6af6afcce263b8eb8ba157495684da343`；只归档页码、hash 与释义，不公开原文/图片。

- VID：pdf575/5-47 默认0；仅本 DOF2/VAD0 卡的空槽到精确整数0。
- 初速度：pdf2337/24-95、2338/24-96 定义 ICID 默认 global/0，第二卡六个实数零及 PHASE/IRIGID 整数零。只接受本 STYP1/ID301/OMEGA0 的完整八字段零卡；缺、多、bool、非有限或非零均拒绝。
- SET DA1–4/SOLVER：pdf2872/39-20、2882/39-30、2887/39-35 的0/MECH；curve七头字段见pdf1716/15-74。LCINT0按pdf1718继承 CONTROL_SOLUTION，不表示零个离散点。
- ITS：R11 表未定义它。只在无任何 Include/COSIM 的本夹具记录精确观察槽；Node raw token1、AST int1、SDK str/default string1 的差异分别保留，Segment为int0。**不称通用 R11 默认；一般 ITS 语义未证。**
- 墙：只允许单个非 DISPLAY 的 plain PLANAR 到 exact PLANAR_ID；15正文不变、ID精确整数1/title=None。R11允许RWID但无默认，title来自SDK；这是具名4.13构建观察校准，4.10为迁移核对，不是源用户指定ID或通用 strip_ID。任何其它ID、标题、选项、标志/尾项、正文变化或未知构建仍拒绝。

## 回归与保留历史

| 产品基准 | 真实旧红 | 口径 / 有效性 |
|---|---|---|
| 1289（loads blob与当时main15ac相同） | 23 failed /8 controls passed | 身份别名及分配残留；不是宣称在另一个 clean main 重跑 |
| 中间分支1274 | 13 failed | 节点/segment/晚期formatter拒绝后原子性 |
| 中间分支907 | 4+9 failed | Include改名/替换后的缓存/Scope保留；结构标题注入 |
| 8e，受控fake export | 8 failed | 走原verify_native入口的单元红；不算原生运行 |
| 8e，原生r1/4.13 | 3真实job，比较失败 | APIs成功但未知墙_ID，原status=failed/differences=null保留；已被新源r2取代但没有改写 |
| 3da，旧r1只读分析 | 无新增native | 新策略重算不是新通过；旧report/export SHA不变 |

最初31个测试夹具错误，以及格式红例首轮两个多空行夹具错误，均不计产品缺陷。合法九类旧输出的2512 LF bytes/SHA `efa7713cbf3dc24add635f7169792ddea9149346dd1edf115fccafa1d7524c1a` 保持，仅为兼容性证据。身份整数兼容形式、合法零/flag保持；失败恢复已加载Include/参数Scope/dirty edits/warnings/尾行，不重新读资源。

## 来源与执行守卫

P05六job加同源P12十八job共24个唯一job UUID；PID可重用，按job事件计数。只读私有配置snapshot是实际输入（413 b07、410 d018），每job manifest核来源及SHA，完整字节/stat/readonly、双exe、原始公共树/目录、源码和空进程库存守卫均通过。globals仅独立被动观察，不能据此证明全APPDATA隔离。OS子进程创建时间没有连续采样，保留host start/end并明确unknown。

4.10保留string4.10.0.1/fixed4.9.0.1/resource_conflict=true/regression_subset，未改成全面支持。内部另一Agent对24个实际manifest及四context/source41复核通过，审计本身0 native，不是用户安排的独立外审。

仓库只保存白名单元数据、hash与此报告；完整配置、原生日志、绝对路径、手册和语料留本地。后续源码漂移必须使当前来源门禁失败，历史对象始终保留实际revision。
