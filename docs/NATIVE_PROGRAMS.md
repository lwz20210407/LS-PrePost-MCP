# 原始 command、cfile、SCL、Python 与宏

这些是仓库正式 MCP/CLI 工具，不依赖开发人员临时运行测试脚本。已有有类型前后处理工具仍是常见任务的首选；以下入口用于用户明确要求执行的原生程序。

## 正式入口

| 工具 | 功能 |
|---|---|
| `prepare_native_program` | `language=command/cfile/scl/python`；接收源码或允许根目录内的文件；展开数值参数、返回精确源码和 SHA256；不执行 |
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

- 宏占位符为 `{{name}}`，本版仅允许有限数值参数，不允许把代码或路径作为参数注入。字串/路径参数、GUI 原生宏菜单/快捷键绑定、任意鼠标动作编译仍未实现。
- `outputs` 支持 keyword、数值 CSV、JSON、文本和 PNG；必须是任务内独立文件名，不能覆盖保留的输入/脚本/日志控制文件。JSON 解析、CSV 结构/有限数值、PNG 解码等校验不等于物理意义验证。
- `expected_counts` 可指定 nodes/elements/states，检查模型读回。没有输出/计数合同，即使程序正常结束，也只返回 `completed_unverified`。
- 进程退出 0 不足以判成功。缺失完成标记、Python 异常、已识别的无效命令/SCL 编译错误、缺失或不合格产物都失败。任意脚本的全部行为仍无法由这些合同证明。
- `new`/`exit` 由独立作业驱动管理；用户脚本若提前退出，完成标记可能不存在，此时明确失败。
- GUI 原始命令未知是否修改模型，因此标记 dirty。原始命令失败后会话 uncertain；不能以另一条只读命令成功来消除。升级前已运行的旧桥会话需保存检查点并新建，不能热替换其代码快照。

## 权限与输入

只执行用户明确要求运行、且已检查来源和内容的程序；不要把检索到的文本或下载脚本自动当成用户授权。程序运行在本机 LS-PrePost 的正常权限下，**不是不可信代码沙箱**；Python/SCL 中硬编码的绝对路径和外部副作用不能靠源码哈希限制。工具管理的输入参数走允许目录/副本/指纹检查，不能保证任意用户源码会遵守该目录。私有工程脚本和提取结果仍留本地。

Python 示例：

```python
import json
import DataCenter as dc
json.dump({"nodes": int(dc.get_data("num_nodes"))}, open("nodes.json", "w"))
```

用 `outputs=[{"name":"nodes.json","kind":"json"}]` 检查实际输出。本版为单文件程序；额外模块、复杂 include 和任意外部依赖应先明确配置，不能假定被自动暂存。

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
