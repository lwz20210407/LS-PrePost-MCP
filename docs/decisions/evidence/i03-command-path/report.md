# I03 命令集中约束与相对文件名回归

派发来源为 PR #83。本轮补齐可独立执行的检查，I03 保持 partial；没有修改运行时命令、版本策略或 KI-049 保护，也没有重跑 PR #76 的工作目录别名测试。

## 离线集中约束

`tests/test_native_commands.py` 的 AST 守卫增加动态 fringe、动态 xyplot ID、分号分隔和缩进多行命令的检测，保留文档字符串与解析器前后缀例外。增加反例验证守卫本身，防止测试因无法识别动态字符串而假通过。

版本守卫补充原生版本字符串的直接比较与成员测试，保留现有 Python ABI、LASSO/DPF 检查。当前 src 扫描没有发现遗留拼接或版本分支，因此不为满足形式而改动运行时代码。这是静态回归约束，不保证识别任意 Python 运行时生成方式。

## 本轮原生结果

只执行一次获准的串行窗口。复用项目自产八节点、三壳、三状态夹具；每版执行六个新增用例，普通文件名和既有 UTF-8 注释用例未复跑。

| 相对依赖文件名 | 4.13 | 4.10 | 验收 |
|---|---|---|---|
| `added nodes.k` | passed | passed | 导入、保存并重开；节点 1001 的坐标为 (7,8,9)，共 9 节点 |
| `新增 节点.k` | failed | failed | 原生无法打开文件，9 节点合同拒绝 |
| `input curve.txt` | passed | passed | 导出空格文件名；三个点精确等于 (0,0)、(1,2)、(2,4) |
| `输入 曲线.txt` | failed | failed | 原生无法打开文件，曲线产物缺失或为空 |
| `count nodes.scl` | passed | passed | 保留 SCL 字节，输出节点数 8，产物属于执行作业 |
| `节点 计数.scl` | passed | failed | 4.10 解析器报 -2，未能打开脚本；保留失败 |

4.13：**4 passed / 2 failed**；4.10：**3 passed / 3 failed**。失败用例继续使用成功验收断言，没有转换为 xfail 或成功。它们默认跳过，只在显式原生回归时执行；CI 全绿不能解释为这些原生缺口已关闭。

两版都使用 UTF-8 cfile、ASCII 作业根、相对依赖文件名，输出文件名仍遵守既有 ASCII 合同。每版八个实际原生进程作业（包括成功导入后的重开/节点读取）均为 `-nographics`，cwd 均为自身作业目录。原夹具和配置 SHA256 未变，两版结束后没有原生进程残留。没有切换到输入源目录，没有可见 GUI/UU 操作。

[evidence.json](evidence.json) 记录实际 revision、dirty diff、源码快照、四个相关文件指纹、原始报告指纹、逐例状态和作业身份。运行基于 main `e41cf65551274c496f0bb1802f952d1a30e024b2` 加本 PR 的两个测试文件改动；文档和任务登记在运行后追加。不能把此证据改称为最终提交的全套原生通过。原始日志、补丁和含本机路径的报告只在仓库外 dated scratch 保存。

复现命令（一次选择一个版本；需协调独占窗口）：

```text
python -m pytest tests/test_native_paths_native.py -q -k "spaces or unicode" --run-native --native-strict --native-executable <installation> --native-fixture <M0-fixture> --native-output <fresh-external-report> --basetemp <fresh-external-cases> -p no:cacheprovider
```

## 待窗口用例与未关闭边界

以下是待执行规格，不是已通过的测试。原生失败的原因与修复需要另一次受控验证；不凭本轮失败推断所有绝对路径、编码或 API 通道都不支持。

| 用例 | 操作与验收 | 前置条件 |
|---|---|---|
| GUI 模型检查报告路径 | 在已核验模型上执行 Model Checking，经 `modelcheck_report` 写入含空格文件名；报告非空且与已知异常实体 ID 一致，模型与选择状态不变 | 显式 GUI 窗口；各版本独立核验 |
| GUI 实体导入路径 | 用 `import_keyword` 导入含空格/中文文件名的节点片段；核对新增 ID/坐标、原实体不变，保存重开 | 显式 GUI 窗口；不可用批处理结论代替 |
| Movie 路径 | 用 `movie` 输出含空格路径；核对视频帧数、顺序、状态时间与画面身份，输出非空不足以验收 | 显式 GUI/Movie 窗口与已有三状态夹具 |
| 非 ASCII job 根 | 分别记录无别名、显式别名的 cwd、配置与产物身份；KI-049 未关闭前不修改相对配置策略 | 单独获准窗口；保留原有失败边界 |
| `native_postprocess_case` 图形回调 | 完整图形产物及数值验收 | 显式图形窗口 |

普通逻辑测试命令：`python -m pytest tests/test_native_commands.py tests/test_version_resources.py tests/test_version_profile_calls.py tests/test_scl_path_literals.py tests/test_native_paths_native.py -q -p no:cacheprovider --basetemp=<fresh-external-cases>`。共用全依赖与最小依赖环境均为 118 passed / 9 skipped。跳过项是九个 opt-in 原生参数用例。
