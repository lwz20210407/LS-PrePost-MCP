# Q06 NODOUT：SPCFORC 包装层变更后的来源刷新

状态 partial / L1；仅本表实际有限主机读取，不是 Native、求解器或完整 Q06 验收。

实际干净源码 `d86edd64b0b293dc8b6826a647db075d8ded95ab`，完整快照 `d54e34170abcd37b9838651aeb1715e9250c6fe77bb2568688c5c4018c0a3518`。三个产品来源为当前 reader/wrapper/scanner；capture 前后完整源码、10个输入、catalog、目录namespace与私有支持脚本均不变。

| 输入 | 帧 | 实体 | 比较值 | 当前 / 历史 |
|---|---:|---:|---:|---|
| result.ansyshelp-ansys-com__doc-assets.4_2_Post_Plot_curve | 121 | 1 | 1089 | current_for_recorded_source |
| result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit | 1001 | 2 | 18018 | current_for_recorded_source |
| result.pranavduraisamy__helmet-fit-bayes-opt.bo-runs.run0.drop | 251 | 1 | 2259 | current_for_recorded_source |
| result.pranavduraisamy__helmet-fit-bayes-opt.bo-runs.run0.pendulum | 251 | 1 | 2259 | current_for_recorded_source |
| result.zenodo__18598355.FEMU_Taylor.03_mat_CS_artificial | 669 | 21 | 126441 | current_for_recorded_source |
| result.zenodo__18598355.FEMU_Taylor.21_mat_JC_real | 429 | 21 | 81081 | current_for_recorded_source |

| 旧上下文 | 原实际源码 | 当前 / 历史 |
|---|---|---|
| docs/decisions/evidence/q06-sleout-source-refresh/nodout | 0c9d588dee1a4b0b0fe0b1b4f96c87a9ec0ed39f | historical：原字节与SHA保留，不作本次新通过 |

本次三个CLI依次为SLEOUT、NODOUT、原explicit_no_data负例；总62个不同host UUID。两份报告作用域分别为6条SLEOUT/14490值、54条NODOUT/231147值，不能据此扩大变量、物理映射或原生支持范围。
负例是两个实际failed作业：无数值payload/artifact，精确保留database/branch/component/backend四项上下文。不把限制负例算作正例通过，不采用旧失败捕获或旧posthoc作为本次成功。
有效性仍raw/unmasked、deletion validity unknown；单位由调用者声明，不推断转换。源/CSV内容与实体数组留在私有资料，公开仅计数、语义组件与身份hash。

## 可复跑有限合同

```powershell
$env:PYTHONPATH = "<worktree>/src;<worktree>"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONOPTIMIZE = "0"
$env:PYTEST_ADDOPTS = ""
$env:LSPP_CORPUS_DIR = "<existing-registered-corpus>"
$env:TEMP = "<owned-existing-private-temp>"
$env:TMP = $env:TEMP
python -B tools/verify_ascii_sleout_corpus.py --corpus "$env:LSPP_CORPUS_DIR" --output "<fresh-private-parent>/sleout"
python -B tools/verify_ascii_nodout_corpus.py --corpus "$env:LSPP_CORPUS_DIR" --output "<fresh-private-parent>/nodout"
python -B -m pytest tests/test_ascii_nodout_corpus.py -q -k explicit_no_data -p no:cacheprovider --basetemp "<fresh-private-parent>/negative-temp" --junitxml "<fresh-private-parent>/negative.xml"
```

复跑需锁定环境、既有登记来源及独立新输出；源码/输入守卫为前后采样，不宣称连续监控。
