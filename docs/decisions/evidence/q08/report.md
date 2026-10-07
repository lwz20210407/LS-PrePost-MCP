# Q08 XYPlot 出图：批处理原生验收（2026-10-07）

工具：`render_xyplot`。逐个作业的参数、哈希与数值核对见 [evidence.json](evidence.json)。曲线数据是测试里生成的原创 CSV；作业目录、PNG 和原生日志都留在仓库外的 `--native-output` 中，这里只记录相对路径和 SHA256。

## 运行方式

- 源码：提交 `a1f386b`，工作树干净。
- 命令：`pytest tests/test_native_xyplot_batch.py -m native --run-native --native-strict --native-executable <LSPP> --native-output <新外部目录>`。
- 版本：LS-PrePost 4.13.4（4.13.0.1）与 4.10，两个版本各 3 个用例全部通过，共 12 个作业。
- 通道：BatchEngine `c=<cfile> -nographics`，不打开可见 GUI，不使用会话。每个作业的返回码为 0，原生诊断为空。
- 首轮运行时，本机 4.13 可执行文件的注册表兼容性设置带 `RUNASADMIN`（Python `CreateProcess` 报 WinError 740），测试进程设了 `__COMPAT_LAYER=RunAsInvoker`。用户随后移除了该标记；不设这个变量，3 个用例在 4.13 上再次全部通过（审阅复核结果相同）。测试不再需要 `__COMPAT_LAYER`。

## 验收对应

| 验收（tasks.yaml） | 证据 |
|---|---|
| 最多 10 条曲线同图；图例、坐标轴标题与范围、对数轴可设 | 3 工况力-位移图（不同长度、不同 X 网格、迟滞回转），图例标题 `Load case`，x 0–4、y 0–25；10 条曲线 Lin-Lin、Log-Log、Log-Log 加 x 0.1–10 / y 0.1–1000；单曲线 Log-Lin（Y 对数）与 x 0.5–2.5。线性与对数、加范围与不加范围的 PNG 像素互不相同。11 条曲线、单位不一致、对数轴上非正数据或下限在进入原生前拒绝（单元测试）。 |
| PNG 与同时导出的 CSV 数值一致 | PNG 与 `native.xy` 来自同一原生绘图窗口，读回在打印 PNG 之后。`curves.csv` 每条曲线与原生读回逐点一致（rtol 5e-11，atol 0），并与输入的 float32 存储值完全相等；manifest 记录三者 SHA256，测试重新计算后一致。 |
| 批处理上下文可用（不依赖可见 GUI），依据 E5 结论 | 全部作业 `visible_gui=false`、`route=batch`，在 4.13 与 4.10 的 `c= -nographics` 下完成。 |

## 原生行为记录

- `xyplot <id> axes` 的记号顺序是 `<Y 刻度>-<X 刻度>`：`Lin-Log` 使 X 轴取对数，`Log-Lin` 使 Y 轴取对数。
- 范围命令为 `xyplot <id> xmin|xmax|ymin|ymax <值>`，在 `axes` 之后发送。两轴行为不同（4.13 与 4.10 实测一致）：
  - X 轴：线性和对数都按请求精确显示。
  - Y 轴：会被向外扩展。线性 [1.3, 21.7] 显示为 [0, 25]，[-3.3, 7.7] 显示为 [-4, 8]；对数 [0.5, 50] 显示为 [0.1, 100]。加 `xyplot minmaxopt 0/1/2` 不改变结果。
  - 工具只发送请求的范围，不读回实际显示范围。manifest 的 `range_policy` 按轴写明；请求了 `y_range` 时 `warnings` 里写明 Y 范围可能被外扩。Y 轴外扩是否满足“范围可设”，由协调方或用户决定。
- 范围只影响显示：`curves.csv` 是全量数据（manifest 的 `csv_scope`）。每条曲线记录 `samples_in_requested_range`；为 0 时（例：数据 x 在 [0, 3]、请求 x_range=[10, 20]）作业仍为 succeeded，但写 warning，PNG 里可能没有这条曲线。
- 3300×2550 是 `-nographics` 下 `print png` 的输出尺寸。

## 会话通道验收（可见 GUI，2026-10-07）

用户授权的可见窗口，LS-PrePost 4.13.4，`a7c3a3b` 的代码，在自有会话里（`start_gui_session` 打开合成 keyword 模型）调用 `render_xyplot(..., session_id=sid)`：

- 3 工况力-位移曲线（5/4/6 点，含迟滞回转），图例标题 `Load case`，x 0–4、y 0–25：succeeded，产出 `curves.csv`。
- 10 条曲线 Log-Log，x 0.1–10、y 0.1–1000：succeeded。
- 录制一步 Y 对数（Log-Lin，y 1–100）两曲线绘图，`stop_session_recording` 得到单步 `render_xyplot` 工作流；第二条曲线路径参数化后用新 CSV 回放：新绘图窗口，succeeded，样本数 5/4，仍为 Y 对数。
- 回放后重新导出第一张图，与首次 `native.xy` 字节一致；模型和全部源 CSV 字节不变；会话正常关闭。Case A 含 y=0 时开 Y 对数轴，在进入原生前被拒绝。

验收脚本当时在仓库外。现在提交为 `tests/test_native_xyplot_session.py`（标记 `native`、`gui`，需要 `--run-native --native-gui --native-fixture <含 input.k 的目录>`，默认跳过）。提交版改为检查第一张图的 `native.xy` 哈希没变，没有再次原生导出；会话返回结构按审阅第 5 条修改后，这个文件还没有在可见窗口里重跑。L1 模拟会话测试见 `tests/test_xyplot_session.py`。

## 未覆盖
- 锁屏、UU 断开等远程条件未测；E5 的远程格仍在 I04。
- 不对 PNG 做 OCR，不核对实际显示的坐标范围；曲线样式（颜色、线型、符号）不可设。
