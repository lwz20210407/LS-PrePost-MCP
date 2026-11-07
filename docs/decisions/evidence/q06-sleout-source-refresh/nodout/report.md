# Q06 NODOUT：SLEOUT 包装层变更后的真实来源刷新

状态保持 partial / L1。此次只重验原有 ASCII NODOUT 平动读取，未执行 Native、求解器或新 SLEOUT 验收。

原 R2 两个命令均 exit 0，实际产生 54 个成功曲线作业和 2 个预期拒绝作业；原私有收尾审计错误要求 data 必须是空对象，因此原 capture proof 仍为 failed。此记录采用主代理批准的同批只读后验复核，没有重跑，也没有改原 proof、作业、CSV 或日志。

原失败 proof SHA 为 `36905a700d0c5311f635cfda51af1c63d99e75533adee892ae6e61053562da73`；专用后验 receipt SHA 为 `8867026a87f9b4fde79df45e6d1e63ed36b89d48f20b09469edd0dc246ecf5dd`；后验审计 code SHA 为 `389d2a0633bbbbca06786ba23d5384c65615e455a970aa0662ad3dd5db960ec0`。

实际干净源码为 `0c9d588dee1a4b0b0fe0b1b4f96c87a9ec0ed39f`，完整来源快照为 `86b1accdd6a61d6a3501e7fb71a751bc513e2dd862225f54118db71d77a3c9f5`。三个轻量产品来源为 reader、wrapper、ascii_records；原六个公共源、54 条曲线、231,147 个数值逐值相等。完整源码与八个输入的 SHA/stat/目录清单前后保持；记录这些采样，不宣称连续监控。

| 公共输入 | 帧 | 节点 | 九列比较值 | 当前有效 / 已被取代 |
|---|---:|---:|---:|---|
| result.ansyshelp-ansys-com__doc-assets.4_2_Post_Plot_curve | 121 | 1 | 1089 | current_for_recorded_source |
| result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit | 1001 | 2 | 18018 | current_for_recorded_source |
| result.pranavduraisamy__helmet-fit-bayes-opt.bo-runs.run0.drop | 251 | 1 | 2259 | current_for_recorded_source |
| result.pranavduraisamy__helmet-fit-bayes-opt.bo-runs.run0.pendulum | 251 | 1 | 2259 | current_for_recorded_source |
| result.zenodo__18598355.FEMU_Taylor.03_mat_CS_artificial | 669 | 21 | 126441 | current_for_recorded_source |
| result.zenodo__18598355.FEMU_Taylor.21_mat_JC_real | 429 | 21 | 81081 | current_for_recorded_source |

另外两份输入是真实拒绝负例：无数据与 float64 下溢。两个测试通过，对应两个作业实际 failed，数值 payload 与 artifact 均为空；data 精确保留 database/branch/component/backend 四项失败上下文，不允许额外 curve/time/values 键。不能合并成公共 8/8 功能通过。

单位和时间单位只保留调用者声明，不换算、不做坐标相减或导数。输出是 raw/unmasked，alive mask 不可用，deletion validity 仍为 unknown。

复用原 verifier CLI 和原 explicit_no_data 两例，没有复制语料。子进程仅阻止 Service._native 入口，实际计数为零；这不是全系统进程隔离证明。旧 q06-ascii-nodout JSON/报告保留原 revision 与字节，新记录单独归档。

R1 曾在私有路径准入守卫阶段失败，真实失败 receipt SHA 为 `87734402a78880e86ad51c5af944b1a240cd22116a21a94ab8fe3dc23d915a94`。当时 plain drive 路径与项目 io_root 的扩展 drive 路径被错误地作字面比较；verifier 和负例测试均未启动，0 个 host job，输入守卫没有完成。这是保留的私有 harness 准入失败，不计为 NODOUT 功能失败，也不被当前成功捕获覆盖。

## 可复跑的有限合同

在项目锁定环境和工作树目录下执行；下例为 PowerShell，所有路径均为占位，语料必须已经登记并存在，输出与临时目录须为调用者自有的新目录。PYTHONPATH 必须同时指向本工作树 src 与根目录；LSPP_CORPUS_DIR 只指定既有来源。

```powershell
$env:PYTHONPATH = "<worktree>/src;<worktree>"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTEST_ADDOPTS = ""
$env:TEMP = "<existing-owned-private-temp>"
$env:TMP = $env:TEMP
$env:LSPP_CORPUS_DIR = "<existing-registered-corpus>"
python -B tools/verify_ascii_nodout_corpus.py --corpus "$env:LSPP_CORPUS_DIR" --output "<fresh-outside-checkout-output>"
python -B -m pytest tests/test_ascii_nodout_corpus.py -q -k explicit_no_data -p no:cacheprovider --basetemp "<fresh-outside-checkout-negative-temp>" --junitxml "<outside-checkout>/negative.xml"
```

以上命令重验相同数据合同；此记录额外的完整源码、SHA/stat/namespace 和私有支持脚本守卫见绑定的 capture receipt。

此记录不提升 Q06 完成状态，不替代独立外部审核、Native/物理/全库覆盖或 SLEOUT 自身验证。
