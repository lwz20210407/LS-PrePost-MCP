# I04：100 例公开语料的 INCLUDE 预检与原生复跑

在干净提交 `19303f7792784108a807a9d6eb00c58b5c2d241a` 上用 LS-PrePost 4.13 无图形复跑同一批 100 例：**16 passed / 34 failed / 50 evidence_only（pytest 为 xfailed）**，退出码 1。历史 **16 passed / 84 failed** 保留；50 个输入限制未启动原生，未改记通过。实际版本资源、报告哈希、源码 Git blob/LF 身份、逐例树指纹和新旧分类见 [evidence.json](evidence.json)。

100 份案例记录都有树 SHA256 / 版本、文件 relative / role / size / sha256；原始输入和预检实际读取的 INCLUDE 文件均已复核字节未变。预检错误中的缺失文件没有伪造哈希；结果族另标 tree_kind=result_family。完整日志和绝对安装路径只留在外部报告。

剩余 34 个失败：24 个被旧原生 INCLUDE 导出入口拒绝，8 个为原生入口尚不支持的 INCLUDE 变体，1 个原生进程崩溃，1 个数值读取器状态数不一致。I04 保持 partial，不把这些统一认定为数据问题。

此前 19 个“原生读入为空”案例在本轮带版本运行中：14 个已通过原生 inventory，随后卡在 INCLUDE 导出；4 个被输入预检拦截；1 个原生崩溃。旧运行未记版本，不能据此断言旧失败的根因已经修复。

## 83 个 keyword 案例的新旧分类

旧 ce28 近似分类为变体 27、缺文件 17、路径写法 8、其他 31。新分类优先采用共享预检第一条 error 的 kind/hint；因此同一案例同时有变体和缺文件时，归入输入错误。预检无 error 才报告原生变体限制或待诊断，不强行维持旧分组数量。

| 旧分组 | 新预检分类 | 数量 |
|---|---|---:|
| missing_file | input_not_found | 17 |
| other | input_not_found | 5 |
| other | input_unreadable | 1 |
| other | preflight_ok_requires_native_diagnosis | 25 |
| path_form | input_absolute_path | 2 |
| path_form | input_not_found | 6 |
| unsupported_variant | input_not_found | 19 |
| unsupported_variant | unsupported_native_include_variant | 8 |

## 可复核记录

报告：`r9-public100-batch-report/report.json`；100 个 per-case JSON 均与总报告逐例对应。共享 API 默认禁止网络引用，本轮没有联网补取缺失文件，也没有修改公开语料。GUI、远程和其他版本不在本次运行内。
