# Q10 截面剖切云图与 SECFORC 验证记录

Q10 配方 `section_cut_fringe` 基于 LS-PrePost 原生 `splane` 命令集（`splane create px py pz nx ny nz`、`splane drawcut on`）在批处理下生成截面云图 PNG。

| 版本 | 模式 | 状态 | 范围 |
|---|---|---:|---|
| 4.13.4 | c_nographics | unverified | 剖切面基准点与法向向量可设，配方模板与参数校验已就绪，原生批处理执行待单一定案窗口统一认证 |
| 4.13.4 | runc | unverified | runc 批处理通道尚未通过原生认证 |
| 4.10.1 | c_nographics | unverified | 行为与 4.13.4 一致，待单一定案窗口统一认证 |
| 4.10.1 | runc | unverified | runc 批处理通道尚未通过原生认证 |

SECFORC 截面合力与时间历史提取通过 `ls_prepost_mcp.domain.results.section` 模块验证：
- 支持 `binout` 及 3-line ASCII `secforc` 双格式严格解析；
- 截面号严格从数据行或 metadata / ids 提取，规避表头包含 "Section" 关键字引起的串号错误；
- 逐时刻校验合力 $F_{\text{total}}$ 与 $\sqrt{F_x^2 + F_y^2 + F_z^2}$ 物理一致性（在 pranavduraisamy pendulum 真实语料上通过）；
- `compare_section_forces` 严格要求时间序列单调递增并有重叠有效区间，分量逐一插值对比，无外推；
- 原生 LS-PrePost GUI/批处理生成截面云图待统一窗口运行原生认证。
