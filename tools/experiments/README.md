# I10：M0 执行通道实验

本目录只提供实验脚本，不修改 src，不注册工具。尚未运行的格子保持 not_run；不把源码生成或已有历史验收当成本次原生证据。

## 离线准备

先用 tools/fetch_corpus.py 获得 shell_d3plot。然后：

```shell
uv run --extra results python tools/experiments/prepare.py --output <新实验目录> --synthetic-d3plot <语料缓存>/shell_d3plot/d3plot
```

生成 E1–E4 启动脚本和 75 格矩阵：4.13 五通道×三模式×三桌面状态；4.10 五通道×两种批处理×三状态。执行、PNG、MP4 各用独立进程/证据，避免渲染失败污染执行结果。每次重跑必须准备新目录。

## 单次 GUI 时间窗

建议预留 45–60 分钟；单个技术分歧实验不超过一小时。先完成并离线检查脚本，再请求用户开始。操作次序：

1. 未锁桌面：核对安装构建与 4.13 菜单截图，审计 tasks.yaml 的 ui_entry。
2. E1：应用内后台线程连续 1000 条命令，逐条读回选择 ID；核对无崩溃/死锁。
3. E2：导出 LsPrePost/DataCenter 的 dir() 与回调候选；查文档签名后才尝试注册。没有实际回调注册回执时不判通过。
4. E3：主线程轮询请求文件，执行并回执；用户观察窗口重绘与响应。仅文件生成不能证明 GUI 不冻结。
5. E4：后台线程仅处理 loopback socket；主线程消费队列并执行 1000 条命令。复核 E1 数值标准及 GUI 响应。若 E2 有已验证回调，再以该回调替换实验轮询方式并保留两份证据。
6. E5：先启动已准备队列，用户手动锁屏一次，解锁后检查产物；在实际 RDP 会话中手动断开一次，重新连接后检查。脚本不锁屏、不注销、不修改远程桌面配置。

E1–E4 的宿主入口：

```shell
uv run python tools/experiments/run_probe.py --directory <实验目录>/E1 --executable <LSPP路径>
```

脚本只结束自身创建的独立实验进程；用户其他会话保留。GUI 响应观察必须单独记录时间和结果。

## 通道矩阵的判定

- `runc=<execution.cfile>` 与 `c=<execution.cfile> -nographics` 是两个独立列；session 使用已有测试进程加载准备的 command 文件。
- command/cfile/Python 保存模型并通过独立节点计数核对；SCL 返回带随机请求 ID 的节点计数。不能仅以退出码或文件存在判成功。
- PNG 必须解码且非空白；MP4 必须经 ffprobe/ffmpeg 完整解码，核对 3 帧、640×480、5 fps。保存原生输出而非转码替代。
- `.mac` 保留完整原生块。macro_probe.py 使用手册记载的 m= 加载；session 候选通过既有 4.13.4 截图记录的 Macro 列表及 Exec 控件执行，并核对进程、标题和宏名。m= 本身只证明加载；批处理没有实际执行产物时记录失败，不据此断言所有原生宏路线均不可用。
- 锁屏和 RDP 是两种不同条件；宿主必须记录实际桌面状态和运行时间。没有实际 RDP 会话时记录未测并请用户选择验收处理方式。

## 队列入口与运行时决策

```shell
uv run python tools/experiments/run_matrix.py --directory <实验目录> --executable <安装路径> --version 4.13 --desktop unlocked
uv run python tools/experiments/run_matrix.py --directory <实验目录> --executable <安装路径> --version 4.13 --desktop locked
```

4.10 替换版本与安装路径；RDP 条件用 rdp_disconnected。每个队列先准备需要的会话，再等待 Windows 实际状态（最多五分钟），逐格记录前后状态，桌面中途变化使该格失败。未测旧版本控件或回调不得猜测：E2 在没有已记录的可调用签名时保持未验证；是否补最小回调适配由实验发现决定。

离线语法、入口、旧产物拒绝和请求关联检查已备齐；原生通过与 GUI 响应仍需该次窗口实测。ADR 保持待实验。脚本默认超时每 lane 60 秒；失败较多时 45–60 分钟窗口可能不够，应记录剩余格子并由用户决定时间安排，不缩减退出标准。
