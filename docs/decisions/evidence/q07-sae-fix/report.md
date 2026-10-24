# Q07 SAE 数值口径修复

根因：此前把不同滤波设计当作同一算法比较。Python 默认是 SAE J211 Butterworth
`2.0775*CFC`、双精度状态、odd扩展；已安装 LS-PrePost 的 legacy SAE 入口是
归一化二阶 Chebyshev-I（0.25dB、1.3*CFC）、双向恒值初始化，并逐点保存float32反馈。
独立脉冲辨识和已安装4.10程序的只读入口核对一致；不是仅靠输出拟合系数。
不发布程序、反汇编、厂商实现源码；只记录数学合同与程序身份。

新增显式 `convention="lsprepost"`，默认 `j211` 保持历史数值。
curve_ops 的 SAE operation 可选同名参数，所有步骤保留实际公式、系数、频率、精度及初始化。
兼容口径目前只接受s/ms和恒值初始化；矛盾padding、浮点溢出或时间丢序拒绝。
这不把两种算法混称为同一标准，不改变 Butterworth 操作。

```json
{"op":"sae_filter","input":"signal","output":"filtered","cfc":600,"convention":"lsprepost"}
```

回归4项在原始0563045失败：domain不接受convention、curve_ops拒绝该参数。
修复前8项差异记录保留在 [历史报告](../q07-native-filter-review02/report.md)。
新运行继续记录旧j211 odd/constant差异，以兼容profile逐点核对同一完整输出，
仍用原定rtol=2e-5、atol=1e-6*max|reference|，不裁掉端点或放宽容差。
程序参数末尾0的语义仍不外推；只对登记的完整命令负责。

干净提交、每项误差、测试和产品blob见 [evidence.json](evidence.json)。
本次不把Q07改为done：Butterworth原生对照、更广波形/版本及独立审阅仍待补。
