# I01：4.10 INCLUDE 漏读必须失败

干净提交 `4dfc675a1ae64619f1767c026be179fa4c9f4cb2` 上执行两个 4.10 无图形原生回归，**2 passed**。相对 INCLUDE 的实际作业为 failed，并保留 `Error - Include File first.k Not open` 诊断；绝对路径对照成功读入 9 个节点。源文件字节与目录清单未变。Git revision、空 diff SHA256、源码 Git blob/LF 身份及逐例状态见 [evidence.json](evidence.json)。

原 ce42 探针也已执行，H0 由不完整的 succeeded 改为 failed；R1/R2 的受控 cwd 文件对照仍成功，未把所有包含 INCLUDE 的作业一律拒绝。原始报告保留在外部证据目录。

边界回归覆盖外部 UTF-16 / 缺失引用 / 二进制内容优先报 outside、cwd 拒绝后 manifest 为 failed、行首空白和 *END 后 INCLUDE 拒绝。ce40 E5/E6/E7 全为 outside；B5/B7/B11 在启动前拒绝。带引号文件名的兼容性变化已登记。共享引用预算仍等待 Claude 的公共接口；4.13 未就本改动重跑。
