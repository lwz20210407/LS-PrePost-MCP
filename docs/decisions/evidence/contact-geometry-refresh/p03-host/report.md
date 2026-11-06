# P03 当前来源刷新（L1，partial）

实际执行 revision `b75759754c7fa1a830de4b7703847f34cff95eaf`，source snapshot `4426fc9e60f68936db44d5f1f444993732477df3c2bf85cee0c4d860a9a9db68`。

角色 `p03`：60 项通过、0 跳过；24 个选定产品来源，4 个实际测试/fixture 来源。各角色有重叠，数量不相加作为独立覆盖。

原始 proof SHA256 `7a591e7ab38f7f7744cbe78578c91e45315e03e7a327b12402a29e793a101013`；日志 SHA256 `dfff610072ed8f61cdeee6ba743b590cdd1e4ffd743f52742aa503a3e1897c28`；JUnit SHA256 `52e768d3ebd3f4e81123fe510dda75d9c5b0d12be8c0121f883604ef98e275bd`。源码执行前后严格一致，命令、raw 源码哈希与 Git blob 对照保留在本机原始记录。

同一冻结来源另完成一次离线 wheel 构建与解包 smoke：785079 bytes，SHA256 `e4799a1edd48315e9eb591453ac3cfb774582348d3f7cac18fbb436b1048660f`。221 个成员全部分类：215 个包/force-include 源码成员、1 个额外许可证及 5 个生成 metadata；记录每个成员的来源类别和 Git LF/原始 wheel 哈希，不将生成 metadata 伪称为 Git 原件。九个旧 source-document refs 不漂移，只执行原 baseline Elastic ref。

wheel smoke 验证 extracted full/compact in-process FastMCP，省略参数与显式 None 等价，预算缺口为非 required coverage missing 且 complete=false。它不是 stdio；本角色既有两个材料 stdio 用例属于上面的实际60项测试。没有 pip 安装、新项目环境或 native 执行。

stdout 原 producer 在内存 LF 文本上计算 `c3836a25c154dffe8a3fe6455318dd919d6452b1bb622168754a71e98910b0af`，Windows write_text 落盘 CRLF；实际落盘文件 SHA256 `92158c0ea8e9f4fee80f6e90564fc5ffc6e0597a3556473d6466d6cb69dd35e4`、197 bytes。两种身份分别归档并可重算，不把换行差解释为产品失败。原 proof、输出与 wheel 均未改写。

选定关键依赖不代表全部程序依赖或全部功能覆盖。以上是 host L1；不等价于原生 Contact Check、typed recognition、求解器响应、GUI 或 P06 整体验收，任务状态保持 partial。历史记录只引用，不重绑原 revision。

有限内部只读账核报告 SHA256 `23011917ad4f38f5b0a5259ba0cb949d711688aa23041b37a01b373a06459a2e`：在记录范围内未发现新的 P0/P1；不等于用户安排的独立外部 done 审阅。私有逐项账本不公开。捕获时 clean b757 的662项源码/snapshot4426保持原值；后续归档新增测试，当前全树快照不同，未把当前 WIP 倒写为捕获时状态。历史 JobObject 关联只按 manifest/engine 记录表述，不冒称本轮重新观测内核绑定。
