# Q01 result_info：公开语料与 LS-PrePost 4.13 对照（2026-10-07，Cursor）

- 代码：基于 main `e41cf65`，本 PR 的 `result_info`（`src/ls_prepost_mcp/result_overview.py`）。逐例数据见 [evidence.json](evidence.json)。
- 后端：LASSO 用 lasso-python 2.0.4（共享实现 `domain/results/lasso_backend.overview` 与 `mpp_shards.catalog`）；LSPP 用 LS-PrePost 4.13.0.1（2026R1），headless 批处理，内嵌 Python `inspect_model`。没有启动可见 GUI。
- 语料：本机公开语料（`LSPP_CORPUS_DIR`），只登记相对路径和 d3plot 的 SHA256，文件本身不提交。
- 时间一致的判据：每个状态的时间差都不超过 1e-6 × 最大状态时间。

## 证据身份（2026-10-22 审阅更正）

本记录不能作为验收第 3 条的通过证据，Q01 在 tasks.yaml 中保持 `partial`：

- 只记了基线 `e41cf65`，没有产生结果的实际提交、工作树是否干净、`result_overview.py` / `lasso_backend.py` 的 SHA256；
- 没有 LS-PrePost 可执行文件的 SHA256，也没有每例的 LSPP job_id、result_info job_id 和运行时间；
- 记录之后 d3plot 头字段改由共享的 `lasso_backend.header` 读取（PR #84 审阅 P1-84a），代码已不是产生这些数字的代码。

LSPP 对照需按身份规范（revision、可执行文件哈希、job id）重跑后再判定。下表的 LASSO 一侧已在审阅中用公开语料直读复算一致（taylor_jc、bolt_b_mpp）；LSPP 一侧的数字照原样保留，仅供参考，未经复核。

## 结果

| 算例 | 状态数 LASSO / LSPP | 最大时间差 | 单元族（删除数） | binout | ASCII | backends_agree |
|---|---|---|---|---|---|---|
| plade_bb | 2 / 2 | 5.96e-9（容差 1e-7） | solid 15390（0） | `binout`：glstat、matsum、rcforc、spcforc、tprint | 10 个 | passed |
| bolt_b_mpp | 102 / 102 | 0 | solid 784、shell 648、beam 70（均为 0） | 4 个 MPP 分片，共 10 个库，没有跨分片拆开的条目 | glstat | passed |
| taylor_jc | 102 / 102 | 0 | solid 540（66）、shell 1（0） | `binout`：nodout | nodout | passed |

三条验收的对应关系：

1. 状态数、每个状态时间、变量（LASSO 数组名）、部件、单元族、HSV 数量和最后状态的删除单元数都在 `data` 中。HSV 给两个数：LASSO 可读的历史变量个数，以及 d3plot 头声明的每积分点附加值个数（NEIPH/NEIPS/NEIPB）。plade_bb 和 taylor_jc 的头声明 NEIPH=6，同时标明存了应变张量，LASSO 把这 6 个值归入 `element_solid_strain`，所以可读的历史变量为 0；这两个数并列给出，不替用户换算。
2. 同目录的 binout 分片及每个分片所含的库（`data.binout`），以及 ASCII 文件（`data.ascii_files`）。
3. `native_check=true` 时，状态数和时间数组与 LSPP 一致：当时记录三例都通过，但缺少上文的身份信息，无法复核，待重跑。

## 失败与限制（如实保留）

- 第一次运行时，bolt_b_mpp 的 LSPP 进程以 0xC0000005（返回码 3221225477）崩溃，结果为 `partial`，`backends_agree=missing`，错误原样返回。立即单独重跑 `inspect_model` 成功，SCL 清点（`inspect_d3plot_scl`）也给出 102 个状态；第二次完整运行三例都通过。崩溃没能复现，原因未查明。
- 只验证了 4.13，本次没有跑 4.10 对照。
- 共享 overview 在状态数超过 2000 时不返回逐状态时间，这时 `result_info` 返回 `partial` 并给出警告，不能做时间对照。
- 删除数只统计最后一个状态；d3plot 没有删除数据时为 null，不写成 0。
