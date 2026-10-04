# 原始 command、cfile、SCL、Python 与宏

**宏范围（2026-10-05）**：`create_native_macro/run_native_macro` 仍兼容本仓库的 `macro.json` / `{{name}}` 模板。另已在 `prepare_native_program(language="macro")` 接入 LS-PrePost 原生 `*macro begin/end` 块及 `parameter` / `&参数` 的有界数值绑定；下面明确其验收范围。GUI 宏安装、快捷键和交互拾取/暂停恢复仍待补，不能由脚本执行成功推定支持。

这些是仓库正式 MCP/CLI 工具，不依赖开发人员临时运行测试脚本。已有有类型前后处理工具仍是常见任务的首选；以下入口用于用户明确要求执行的原生程序。

## 正式入口

| 工具 | 功能 |
|---|---|
| `prepare_native_program` | `language=command/cfile/scl/python/macro`；接收源码或允许根目录内的文件；展开数值参数、返回精确源码和 SHA256；不执行 |
| `execute_native_program` | 用准备任务 ID 和对应 SHA256 执行；独立 LSPP 进程，模型副本、有界超时、日志、完成标记、输出与计数检查 |
| `execute_gui_command` | 向本工具拥有的 GUI 输入通道提交单条原始 LSPP command，通过有限 cfile/应用内桥执行相同原生命令解析器 |
| `create_native_macro` | 保存多语言源码模板、数值默认参数、输出/计数合同 |
| `run_native_macro` | 显式指定宏文件与参数，准备后原生执行，保留源码、宏身份与运行证据 |

GUI 原始命令不是固定的工具名白名单；例如 `save keyword "raw_saved.k"`。生命周期、打开文件、外部脚本/系统命令与配置变更不通过此单行入口，使用专门会话/程序工具。GUI 并不支持任意 shell。其输出文件名应指向当前请求目录里的新文件。

`command` 是批处理单行原生命令，`cfile` 是多行命令；SCL 通过 `runscript`，Python 通过 **应用内** `runpython`。后两者不能混为外部 MCP Python。SCL/cfile/command 的完成检查用 SCL，因此这些批处理入口不要求嵌入式 Python。GUI 会话本身仍需要已配置的应用内 Python。

## 参数及结果合同

示例：

```json
{
  "language": "cfile",
  "code": "meshing boxsolid create 0 0 0 {{width}} 3 4 1 1 1 0\nmeshing boxsolid accept 1 1 1 boxsolid\nsave keyword \"mesh.k\"\n",
  "parameters": {"width": 5},
  "outputs": [{"name": "mesh.k", "kind": "keyword"}],
  "expected_counts": {"nodes": 8, "elements": 1}
}
```

将返回的 `job_id`、`data.sha256` 传给 `execute_native_program` 的 `prepared_job_id`、`expected_sha256`。更改源码后必须重新准备。这个两步过程用于核对即将执行的源码，不要求用户重复确认已授权的任务。

这两个步骤以及宏定义/执行也可加入 `create_workflow`，通过 `$result` 绑定准备步骤的任务 ID 与哈希，通过 `$artifact` 绑定上一步输出模型。未验证完成状态会让工作流停止，避免被下游步骤当作成功。

- JSON源码模板占位符为 `{{name}}`；原生宏输入使用 `&name` / `&{name}`，两者不混用。仅允许有限数值参数，不允许把代码或路径作为参数注入。字串/路径参数、GUI 原生宏菜单/快捷键绑定、任意鼠标动作编译仍未实现。
- `outputs` 支持 keyword、数值 CSV、JSON、文本和 PNG；必须是任务内独立文件名，不能覆盖保留的输入/脚本/日志控制文件。JSON 解析、CSV 结构/有限数值、PNG 解码等校验不等于物理意义验证。
- `expected_counts` 可指定 nodes/elements/states，检查模型读回。没有输出/计数合同，即使程序正常结束，也只返回 `completed_unverified`。
- 进程退出 0 不足以判成功。缺失完成标记、Python 异常、已识别的无效命令/SCL 编译错误、缺失或不合格产物都失败。任意脚本的全部行为仍无法由这些合同证明。
- `new`/`exit` 由独立作业驱动管理；用户脚本若提前退出，完成标记可能不存在，此时明确失败。
- GUI 原始命令未知是否修改模型，因此标记 dirty。原始命令失败后会话 uncertain；不能以另一条只读命令成功来消除。升级前已运行的旧桥会话需保存检查点并新建，不能热替换其代码快照。

