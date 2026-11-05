# P12：边界曲线helper显式41来源复验

实际源码 `3da18f1f924ac499aa66dc49675d25280a855f54`，snapshot `9b3c446eaa5b40995cc2e8fd73cf49e2fd52afba748a682191fa9605ccc71137`，dirty=false/empty diff。loads.ensure_curve 在这次**实际显式41**（32 product+9 auxiliary）中，不沿用旧40加后验补档。

| 版本 | case | Joint定义数 | strict差异 | 格式记录 | 剩余差异 | 真实job | 有效性 |
|---|---|---:|---:|---:|---:|---:|---|
|4.13|pilot|1|0|0|0|3|当前有效|
|4.13|nine_types|11|2|2|0|3|当前有效|
|4.13|body_modes|4|0|0|0|3|当前有效|
|4.10|pilot|1|0|0|0|3|当前有效|
|4.10|nine_types|11|2|2|0|3|当前有效|
|4.10|body_modes|4|0|0|0|3|当前有效|

仅普通两motor/type0不适用R1空槽写0的原窄规则；两项严格差异和两项格式记录逐一分列。保存树实际根目录重开、普通export的逐字节相同staged input，以及手工Joint/双侧body/节点/集合/曲线期望保持。native导出文件本身不声称与saved逐字节相同。

实际配置输入为批准的只读私有snapshot（413 b07/410 d018）；每job来源及SHA、完整字节/stat、双exe、源/公共目录与空库存守卫均通过。globals独立passive observation，不是输入或全局写隔离证明。4.10仍为regression_subset，fixed4.9.0.1/string4.10.0.1冲突事实保留。

同一串行批次为P05六job+P12十八job，总24个唯一UUID；PID不作为去重依据，OS子进程创建未连续测量，host时间不冒充OS创建时间。内部另一Agent只读逐manifest/context/source41审计通过，不是用户安排的外部独立审阅。

本页新六run/checkpoint成为active；旧18个run、两个checkpoint、1289原40+后验loads补档、be0/80/1b/28失败/探索/恢复对象均原值保存。旧报告为历史已被取代，不改写其实际revision或测量结果。

P12仍partial。仅自有单文件关键字定义往返；typed Joint识别、动力学/R11、Include树、GUI及广泛真实模型仍未验。原生日志、配置正文、绝对路径及手册不入公开仓库。
