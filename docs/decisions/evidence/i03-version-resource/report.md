# I03：可执行文件版本资源与兼容性门禁

2026-10-06。Windows 优先读取 FileVersion、ProductVersion 字符串及固定版本信息，
路径提示仍返回供比较；缺失资源/非 Windows 的退路明确标为 path_hint，runtime_verified 始终为 false。
元数据不是签名认证，也不是实际 GUI/原生完整构建号的证明。

实际发现：本机 4.10 的 FileVersion / ProductVersion 字符串为 4.10.0.1，固定版本却为 4.9.0.1。
一致的版本字符串优先，保留 resource_conflict。任一读取到的版本项标明 4.11 时拒绝，
两个版本字符串不同、配置标签与检测结果冲突、资源标识其他产品时均在启动前拒绝。
辅助模块随独立 bridge 一起复制，保留 Python 3.6 语法；DPF Server 7.1 门槛也移到版本表。

## 实测

- 4.13、4.10、4.8 各一份本机二进制副本：改名为无版本、4.11、4.13 文件名后仍返回原版本族。
- 4.10/4.8 改名后依旧拒绝未经验证的队列模型身份能力；原文件大小、时间戳不变。
- 首轮 4.13 / 4.10 各 7 passed（6 项批处理 + 1 项资源检查），4.8 为 1 项只读资源检查，没有运行 4.8 原生任务。
- 补文件身份缓存键后，最终代码在 4.13 / 4.10 各 6 项批处理回归再次通过。
- 12 项版本资源专项回归通过，包含同大小同时间戳的文件替换、重命名、冲突、4.11 拒绝；独立 bridge 的隔离加载与兼容语法测试也通过。
  4.11 拒绝用的是合成元数据，没有启动被排除的版本。

实际 revision `e36e0a65a5e007c0257e28321302e9fd13222d9c`。
首轮未提交 diff SHA256 `f8330f8c18485894b383083df5b7f85b4445a890dda9f825d7dbe4b12509db13`；
最终 diff SHA256 `c5b5f100a53802ea9fad7c7d76fbf12339b50ba719c4204d063c9249dd5cd98e`。
[证据 JSON](evidence.json) 保存各轮实际版本、冲突字段、逐项结果和报告指纹。
二进制副本仅留在仓库外测试目录，未提交；原生功能范围仍按各版本实际回归证据，I03 保持 partial。

只读 API 依据：[GetFileVersionInfoW](https://learn.microsoft.com/en-us/windows/win32/api/winver/nf-winver-getfileversioninfow)、
[VerQueryValueW](https://learn.microsoft.com/en-us/windows/win32/api/winver/nf-winver-verqueryvaluew)。

## 第六轮重挂后的引擎补验

在包含 main、进程回收、日志解码和版本资源修复的干净 c1f3fa0 提交上，
4.13/4.10 各 6 项批处理回归通过；五入口完成模型/产物验证，无效命令仍显式失败。
restack_runs 追加实际 revision、working_tree_dirty=false、原始报告哈希与框架执行身份。
本轮没有 GUI/UU 运行，也没有把历史 4.8 资源检查扩写成 4.8 的引擎实测。
