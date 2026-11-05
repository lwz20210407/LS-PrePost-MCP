# P11 typed matching r2：LS-PrePost 4.13

实际revision `be3244df3073c6e9b99ac052c093015bbf0419e5`；dirty=false；empty diff `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
这是完成并释放唯一串行lease后的新r2捕获，不是对旧r1重新标记。

| 口径 | 实际结果 |
|---|---|
| pytest |12 passed / 0 failed / 0 skipped|
| 业务正例 |10 succeeded|
| 占位符警告 |1 partial|
| 预期计数不符 |1 expected failed，已执行一次before-save原生检查|
| 实际native进程 |23，全部headless/rc0/无超时；没有预分发拒绝冒充原生|

## 上下文与身份

程序 `lsprepost4.13.exe` SHA `ce76fdf75a2f14c0a3e94964809ddd178934d04381f7f31e1e1eb05592bd5414`；源配置 SHA `b07a0f5466e4a3c438c4b98f78e4a8e193249c6ed1c8f8c4cb465a4d7bde4958`。
两版程序/源配置在每版前后和整批边界均实测；新测量保存私有before/after字节副本并比对SHA、size、mtime、device、inode，均保持；source/public Include树字节和目录、checkout及结束无残留守卫通过。
完整profile保留在evidence，不把file resource与真实runtime查询混同。

## 每项用例

| 用例 | pytest | 业务结果 | 实际进程 | 原始树重开 |
|---|---|---|---|---|
|edited|passed|succeeded|2|True|
|edited-search|passed|succeeded|2|True|
|empty|passed|succeeded|2|True|
|include|passed|succeeded|2|True|
|mismatch|passed|failed|1|None|
|placeholder|passed|partial|2|True|
|public-edited|passed|succeeded|2|True|
|public-include|passed|succeeded|2|True|
|relative-search|passed|succeeded|2|True|
|search|passed|succeeded|2|True|
|standalone|passed|succeeded|2|True|
|unused-search|passed|succeeded|2|True|

before_save为既有规范化输入观察，after_reopen按另存根目录和相对主文件名读取实际保存树；不以平铺副本替代另存树路径验收。
原12条产品绑定路径保持，另加matching.py与_identity.py共14条，测试绑定原两个P11文件。完整source snapshot仅作来源审计，不证明14个模块所有功能均被覆盖。
原生观察/Part IDs、每个PID与manifest/proof SHA均白名单记录；私有绝对路径、配置正文及原生日志留本地。

## 原始报告身份

- `execution-context.json`：`a81d36d55510740b782daf065123bb50f240738135b04dcc5d9cda1431937438`
- `report.json`：`efe2621d70435e2332ca4ae9382bc9f2e224e9eb35db167e3a535e48242002dc`
- `report.md`：`3ce5af87efc308cdf1d1b47ff7967f0510bbf46a2e104ca4084ddc72bad97f92`
- `working-tree.patch`：`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

## 有效性与限制

本记录当前仅对列明产品blob和原12项范围有效；P11保持partial。GUI、4.8、更广合法Include变体、非ASCII另存及物理正确性不由本轮证明。
旧r1真实source410偏好文件hash变化仍为失败历史；writer未确定，不归因于I02代码，也不宣称全局配置写隔离已证明。r2基于自然变化后的f5ed配置新输入实测通过，不能覆盖旧失败。
