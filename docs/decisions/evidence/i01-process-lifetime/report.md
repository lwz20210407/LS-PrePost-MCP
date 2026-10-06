# I01：批处理进程生命周期回归

2026-10-06。旧代码实测在 communicate 阶段注入 KeyboardInterrupt 后，真实父/子进程仍存活；
基线实验最后由测试程序清理了它们。修复后 7 项真实进程回归通过：正常退出、超时、
KeyboardInterrupt、SystemExit、Job 绑定失败、父进程正常退出后的遗留子进程，以及宿主 os._exit。
宿主退出用例同时确认独立进程未被误杀；绑定失败用例确认暂停进程没有执行用户代码。
中断是注入 Python 异常，不宣称覆盖每一种 MCP 客户端取消方式。

LS-PrePost 4.13 / 4.10 后台各 6 项通过：五个批处理入口与零退出码诊断失败回归。
GUI 会话没有改为短生命周期进程，也没有在本次运行可见 GUI 或 UU 验证。

实际 revision `22ce5a59ffa4cabce153a89baa175d87d494c1e1`；修复运行有未提交修改，
diff SHA256 `1cf222e986469f2ce934bb3a7f36a8b836fa0219969e33ed8a1ca686f2cb4070`。
[证据 JSON](evidence.json) 包含基线、逐项结果、原始报告和 JUnit 指纹。

## 生命周期与限制

Windows 使用未命名、不可继承的 Job Object，设置 kill-on-close，暂停创建后绑定并恢复。
正常退出、超时或中断均释放本次 Job；绑定失败直接终止暂停子进程，禁止无监管回退。
POSIX 使用独立进程组，在组长尚未回收时处理取消/超时；主动脱离进程组的后台进程不在该保证内。
所有退出路径关闭管道并限时等待，清理错误保留到原异常注记；普通失败的注记进入 JobResult.warnings。

仍保留一个 Windows 启动窗口：宿主若在 CreateProcess 返回到 AssignProcessToJobObject 之间
被强制终止，尚未绑定的暂停子进程可能遗留。本机 Python 3.11.15 的 lpAttributeList job_list
探针未获得原子 Job 绑定，未把该窗口标为已解决。已验证的宿主强制退出发生在子进程加入 Job 之后。
I01 保持 partial。

实现依据：[Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)、
[进程创建标志](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)、
[扩展限制结构](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information)。

## 第六轮重挂后的原生补验

在不含 Draft #26 的干净 2cdc727 提交上，4.13 和 4.10 各运行 6 项批处理用例并通过：
五个入口的实际模型/产物验证，以及无效命令诊断。不是 GUI 或队列验证。
evidence.json 的 restack_runs 追加实际 revision、working_tree_dirty=false、原始报告哈希、
用例状态及框架捕获的执行身份；历史 runs 与 diff/hash 保留。
