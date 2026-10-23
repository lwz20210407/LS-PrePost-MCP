# Q07 原生 SAE 滤波对照（review02）

这是差异取证，不是滤波等价性通过；Q07 保持 partial。

## 方法与口径

官方 [XYPlot 说明](https://lsdyna.ansys.com/xyplot/) 提供滤波类型、时间单位和频率设置。
批处理候选命令先在拥有目录中实测；正式用例固定 `xyplot 1 filter sae <CFC> sec|msec 0`，
末尾0表示本次不要求零起点。该语法以实际命令、输入/输出和程序版本绑定，不外推其他版本。

固定输入：4001点，20kHz，0–0.2秒，`20*sin(2*pi*5*t)+0.5*sin(2*pi*3000*t)`。
先不滤波导出 control.xy，逐值验证导入的 float32 存储及原始顺序；再执行 SAE60/600，
分别以秒/毫秒标签运行，完整导出 filtered.xy。时间坐标及样本数不变，源文件字节不变。
Python 使用同一导入后的 float32 纵坐标和声明的均匀原始时间网格，独立计算 odd/constant。
逐样本容差固定 rtol=2e-5、atol=1e-6*max|reference|；同时记录两端和中间2001点误差。
不剪掉端点换取通过，不拟合参数，不修改现有 SAE 公式来迎合本次输出。

## 记录

正式运行记录、Git revision、产品/test blob、程序/输入/产物哈希见 [evidence.json](evidence.json)。
pytest 的 xfail 在这里明确表示原生与 Python 默认结果不一致，不是通过数。

干净 d5bc5c2 上4.13、4.10各4个进程正常完成，控制读回均通过，但8项滤波等价性全部不通过。
SAE60 的 odd 全段最大绝对误差约1.09、中段约0.0184；SAE600 分别约0.136、0.00344。
这些数值只描述本波形，不是其他模型的误差上界。

| 批次 | 结论 | 有效性 |
|---|---|---|
| 探索 r01 | help命令不可用且临时XY格式不正确；不是功能判定 | 已被取代的试验驱动 |
| 探索 r02 / 4.10 SAE600 sec | 控制读回正确，odd/constant 均有差异；非正式验收 | 历史探索 |
| pytest 固定波形 | 以 evidence.json 中干净提交运行记录为准 | 当前取证 |
| Butterworth / 实际工程波形 / GUI | 未测 | 未验证 |

重跑命令（分别选4.13和4.10，输出在仓库外）：

```text
python -m pytest tests/test_curve_filter_native.py -m native --run-native --native-strict --native-executable <selected-executable> --native-output <external-scratch>/q07-sae-reference -q
```

不需要可见 GUI 或 UU 断开；所有原生进程按版本串行。原始日志、配置和程序绝对路径不入仓库。
