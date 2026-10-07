# G01 视图控制覆盖矩阵

`set_view` 是 G01 目标工具，返回 JobResult/v1。实现见 `src/ls_prepost_mcp/view_tools.py` 和 `src/ls_prepost_mcp/view_state.py`；旧入口 `set_gui_display` 保持原签名和行为至 v0.6。

## 语义

- 命令顺序：标准视图 → 投影 → 全局 X/Y/Z 增量旋转 → fit（`ac`）→ 绝对 zoom → 绝对 pan，复用 `gui_controls.camera_commands` 的类型和边界（zoom 0.01..100，pan ±100，角度 ±360）。
- `zoom_scale` 是原生绝对缩放，不是倍数；"放大 2 倍"必须给出绝对值。`pan_xy` 是原生视图偏移，不是模型长度。
- 只有显式标准视图和投影的请求标记为 `replayable`；fit 依赖当前显示内容，标记为 `content_dependent`。
- `context=session` 只使用已存在的会话，经既有 `gui_display` 路由下发，从不启动会话。返回 `camera_state=applied_unverified`：没有相机矩阵读回。
- `context=batch` 默认只生成经审阅的 cfile/PNG 程序（`prepare_native_program`），不启动原生进程，结果为 `unverified`/`preparation`。显式 `execute=True` 时经既有 `execute_native_program` 以 `graphics=False`、`c= -nographics` 启动一个独立进程（从不启动 GUI 或会话），要求执行成功、恰好一份通过校验的 PNG、暂存输入哈希等于准备时的模型哈希，否则 `failed` 且不保存预设；成功为 `succeeded`/`execution`，`camera_state=applied_unverified`。每次批处理都是新进程，视图从打开的模型开始，不承接前一次调用。
- 命名预设（`ViewPreset/v1`）只保存可重放请求，`kind=request_preset`、`native_camera_captured=false`。绑定会话 ID + 模型代次 + 可执行文件哈希，或批处理输入字节哈希；原子创建、名称大小写不敏感且不覆盖；损坏、改写、模式版本或绑定变化均拒绝。
- `center_on` 按核心 `Selector` 合同校验后以 `unsupported` 失败关闭，不下发命令、不改选区或显隐。
- 像素一致性：`compare_png_pixels` 对解码后的 RGBA 做逐像素零容差比较，同时记录文件和像素哈希；尺寸不同或非 PNG 不判一致。

## 验收格

| 验收项 | 离线（L1） | headless 4.13（批处理） | GUI 会话 | 状态 |
|---|---|---|---|---|
| 标准视图 | 命令/顺序/拒绝 | front、isometric 执行成功，PNG 可重复 | 待授权窗口 | headless 已执行；无相机读回 |
| 缩放、平移 | 绝对语义与边界 | zoom 2、pan 0.1 -0.05 执行成功，PNG 可重复；top+zoom 0.5 产生不同画面 | 同上 | headless 已执行；无相机读回 |
| 绕轴旋转 | X→Y→Z 顺序 | rx 15、rz -30 执行成功，PNG 可重复 | 同上 | headless 已执行；无相机读回 |
| fit | `ac` 位置，content_dependent | isometric/perspective 后 `ac` 可重复，但画面仍有部件超出边框 | 同上 | 可重复；fit 是否框住全部内容未证实 |
| 居中到 Selector | 合同校验 + 失败关闭 | 未执行 | 未执行 | gap：无已证实命令 |
| 命名视图保存 / 恢复 | 请求预设的身份、碰撞、损坏、绑定 | 预设 save→扰动→restore，restore 与 save 0 差异像素 | 待授权窗口 | 仅请求预设重放；真实相机捕获/原生命名视图为 gap |
| 两次出图像素一致 | 零容差比较器 | A、B 各两次独立进程 0 差异像素 | 同一会话两次渲染用例，待授权窗口 | headless 批处理已满足；会话未测 |

## headless 4.13 证据（2026-10-08，lease G01-001）

[headless-4.13.json](headless-4.13.json)：4.13.0.1，`c=<作业>/commands.cfile -nographics`，graphics=false，原创 M0 合成关键字夹具，7 个串行独立进程，均退出码 0、未超时、诊断为空，运行后无残留 LS-PrePost 进程。prepared 与实际执行的 program.cfile 哈希一致，暂存输入哈希等于源哈希。PNG 为 3300×2550 RGB，比较解码后 RGBA 像素：A1/A2、B1/B2、预设 save/restore 均 0 差异像素；对照组扰动 5,031,517 像素不同，说明比较器能检出差异。

结论只覆盖“同一请求在新进程中重放得到相同像素”，不证明相机矩阵、原生命名视图或 fit 语义。仓库内的复现入口为 `tests/test_view_native.py` 的 headless 用例（需 `--run-native --native-executable`）；该入口本身尚未在 lease 下运行，本次证据来自同一路由 `set_view(context="batch", execute=True)` 的 lease 探针。

## 剩余缺口

- 原生相机矩阵读回、真实命名视图捕获/恢复（不得猜命令语法）。
- Selector 中心到相机目标或选中范围 fit 的已证实原生命令。
- fit 在 perspective 下未框住全部部件，语义未证实。
- 4.10 headless、GUI 会话用例（需一次授权窗口）、UU 远程均未测。
