# Q08 XYPlot 出图：批处理原生验收（2026-10-07）

工具：`render_xyplot`。逐个作业的参数、哈希与数值核对见 [evidence.json](evidence.json)。曲线数据是测试里生成的原创 CSV；作业目录、PNG 和原生日志都留在仓库外的 `--native-output` 中，这里只记录相对路径和 SHA256。

## 运行方式

- 源码：提交 `a1f386b`，工作树干净。
- 命令：`pytest tests/test_native_xyplot_batch.py -m native --run-native --native-strict --native-executable <LSPP> --native-output <新外部目录>`。
- 版本：LS-PrePost 4.13.4（4.13.0.1）与 4.10，两个版本各 3 个用例全部通过，共 12 个作业。
- 通道：BatchEngine `c=<cfile> -nographics`，不打开可见 GUI，不使用会话。每个作业的返回码为 0，原生诊断为空。
- 本机 4.13 可执行文件在注册表兼容性设置中带 `RUNASADMIN`，Python `CreateProcess` 会报 WinError 740。测试进程设置了 `__COMPAT_LAYER=RunAsInvoker`，没有修改注册表。

## 验收对应

| 验收（tasks.yaml） | 证据 |
|---|---|
| 最多 10 条曲线同图；图例、坐标轴标题与范围、对数轴可设 | 3 工况力-位移图（不同长度、不同 X 网格、迟滞回转），图例标题 `Load case`，x 0–4、y 0–25；10 条曲线 Lin-Lin、Log-Log、Log-Log 加 x 0.1–10 / y 0.1–1000；单曲线 Log-Lin（Y 对数）与 x 0.5–2.5。线性与对数、加范围与不加范围的 PNG 像素互不相同。11 条曲线、单位不一致、对数轴上非正数据或下限在进入原生前拒绝（单元测试）。 |
| PNG 与同时导出的 CSV 数值一致 | PNG 与 `native.xy` 来自同一原生绘图窗口，读回在打印 PNG 之后。`curves.csv` 每条曲线与原生读回逐点一致（rtol 5e-11，atol 0），并与输入的 float32 存储值完全相等；manifest 记录三者 SHA256，测试重新计算后一致。 |
| 批处理上下文可用（不依赖可见 GUI），依据 E5 结论 | 全部作业 `visible_gui=false`、`route=batch`，在 4.13 与 4.10 的 `c= -nographics` 下完成。 |

## 原生行为记录

- `xyplot <id> axes` 的记号顺序是 `<Y 刻度>-<X 刻度>`：`Lin-Log` 使 X 轴取对数，`Log-Lin` 使 Y 轴取对数。
- 范围命令为 `xyplot <id> xmin|xmax|ymin|ymax <值>`，在 `axes` 之后发送。线性轴会把范围外扩到相邻刻度（例：ymax 23 显示为 25）；对数轴会外扩到十进位附近，非正下限会被替换。工具只发送请求的范围，不读回实际显示范围，manifest 的 `range_policy` 写明了这一点。
- 3300×2550 是 `-nographics` 下 `print png` 的输出尺寸。

## 未覆盖

- 会话通道（传 `session_id`）复用已有的 `export_gui_curve_plot` 流程，这次没有安排可见 GUI 时间窗，未做原生回归。
- 锁屏、UU 断开等远程条件未测；E5 的远程格仍在 I04。
- 不对 PNG 做 OCR，不核对实际显示的坐标范围；曲线样式（颜色、线型、符号）不可设。