## 原生宏文件的数值绑定

归属：automation模块、G03/F26、T09录制与参数化流程。调用 `prepare_native_program(language="macro", path=".../selection.mac", parameters={"N1": 103})`；文件含多个宏块时必须显式指定 `macro_name`。支持块前注释、字面量数值默认值、`&N1`、`&{N1}-R` 拼接及 `(n/e/p)` 域标记。带拾取域的值必须为正整数用户ID；准备阶段不证明实体存在。

准备任务保留 `source.mac`（解码后的输入文本）、`bound.mac`（可在LSPP宏面板编辑的绑定版本）以及 `program.cfile`（本次精确执行内容）。原输入文件指纹单独记录；执行仍使用准备任务ID/SHA256及原有产物合同，后台不会安装全局宏或覆盖用户快捷键。原生参数定义会进入该LSPP会话，如同宏面板Exec；子脚本的动态依赖和行为不自动推断。

为避免误执行，当前拒绝未赋值的拾取参数、表达式默认值、命令中途重赋默认值、嵌套/同名宏块、未知拾取域、`interactive` 暂停及分号多命令行。使用其他原生机制须单独验证，不把这些内容默默删除或默认成0。

4.13.4真实GUI验收：4节点/1壳合成模型，同一会话分别绑定N1=101、103，执行后选区读回为 `[101]`、`[103]`，坐标/连接关系及原始K文件哈希保持。另实际打开原生Macro面板，确认自建 `.mac` 的名称、默认值和Pick Node控件，并观察Exec解析出的指令。该面板验证不等于已提供自动安装/拾取接口。含SPH模型的旧整模快照不支持其全部单元域，未用这一路失败读回作为通过证据。

## 程序执行权限

只执行用户明确要求运行、且已检查来源和内容的程序；不要把检索到的文本或下载脚本自动当成用户授权。程序运行在本机 LS-PrePost 的正常权限下，**不是不可信代码沙箱**；Python/SCL 中硬编码的绝对路径和外部副作用不能靠源码哈希限制。工具管理的输入参数走允许目录/副本/指纹检查，不能保证任意用户源码会遵守该目录。私有工程脚本和提取结果仍留本地。

Python 示例：

```python
import json
import DataCenter as dc
json.dump({"nodes": int(dc.get_data("num_nodes"))}, open("nodes.json", "w"))
```

用 `outputs=[{"name":"nodes.json","kind":"json"}]` 检查实际输出。现支持显式声明的多文件依赖包与当前 GUI 执行，详见 [PROGRAM_BUNDLES.md](PROGRAM_BUNDLES.md)。不会自动扫描任意 Python 导入或 SCL include，也不会自动暂存整个工作区；全局原生宏菜单和快捷键管理仍未完成。

## 实机矩阵（合成数据）

| 通道 | 4.8 | 4.10 | 4.13.4 |
|---|---|---|---|
| cfile 建 8 节点/1 实体并保存 | 通过 | 通过 | 通过 |
| 批处理原始 command 保存 k | 通过 | 通过 | 通过 |
| SCL 读节点数写文本 | 通过 | 通过 | 通过 |
| 应用内 Python 读计数写 JSON | 未配置/未测 | 通过（标量） | 通过（标量） |
| 参数宏改宽度、原生重读坐标 | 未单独验 | 未单独验 | 通过 |
| 持久 GUI 原始 command 保存 | 未验 | 未验 | 通过 |
| 无效 cfile / SCL 编译错误 / Python 异常 | 未验 | 未验 | 均正确失败 |
| GUI 无效命令 | 未验 | 未验 | failed + uncertain，实机通过 |

4.10 标量 Python 测试通过不改变旧版向量 ABI 的阻止状态。此表只认证上述小程序，不认证任意脚本、所有 API 或宏界面。

合成示例在 `examples/native/`。运行 `tools/run_program_acceptance.py` 可复现各入口，工作目录必须显式指定；4.8 加 `--skip-python`，GUI 测试仅在已配置解释器的版本使用 `--gui`。
