# I04 两例公开语料失败诊断

派发 #91；实现 #92。I04 保持 **partial**。机器可读记录见 [evidence.json](evidence.json)。
本轮只诊断两个已有 gap，未把路径对照或离线回归算作原生验收通过。
下文 4.13.0.1 来自安装文件的版本资源；未将其标记为独立核验的运行时构建号。

## 关键词：非 ASCII 的 INCLUDE 根路径

`extra-keyword-064`（`keyword.Wanggs2418__ANSYS_Code`）的两个输入文件与 #54
冻结证据哈希一致，预检通过。4.13.0.1 在绝对源路径打开失败后以 `3221225477`
（`0xC0000005`）退出，未超时，未得到 inventory；因此没有执行保存/重开。
这不是历史 `extra-keyword-020` 的输入限制，也没有证据表明是空模型。

第二个独占时段只执行三次 inventory：

| 输入 | 唯一受控变化 | 结果 |
|---|---|---|
| 原创四节点壳、plain INCLUDE | ASCII 父目录 | 成功 |
| 同字节原创文件族 | 中文父目录 | 打开失败，原生失败 |
| 公开例的完整两个文件、相对结构和字节不变 | 暂存到 ASCII 父目录 | 成功 |

现有 batch 路线对单文件使用 ASCII 暂存名，但含 INCLUDE 的模型仍直接打开绝对根路径。
证据支持在 Windows 此路线启动前拒绝非 ASCII 根路径。本次在 `Service._native` 增加明确
`ValueError`，发生在创建作业之前；不改文件、不自动搬移输入、不启动原生进程。
ASCII INCLUDE、非 ASCII 单文件的既有暂存路线继续进入原有逻辑。
**Unicode 原生支持没有修好**，原路径验收仍未通过；ASCII 对照不能代替验收。
含 INCLUDE 的原生导出仍受既有 staged-tree 限制，未绕过。

## 结果：结束标记后尾数据被读取为状态

`extra-result-03`（`result.ansys__pyansys-heart.tests.heart.assets.post.zerop`）
两个文件的哈希与 #54 一致。4.13.0.1 得到 2 个状态，时间 `[0, 1000]`。
LASSO 2.0.4 元数据和完整读取均得到 11 个状态：

```text
0, 1000, -999999, 300.4748934509089, 400.950350711292,
501.4258079716751, 604.1580370191859, 707.308836521931,
814.3632933164408, 933.7954444824898, 1000
```

用现有 LASSO 布局计算得到 wordsize=8、每状态 1,957,336 字节；状态文件偏移
3,914,672（恰好两个状态之后）已有结束标记，21,530,696 还有结束标记。
LASSO 2.0.4 的 `_collect_file_infos` 从文件尾寻找最后非零字节，再除以状态大小估计数量，
没有在第一个结束标记处停止。这解释了第三个“时间”为结束标记值及其后的错误状态映射。
这些是局部字节检查和既有读取器的诊断，不是另写结果解析器。

原创回归由 LASSO writer 写两状态四节点壳，先验证时间 `[0, 1]`，再只在原创文件的
结束标记后添加非零尾数据。同一 reader 变成 `[0, -999999, 1]`，诊断保留全部值并报告
状态数不一致。此回归固定记录当前 2.0.4 缺陷；它的通过不代表读取器修复或原生验证。

交 Claude 的接口需求：在共享读取器处校验状态文件结束边界，保证 state_filter、完整读取及
元数据读取一致；遇结束标记后非零尾数据，应明确拒绝并给出文件/偏移诊断，或实施经独立
验证的边界读取策略。不要过滤返回时间中的 `-999999` 后重新编号，也不要只调整状态数。
所有结果量的状态映射须一致。共享 model/results 和 LASSO 安装均未改动，此 gap 仍开放。

## 复现、来源与验证边界

先配置外部 `LSPP_CORPUS_DIR`，安装锁定的 results/dev 依赖；默认只做离线诊断：

```shell
python tools/diagnose_public_corpus.py --case extra-result-03 --output <新的仓库外目录>
python tools/diagnose_public_corpus.py --case extra-keyword-064 --output <另一新的仓库外目录>
```

仅在获准的独占 headless 时段追加 `--run-native --executable <已确认的安装>`。
修复后原关键词路径会在启动前拒绝，原生崩溃记录来自修复前的诊断版本。
工具输出原始 `diagnostic.json` 与作业日志，可能含本机路径，**不得直接提交**。
它只支持这两个登记 ID，复用注册表、预检、Service/Engine 和既有 LASSO reader。

五次 4.13 调用均逐次核对无残留进程；源文件族 SHA256 和源目录清单前后不变。
源/输出身份、实际 revision、dirty diff SHA256、固定 diff 命令及源码字节哈希记在 evidence。
原生时源码尚未提交：Git patch 不含未跟踪文件，source snapshot 包含其哈希；按磁盘原字节
取哈希，不把 CRLF/LF 归一化的 Git blob 冒充同一指纹。没有在修复后重复原生窗口。
外部清单登记关键词来源 Apache-2.0、结果来源 MIT；仍不再分发模型、结果、手册或原生日志。

本地相关 pytest：29 passed / 2 skipped；非 ASCII INCLUDE 拒绝回归修复前 1 failed，修复后通过。
相同相关测试在现有最小依赖环境为 28 passed / 3 skipped（缺 LASSO 的原创二进制复现跳过）。
Ruff、import-linter、validate_tasks、gen_docs --check、validate_tool_migration、
fetch_corpus --check-registry、check_doc_links、git diff --check 均通过。
完整 Ubuntu/Windows × Python 3.11/3.12 与 minimal-deps 以 PR #92 的正式 CI 为准。
未执行 GUI、UU、4.10、求解器；不改变 I04 原验收和其他未完成格。
