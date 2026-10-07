# G01 视图控制覆盖矩阵

`set_view` 是 G01 目标工具，返回 JobResult/v1。实现见 `src/ls_prepost_mcp/view_tools.py` 和 `src/ls_prepost_mcp/view_state.py`；旧入口 `set_gui_display` 保持原签名和行为至 v0.6。

## 语义

- 命令顺序：标准视图 → 投影 → 全局 X/Y/Z 增量旋转 → fit（`ac`）→ 绝对 zoom → 绝对 pan，复用 `gui_controls.camera_commands` 的类型和边界（zoom 0.01..100，pan ±100，角度 ±360）。
- `zoom_scale` 是原生绝对缩放，不是倍数；"放大 2 倍"必须给出绝对值。`pan_xy` 是原生视图偏移，不是模型长度。
- 只有显式标准视图和投影的请求标记为 `replayable`；fit 依赖当前显示内容，标记为 `content_dependent`。
- `context=session` 只使用已存在的会话，经既有 `gui_display` 路由下发，从不启动会话。返回 `camera_state=applied_unverified`：没有相机矩阵读回。
- `context=batch` 只生成经审阅的 cfile/PNG 程序（`prepare_native_program`），不启动原生进程，结果为 `unverified`/`preparation`。headless PNG 渲染尚未取得 lease 实测。
- 命名预设（`ViewPreset/v1`）只保存可重放请求，`kind=request_preset`、`native_camera_captured=false`。绑定会话 ID + 模型代次 + 可执行文件哈希，或批处理输入字节哈希；原子创建、名称大小写不敏感且不覆盖；损坏、改写、模式版本或绑定变化均拒绝。
- `center_on` 按核心 `Selector` 合同校验后以 `unsupported` 失败关闭，不下发命令、不改选区或显隐。
- 像素一致性：`compare_png_pixels` 对解码后的 RGBA 做逐像素零容差比较，同时记录文件和像素哈希；尺寸不同或非 PNG 不判一致。

## 验收格

| 验收项 | 离线（L1） | 原生 | 状态 |
|---|---|---|---|
| 标准视图 | 命令/顺序/拒绝 | `tests/test_view_native.py`，待 GUI 窗口 | 未原生验证 |
| 缩放、平移 | 绝对语义与边界 | 同上 | 未原生验证 |
| 绕轴旋转 | X→Y→Z 顺序 | 同上 | 未原生验证 |
| fit | `ac` 位置，content_dependent | 同上 | 未原生验证 |
| 居中到 Selector | 合同校验 + 失败关闭 | 无已证实命令 | gap |
| 命名视图保存 / 恢复 | 请求预设的身份、碰撞、损坏、绑定 | 恢复后像素比较用例，待 GUI 窗口 | 仅请求预设；真实相机捕获为 gap |
| 两次出图像素一致 | 零容差比较器 | 同一会话两次渲染用例，待 GUI 窗口 | 未原生验证 |

## 剩余缺口

- 原生相机矩阵读回、真实命名视图捕获/恢复（不得猜命令语法）。
- Selector 中心到相机目标或选中范围 fit 的已证实原生命令。
- headless 批处理渲染需要总调度 lease 实测；GUI 用例需要一次授权窗口。
