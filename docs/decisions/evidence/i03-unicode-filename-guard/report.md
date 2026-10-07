# I03 相对依赖文件名启动前防护（L1）

派发来源：[PR #99](https://github.com/lwz20210407/LS-PrePost-MCP/pull/99)。
I03 保持 partial；本轮交付是启动前拒绝，**不是中文原名原生成功**。

## 证据和策略边界

历史输入是 [PR #87 的冻结证据](https://github.com/lwz20210407/LS-PrePost-MCP/blob/6373e9c4a7488b0475f5efafd63ee41b44ec3329/docs/decisions/evidence/i03-command-path/evidence.json)。
该证据记录 ASCII 作业根、UTF-8 cfile、中文相对依赖名：import keyword 和 open xydata 在两个安装均失败；runscript 在 4.13 成功、4.10 失败。
证据中的文件版本资源分别为 `4.13.0.1` 和 `4.10.0.1`；它们不是可执行文件名或营销版本标签。
原失败断言、历史 dirty revision 和原生数学验收均保持原样，没有重跑旧失败矩阵。

| 文件版本资源 | import keyword | open xydata | runscript |
|---|---|---|---|
| 4.13.0.1 | 中文相对名启动前拒绝（已有失败） | 同左 | 保留已有许可 |
| 4.10.0.1 | 中文相对名启动前拒绝（已有失败） | 同左 | 中文相对名启动前拒绝（已有失败） |
| 未知、资源冲突、只有路径提示 | 未验证，要求显式 ASCII 别名 | 同左 | 同左 |

策略集中于 native/versions.py 的独立操作表，不把单次实测外推成整个版本族的支持保证。
未知构建提示 `unverified build/operation`，不称其原生不支持；无安装信息时也不会猜版本。
只有三个实际读取命令的非 ASCII **相对**参数受此策略约束；不按扩展名判断读者。
绝对 import/XY 路径、未引用的依赖、Python/SCL 内部代码、runpython、命令注释不受此新限制。
已有脚本引用安全约束仍保留（例如 runscript 原来就必须使用声明的相对路径）。
这不是任意用户脚本的静态安全分析，不解析运行时生成的命令。

复用 program_bundle 的字面量引用遍历，包括嵌套 open/openc command、分号和引号。
prepare 在创建作业前检查；execute 在源/合同/依赖身份重验后、批处理作业创建或 session dispatch 前重新检查。
执行不信任合同中的旧引用图或能力信息，也不因省略依赖清单而放行已知读者的中文相对名。
prepare 使用当前配置的安装；session 执行使用会话自身记录的可执行文件，ASCII 程序无需读版本信息。
因此默认安装未验证时，中文 SCL 也不能仅凭未来可能选择的 4.13 会话提前获准准备；可选择对应安装准备或使用显式别名。

## 用户显式别名

依赖声明可使用 `{"path": "中文 源文件.txt", "name": "input data.txt"}`。
命令必须相应写成 `open xydata "input data.txt"`，曲线引用仍须写成 `show "input data.txt~1" 0`。
import/runscript 同样使用声明中的 ASCII 名。工具不猜别名，不替换用户脚本，不修改源文件或编码。
冻结的 bytes、size、SHA256、source、输出合同及 bundle identity 沿用现有实现。
源文件准备后改变不会改动冻结副本；准备副本或合同改变仍拒绝执行。
上述别名行为仅有离线合同验证，**本轮没有新增原生兼容性结论**。

## 离线红绿与复现

基线 main 为 `e41cf65551274c496f0bb1802f952d1a30e024b2`。
仅加入原创 tests/test_native_filename_guard.py 的首七例、未改运行时：**7 failed**。
五例证明准备未拒绝已有失败名，两例证明旧合同会到达假 batch/session 执行器。
加入三个运行时文件的修复后，同一组 **7 passed**。
后续扩展断言覆盖 ASCII/空格别名、UTF-8 字节、4.13 SCL、未知资源、注释和绝对路径边界、嵌套/分号、缺失清单、大小写碰撞、穿越、源/合同篡改、会话版本、产物缺失/伪造及作业身份。

相关测试命令（既有环境，不新建或安装环境；未跑本地全量）：

```text
python -m pytest tests/test_native_filename_guard.py tests/test_native_filename_guard_native.py tests/test_program_bundle.py tests/test_programs.py tests/test_program_context.py tests/test_native_commands.py tests/test_scl_path_literals.py tests/test_version_profile_calls.py tests/test_version_resources.py tests/test_batch_input_staging.py -q -p no:cacheprovider --basetemp <fresh-task-temp>
python -m ruff check . --no-cache
lint-imports --no-cache
python tools/validate_tasks.py
python tools/gen_docs.py --check
python tools/validate_tool_migration.py
python tools/fetch_corpus.py --check-registry
python tools/check_doc_links.py
git diff --check
```

既有全依赖 Python 3.11、全依赖 Python 3.12、最小依赖环境分别 **207 passed / 4 skipped**。
跳过项为三个显式 opt-in 原生用例及本机未开放符号链接创建的产物逃逸测试；没有失败转 xfail。
Ruff 通过；import-linter 3 kept / 0 broken；任务、生成文档、153 工具迁移、语料登记和链接校验通过。
正式提交的托管 CI 链接在实现 PR 中记录。基线 main 的正式 CI 五绿不代替实现提交的 CI。

首轮正式 PR CI 在 Windows cp1252 环境发现新测试的两处合同 JSON 读取遗漏显式 UTF-8，导致三个参数用例解码失败。
修复测试的 UTF-8 读写后重新验证；未改运行时策略，未以重跑掩盖失败。最终 CI 以修复后的精确提交为准。

## 原生与剩余缺口

本轮原生调用数 **0**，没有申请或占用 G01 lease，没有 GUI/UU/求解器操作。
新 tests/test_native_filename_guard_native.py 默认跳过；显式 --run-native 仍须在获准窗口内使用。
它提供未来显式 ASCII 别名的三条正向对照，保留导入保存重开后的 9 节点和 ID1001 坐标 (7,8,9)、XY 三点 (0,0)/(1,2)/(2,4)、SCL 8 节点/字节/产物归属断言。
每版本预计 import 3 次进程调用、XY 1 次、SCL 1 次；正式申请前须再核对调用数、构建、配置/源族哈希与退出检查。
默认跳过和 mock 成功不计为上述原生验收通过；中文原名失败、GUI/Movie、KI-049 无别名中文 job 根和图形回调缺口均未关闭。

programs.py 与 PR #88 的潜在交集已逐 hunk 比较：本轮仅两处引用校验调用，未触及其宏参数/文档修改，未合入或修改旧 PR 头。
tasks、看板、安装配方、service/config、model/results 等白名单外文件均未改动。
仓库外 dated scratch 保留本轮红绿日志、校验输出及 PR 正文以供追溯，不入 Git；工作树根无新增条目。
AO 会话 API 未提供 Codex GUI 的真实项目归属；保留待归类，不以工作目录代替确认。
