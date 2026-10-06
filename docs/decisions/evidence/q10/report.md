# Q10 截面剖切云图与 SECFORC 验证记录

Q10 配方 `section_cut_fringe` 基于 LS-PrePost 原生 `splane` 命令集（`splane create px py pz nx ny nz`、`splane drawcut on`）在批处理下生成截面云图 PNG。

| 版本 | 模式 | 状态 | 范围 |
|---|---|---:|---|
| 4.13.4 | c_nographics | verified | 剖切面基准点与法向向量可设，支持状态选择与物理量编号 |
| 4.13.4 | runc | failed | runc 批处理通道不支持图形窗口抓图（与 snapshot 表现一致） |
| 4.10.1 | c_nographics | verified | 剖切面基准点与法向向量可设，与 4.13.4 行为一致 |
| 4.10.1 | runc | failed | runc 批处理通道不支持图形窗口抓图 |

SECFORC 截面合力与时间历史提取通过 `ls_prepost_mcp.section` 模块验证：
- 支持 `binout` 及 ASCII `secforc` 双格式读取；
- 逐时刻校验合力 $F_{\text{total}}$ 与 $\sqrt{F_x^2 + F_y^2 + F_z^2}$ 物理一致性；
- 独立截面力计算与求解器 `SECFORC` 历史曲线对比误差控制在容差以内。
