# Q07：显式原生 BW 口径与整段波形对照

默认 Butterworth 将 `cutoff_hz` 作为单次滤波的 -3 dB 频率，双向后该处为 -6 dB。
登记的原生 XYPlot BW 使用不同口径：标称频率乘 1.25，并采用短反射段初始化。
单纯换用现有 odd/constant 填充不能复现原生端点；固定混合正弦上旧默认最大差异约 0.2034。

新增显式 `convention="lsprepost"`，沿用标准二阶 Butterworth 极点/双线性变换，
使用登记的反射初始化和两遍之间的 float32 存储。实现采用 float64 系数/递推状态；
输出对照不等于证明原生内部采用相同表示。反射长度为 `max(1, floor(0.1*fs/f_nominal))`，
必须小于记录长度；端点溢出、输入下溢及 float32 时间丢序均拒绝。
兼容口径只接受 order=2、s/ms；初始化固定，不悄悄忽略矛盾的 padding。

```json
{"op":"butterworth_filter","input":"force","output":"filtered","order":2,"cutoff_hz":600,"convention":"lsprepost"}
```

输出元数据区分标称频率和实际设计频率，并登记反射长度、精度与公式。
默认 `standard` 保持原有数值；本地与 main `892aca9` 的 14 组 Butterworth/SAE 输出逐位一致。

干净代码提交 `2f3242ca488561cd780d5fc5f3282c82686630d8` 的实际运行：

| 版本 / 上下文 | BW | SAE 回归 | 失败 / 跳过 | 有效性 |
|---|---:|---:|---|---|
| [4.13 batch](bw-sae-413-batch-report.md) | 16 | 4 | 0 / 0 | 当前有效（登记范围） |
| [4.10 batch](bw-sae-410-batch-report.md) | 16 | 4 | 0 / 0 | 当前有效（登记范围） |

BW 覆盖短脉冲、混合正弦、带偏置阶跃、冲击后衰减振铃四类固定合成波形，
各取标称 60/600 Hz × s/ms。SAE 继续回归原有混合正弦的 60/600 × s/ms。
完整记录含两端逐点比较，保持 `rtol=2e-5`、`atol=1e-6*max(abs(reference))`，不裁样本、不放宽容差。
同时核对输入字节、原生导入控制曲线、点数、时间轴、有限值及 headless 执行。
33 点独立原生参考也已登记为单元测试；13 项新增回归在旧 main 上失败，修复后通过。

复跑命令（两个版本串行，各用尚不存在的输出目录）：

```shell
python -B -m pytest tests/test_butterworth_filter_native.py tests/test_curve_filter_native.py -q --run-native --native-strict --native-executable "<4.13或4.10的可执行文件>" --native-output "<仓库外全新目录>"
```

原生运行器记录实际 revision、工作树状态、固定 diff 范围及源码快照。
本次工作树干净，diff 为全部 tracked staged/unstaged 改动，未跟踪文件不进入 diff；
空补丁 SHA256 为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
仓库内 [evidence.json](evidence.json) 保留逐例误差、输入/输出哈希、程序身份、测试与产品 Git blob ID。
源码身份使用 Git 的文本规范化；Markdown 哈希以 UTF-8/LF 重算，原生配置仅登记 SHA256。
含本机路径的配置和原生日志留在本机，没有提交厂商伪代码或二进制。

Q07 保持 partial：登记波形不替代真实工程数据；SAE 尚未覆盖上述所有波形，其他版本及
更广输入范围仍待验证。CLI 尾参数 0 的语义未独立读回，不推断 GUI 选项。
将任务升级为 done 前仍需独立审阅和原生证据抽查。
