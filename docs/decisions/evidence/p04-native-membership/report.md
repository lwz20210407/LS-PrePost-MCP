# P04：具名编号闭环后的有限原生成员验证

**P04整体仍partial。** 当前记录只覆盖ce76字节身份的4.13程序、自有单文件四节点、LIST/GENERATE/ADD三组成员；不是通用编号适配器或完整顺序/保存验收。
实际执行提交`01a6be53ea5de9364be02f0705d9b1a0f847506c`，dirty=false、empty diff；1fc merge时既有src/tools/tests与执行头逐字节相同；本PR随后新增的专属来源门禁是离线测试，不冒充原生执行上下文。来源和上下文见[evidence.json](evidence.json)。

## 实际闭环

独立手写用户ID为11、37、89、121。原生完整node_ids注册表逐一核对；每个具名internal_id均等于独立升序表的0起算位置，具名user_id反向读取全部四项成功后，才允许本构建静态路径的1起算集合槽位解释。
这不是看四个raw数值拟合偏移量：所有注册表/双向映射/程序/输入守卫先闭合；不满足条件即拒绝，也没有把这条规则接进通用产品读取路径。

| 集合 | raw ids_inset | 验证后的用户ID | 手写定义 | 成员一致 | 定义顺序一致 |
|---|---|---|---|---|---|
|101 LIST|[4,2]|[121,37]|[121,37]|true|true|
|202 GENERATE|[1,2,3]|[11,37,89]|[11,37,89]|true|true|
|303 ADD|[1,2,3,4]|[11,37,89,121]|[121,37,11,89]|true|**false**|

只有一个真实无图形进程：PID5828、rc0、未超时、3.75秒；API succeeded与domain passed分别记录。六项own身份守卫通过；两版本源配置完整字节SHA、size/mtime均实测保持，私有before字节留本地，其他版本未启动。
source/config SHA、producer/test Git blob与原始工作树SHA、脚本/fixture/created model、job manifest和原始报告SHA均登记；私有路径、配置正文、厂商伪代码不入库。

## 原失败保留

旧d139 raw和三项用户ID不一致仍是原历史观察。950首次新producer实际启动但domain failed，未被新规则倒改为成功。
对950 raw采用后续规则的离线重评仅说明policy差异，明确new_native_execution=false；真正新成功是01a/r2的独立新进程。旧报告与旧analysis-only对象未重写。

## REA怎样辅助，而没有扩大证明

仅复用已有静态导出：相关分发/集合扩展路径使用1起算的排序记录位置，而具名user_id的NODE路径是0起算数组读取；普通查表根、部分callee及alternate backend仍未全面恢复。
登记ce76、manifest/dispatch表/函数序列及18个函数的bundle/entry/hash，以文字概括逻辑，不复制厂商伪代码。输出是近似恢复伪代码的静态观察，既非厂商原始源码，也不是调用栈运行追踪。
这支持严格受限的充分条件：完整原生注册表和每个具名双向映射先实际证实排序位置一致，再对本四节点fixture解释集合槽位；不外推4.13.5、其他构建、Include或未知后端。

## 检查与未完成项

33项host pytest及30个有限内部peer控制分别记录，不相加为native数量；新native只有1次。内部peer不是用户安排的独立done审阅。
ADD顺序已出现差异；Include、非4.13/其他实体族、稀疏/逆Increment、参数化成员、完整保存重开与通用table关系均保留gap。原P11配置漂移历史也没有因这个窗口保持而变成已修全局写保护。

## 复跑

需要root单一串行headless授权、同字节身份4.13程序与已有配置，先保存两profile源配置字节及SHA/size/mtime，结束复测；不能把普通单测/mock当native。

```powershell
$env:PYTHONPATH = "<worktree>\src;<worktree>"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:TEMP = "<本任务仓库外scratch>"
$env:TMP = $env:TEMP
python -B tools/verify_node_set_user_ids.py --run-native --executable "<同ce76字节身份4.13程序>" --output "<全新仓库外输出目录>"
```

本分支另加3项离线来源门禁；在1fc加授权文档/新门禁WIP时，与原33个producer单测一次运行36 passed，source/producer核心未变。36已含33，不与30个peer控制相加，且不是新的原生执行。
