# I04：普通路径下的完整 INCLUDE 树复跑

干净提交 `53f6072ca54bc2f7c3a6bfa887450dacd78c3d93` 上用 4.13 无图形重跑同一批 100 例：**16 passed / 45 failed / 39 evidence_only（pytest xfailed）**，exit=1。11 个假输入限制已恢复进入原生入口检验；它们仍有导出或变体限制，不因此标为通过。逐例状态、哈希、Git 身份见 [evidence.json](evidence.json)。

预检、Service 输入及允许目录使用普通路径；低层长路径 IO 先 normpath，再加扩展前缀。文件清单显式声明 files_relative_to=common_input_directory 和 main_relative，父目录 INCLUDE 也有可定位的相对名称，不再用 null。100 例的原文件字节、已读树字节和源目录文件清单均已核对未变。

## 历史勘误

19303f7 的 **16 / 34 / 50** 原始证据逐字节保存在 [历史记录](historical-19303f7.json)。其中 006、025、037、042、050、063、069、071、073、074、082 的缺文件结论来自运行器扩展路径错误；这 11 个不是真实输入缺失。029、031 的错误数也从 2 降为 1。

先在 acdc648 修正路径后得到 16 / 45 / 39；随后补齐父目录文件相对定位，再于上述干净提交整批复跑，计数一致。两次修正运行及旧记录均保留。

旧 p100 的 **16 / 84** 保持不变。其 job.json 实际记录了 4.13；此前“没有版本”的说法已更正。复核旧日志得到 42 次按暂存相对名打开、127 次 INCLUDE 打开失败，全部发生在 job 目录：旧空模型来自只暂存根 deck，不能归咎于语料。

## 分类对照

以下按共享预检第一条 error 的 kind/hint 分组；预检成功后仍可能受原生入口能力限制。

| 旧 ce28 分组 | 当前预检分类 | 数量 |
|---|---|---:|
| missing_file | input_not_found | 17 |
| other | input_unreadable | 1 |
| other | preflight_ok_requires_native_diagnosis | 30 |
| path_form | input_absolute_path | 2 |
| path_form | input_not_found | 6 |
| unsupported_variant | input_not_found | 13 |
| unsupported_variant | unsupported_native_include_variant | 14 |

剩余原生/入口失败：{"legacy_include_export": 29, "unsupported_native_include_variant": 14, "native_process_failure": 1, "backend_state_count_mismatch": 1}。I04 保持 partial；本批未覆盖 GUI、UU 或其他版本。
