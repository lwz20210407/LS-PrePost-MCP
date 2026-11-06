# P12 当前43来源定义读回刷新（L2，partial）

实际执行 revision `b75759754c7fa1a830de4b7703847f34cff95eaf`，source snapshot `4426fc9e60f68936db44d5f1f444993732477df3c2bf85cee0c4d860a9a9db68`。使用两份只读私有配置快照，执行前后完整身份、两版可执行文件与公开来源均保持；每步结束无残留进程。全控制器24个唯一 job UUID，P05为6个、P12为18个；这些依赖回归不构成 P06 原生 Contact Check。

| Run / version | Case | Raw comparison SHA256 | Controller context canonical SHA256 |
|---|---|---|---|
| geometry-b757-p12-4.13-body_modes / 4.13.0.1 | body_modes | `e83f5374d152f669b998cc5f137f20535dfed7720de50b22064bdc3f6b9fcf2a` | `9e6b3654ae6b1140b08efe9edcd10968a468fec1494ae51663d6772a7d4a4c59` |
| geometry-b757-p12-4.13-nine_types / 4.13.0.1 | nine_types | `b9237a255cd0e66471495677e69b17e7a84c36c411b623837cf3b5500dbc697f` | `9e6b3654ae6b1140b08efe9edcd10968a468fec1494ae51663d6772a7d4a4c59` |
| geometry-b757-p12-4.13-pilot / 4.13.0.1 | pilot | `e1581eb41197a9681e6ca0a3aa8bf34df3c5df255e0d77da6ad1c6f2a5c25c50` | `9e6b3654ae6b1140b08efe9edcd10968a468fec1494ae51663d6772a7d4a4c59` |
| geometry-b757-p12-4.10-body_modes / 4.10.0.1 | body_modes | `71e136e10e45f015beb1d7999ae06b4925c42f1e0242b78d729e7e4510c01202` | `9e6b3654ae6b1140b08efe9edcd10968a468fec1494ae51663d6772a7d4a4c59` |
| geometry-b757-p12-4.10-nine_types / 4.10.0.1 | nine_types | `e99c180b968bf0db023037f256d0747653d7404796143528970bd8f93275424d` | `9e6b3654ae6b1140b08efe9edcd10968a468fec1494ae51663d6772a7d4a4c59` |
| geometry-b757-p12-4.10-pilot / 4.10.0.1 | pilot | `4fc577b7ca7f351481163b253257ab32ff7ba642dfc636b181f000e47130a39a` | `9e6b3654ae6b1140b08efe9edcd10968a468fec1494ae51663d6772a7d4a4c59` |

控制器原始文件 SHA256 `eb8b942f775a9c8cb1f53547cf941f9453b588ec9e4a6bad66e07681356d0e06`。context SHA 来自其 source_before 嵌入对象，以 UTF-8、sort_keys、紧凑 JSON 规范化；不冒称存在单独的逐 case context 文件。每个 run 另绑定实际43项源码和其原始 comparison 哈希。

两版各 pilot / nine_types / body_modes：严格差异分别0/2/0；两个 type-0 motor R1 空白变0仅按已有格式规则归类，剩余语义差异0，不推导为通用物理默认。

4.13 为主要版本；4.10 字符串资源为4.10.0.1、fixed resource为4.9.0.1的已登记 regression subset，冲突原样保留。保存树重新打开的 counts/parts 与定义导出均已校验；typed boundary/joint recognition、物理响应、原生 Contact Check、GUI 和整体验收仍未完成。全局配置只是被动观察，不是本次输入，不据此声称隔离已证明。

连续 OS process-creation 观察未声称完成；本次记录实际 manifest UUID、PID、host 开始/结束时间、Windows Job 隔离与结束后的无残留检查。历史40/41来源和旧失败/观察记录保持原始字节，当前43不采用历史兜底。任务保持 partial。

每个 job 的 manifest 因可执行文件超过64 MiB，只记录路径、size/mtime 与 hash_note，sha256 为 null。完整可执行文件 SHA256 来自外层 controller/profile 与 case comparison 的执行前后链；不把它冒称为逐 job 完整 SHA，也不声称连续监控进程内字节。私有配置的逐 job source_sha256 仍为完整值。

有限内部只读账核报告 SHA256 `23011917ad4f38f5b0a5259ba0cb949d711688aa23041b37a01b373a06459a2e`：在记录范围内未发现新的 P0/P1；不等于用户安排的独立外部 done 审阅。私有逐项账本不公开。捕获时 clean b757 的662项源码/snapshot4426保持原值；后续归档新增测试，当前全树快照不同，未把当前 WIP 倒写为捕获时状态。历史 JobObject 关联只按 manifest/engine 记录表述，不冒称本轮重新观测内核绑定。
