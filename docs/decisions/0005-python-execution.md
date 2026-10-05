# A04：应用内 Python、依赖和数组产物

2026-10-05，归属 A04。I02 合同字段不变。

`run_script(language="python")` 执行 LS-PrePost 内置 Python，parameters
作为独立 JSON 数据提供给脚本的 PARAMETERS 全局变量，不替换源代码。
执行身份包含参数、原文和声明的依赖文件；依赖继续通过原有 bundle 的
路径、大小、哈希和模块缓存隔离检查。Python 代码中的双花括号保持原样。

Python 异常返回完整 traceback，包括依赖文件栈。结果同时保留原生回显。
数组通过声明 kind=npz 输出；响应仅带路径、SHA256 和每个数组的 shape、
dtype、内存字节数、排列顺序。验证 NPY 1/2 头、载荷长度及 ZIP CRC，
按块读取，避免解压后的整个数组占用 MCP 内存；拒绝 pickle/object 数组。
结构核验不等于工程数值正确性判断。

## L2 证据

`tests/test_script_python_native.py` 在真实内置 Python 中调用 DataCenter
和 LsPrePost，加载 helper.py 及子目录 JSON 文件，接收含引号/换行的数据
参数，生成 1000000×2 float64（16000000 字节）数组并输出 NPZ。
外部独立检查 shape/dtype、首尾值及响应体大小；修改 helper 后再次执行，
核对新依赖异常的完整文件栈，确认没有复用旧模块。

- 4.13.4：batch 与 queue session 通过。
- 4.10：标量 SDK + 参数/依赖/NPZ/异常子集通过，未放宽旧版向量 ABI 限制。
- A03 的原生 SCL 坐标 CSV 与等价 DataCenter Python 输出继续作为交叉证据。
- 原始日志、大数组和本机路径留在外部原生测试目录。
