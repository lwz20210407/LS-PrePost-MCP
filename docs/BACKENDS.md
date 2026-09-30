# Python后端与语义合同

| 后端 | 实际作用 | 运行环境 |
|---|---|---|
| LS-PrePost | 软件模型、cfile、SCL、应用内Python和渲染 | 4.8/4.10/4.13各自安装；按功能实测 |
| LASSO | d3plot/binout读取、节点向量与曲线 | 外部MCP的`results`可选依赖 |
| LS-Reader | 独立结果读取与交叉核验 | `LSPP_LSREADER_PYTHON`指定的匹配ABI解释器 |
| PyDYNA | Deck清单、MAT_001片段、材料修改、导出后重新导入核对 | `pydyna`可选依赖，目前验证0.12.1 |

安装外部依赖：

```shell
uv sync --extra dev --extra results --extra pydyna
```

LS-Reader由用户按分发说明配置在自己的Python环境。本仓库不复制其DLL/pyd。设置示例：

```powershell
$env:LSPP_LSREADER_PYTHON = 'C:\path\to\lsreader-python\python.exe'
```

工作进程只接受固定的inspect/nodal请求，输出写到当前任务目录；ABI异常和崩溃不会直接结束MCP宿主。

## 统一约定

- 工具公开state从1开始，LS-Reader内部ist转换为state-1。
- 输出的node_id是数据库中的用户编号，不使用数组下标代替。
- 数值结果明确backend，不让外部读取器冒充LS-PrePost原生执行。
- 坐标、位移、速度分别定义；位移参考为初始几何，单位不自动推断。
- LS-PrePost字段/壳层/积分点与LS-Reader枚举属于不同接口，不能直接复用数字。
- 当前binout工具只接受单个字面文件；发现MPP多分片时拒绝不完整提取。文件名中的方括号等会转义，不作为任意glob解释。

## LASSO坐标语义修正

本次使用的LASSO 2.0.4以`node_displacement`命名d3plot状态坐标数组。其绘图代码也将此数组直接作为节点坐标使用。因此位移输出必须减去`node_coordinates`，速度不作此处理。

初次跨后端测试发现未做转换时，初始状态被错误报告为非零位移。修正后，选取具有非零运动的一个节点，在三个状态上与LS-Reader的`D3P_NODE_DISPLACEMENTS`逐列对照一致。单元测试还使用非零初始坐标的合成数据防止回归。该对照验证读取语义一致，不等于证明模型物理正确。

## PyDYNA资料迁移

依据：[官方仓库](https://github.com/ansys/pydyna)、[官网](https://dyna.docs.pyansys.com/version/stable/)、[Deck API](https://dyna.docs.pyansys.com/version/stable/api/ansys/dyna/core/lib/deck/index.html)和版本相符的本地Agent指南。

本地资料同时包含旧0.4系列源码/`pre`示例和新Deck/keywords案例。已经盘点入口并精读最小deck、Taylor-bar构造及单单元示例；未把旧示例整体当作0.12.1可执行实现，也未运行求解或优化。

当前材料修改仅支持唯一MAT_001/MAT_ELASTIC且无include的独立deck。输出总是新文件并重读字段验证；复杂include树重写、其他材料模型、边界/接触以及求解器功能仍按路线扩展。
