# Q06 ASCII SLEOUT：三列原始接口能量

当前有效证据是干净 `0c9d588dee1a4b0b0fe0b1b4f96c87a9ec0ed39f` 的 **L1 / partial**
读取：两份已有公共文件、6 条分量/文件曲线、14,490 个原始能量值与独立扫描器精确一致，
其中 6,757 个非零。没有启动 LS-PrePost、GUI 或求解器。

| 记录 | 实际产品头 / 状态 | 结果 | 当前有效 / 已取代 |
|---|---|---|---|
| 公共逐值读取 | `0c9d588` / clean | 2 源、6 曲线、14,490 值 exact | 当前有效 L1 |
| parser / Service 合同 | `0c9d588` / clean | 99 passed，0 skipped | 当前有效，窄范围 |
| 同 SHA 外置回归合同 | `0c9d588` / clean | 11 passed，0 skipped，12 deselected | 当前有效，与上项重叠 |
| 缺 SDK 策略 | `0c9d588` / clean | 99 passed，0 skipped | 当前有效，同窄范围重叠 |
| 首轮公共读取 | `6edca5d` / clean | 14,490 值 exact | 已取代：在前导孤行修复之前 |
| 新功能旧产品负控 | `5ec22b6` / clean | 6 个真实 Service 失败 | 历史预期 red；新头同 SHA green |
| 缺列/多列/单 ID 孤行负控 | `6edca5d` / clean | 3 个未拒绝失败 | 历史预期 red；新头同 SHA green |
| 小数起始孤行负控 | `bac131b` / clean | 2 个未拒绝失败 | 历史预期 red；新头同 SHA green |

上述测试范围互相重叠，不相加。缺 SDK 检查用独立共享解释器进程阻断 `lasso` / `ansys`
导入，不能称为实际最小依赖环境。较早的 549/56 skipped 与 98/3 skipped 发生于
`6edca5d` 的 dirty 开发树，仅保留私有开发日志，不作为当前 clean 证据。

## 来源与身份

仅登记来源 ID、SHA256 和数量。两源未声明许可证，原文、逐行 CSV、完整原始日志和目录清单
留在外部已有 corpus / 任务 scratch，未复制入 Git。

| 来源 ID / member | 字节 | 帧 × 原始接口数 | 三列值数 | SHA256 | 当前有效/已被取代 |
|---|---:|---:|---:|---|---|
| `result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit` / `sleout` | 544995 | 1001 × 3 | 9009 | `ae1aaeab68ce48f7a4da4d10ebeb49bb99556fcc7444c99f4f5a856754ee56eb` | current_for_recorded_source |
| `result.praveenvenky110395__LS-DYNA-Crimping-Simulation.results` / `sleout` | 224203 | 261 × 7 | 5481 | `21fb2eda6bdeb55ea43aec6947115a2e2233873b1154803b138850c8e43e3fc9` | current_for_recorded_source |

公共 capture 的完整 689 个源码文件前后相同，snapshot 为
`86b1accdd6a61d6a3501e7fb71a751bc513e2dd862225f54118db71d77a3c9f5`；tracked diff 为空。
输入 full SHA、稳定 stat 字段、完整目录 namespace 和 catalog SHA 前后相同。
公共报告 SHA 为 `8c4c2beaa609a8fd6105a976ddce92d68593384f7729dbca916cdd36842ccba8`。
`evidence.json` 保存 reader、wrapper、bounded reader 和测试/扫描器的 Git blob、LF SHA 与
实际捕获字节 SHA。测试命令均在冻结 actual HEAD 运行；parser / Service 与外置合同前后 clean Git 状态已记录，
窄缺 SDK 与该区间并行。没有为每条测试命令独立捕获完整源码字节 before/after，
后续公共 capture 提供同头完整源码一致性旁证。

## 读取合同

`side_a_energy`、`side_b_energy`、`frictional_energy` 只映射写出列位置，保留
`slave/master/frictional` 或 `surfa/surfb/frictional` 原标签。允许负值。
按首个完整帧的 printed raw interface ID 顺序输出，后续乱序按同一 ID 集合对齐；
不认证 keyword CID / UI 用户号，不关联 legend 或邻居模型文件，不合并两侧。
单位仅调用者声明；曲线 raw/unmasked，alive/deletion validity unknown。

重复 ID、成员变化、重复/下降时间、缺列/多列、截断列头、缺失或错误 summary、非 finite、
非零 float64 下溢、输入变化和资源预算超限均拒绝。仅支持非行状文字及可选 legend 前导；
数字标题与孤行有歧义时报告 unsupported，不静默忽略，也不宣称数字标题属于 LS-DYNA 非法格式。
完整四行 summary 只做语法/数值表示检查，不输出、不算守恒或总能量物理。
`native_check=True` 在创建 job / 启动原生程序之前明确拒绝。

## 可重复命令与边界

以下是实际命令的可移植等价写法。`LSPP_REPO` 指冻结 checkout，`LSPP_PYTHON` 指已有共享
解释器，`LSPP_CORPUS_DIR` 指已有只读语料，`LSPP_EVIDENCE_DIR` 必须是外部全新目录，
`LSPP_TEST_TEMP`、`LSPP_CONTRACT_DIR` 指各自任务 scratch。命令均未含 native opt-in。

```powershell
$env:PYTHONPATH="$env:LSPP_REPO/src;$env:LSPP_REPO"
$env:PYTHONDONTWRITEBYTECODE="1"
$env:TEMP=$env:LSPP_TEST_TEMP
$env:TMP=$env:LSPP_TEST_TEMP
Set-Location $env:LSPP_REPO
& $env:LSPP_PYTHON -B tools/verify_ascii_sleout_corpus.py --corpus $env:LSPP_CORPUS_DIR --output $env:LSPP_EVIDENCE_DIR
& $env:LSPP_PYTHON -B -m pytest tests/test_ascii_sleout_parser.py tests/test_ascii_sleout_database.py -q --tb=short -p no:cacheprovider --basetemp "$env:LSPP_TEST_TEMP/sleout-unit"
Set-Location $env:LSPP_CONTRACT_DIR
& $env:LSPP_PYTHON -B -m pytest contract_test.py orphan_contract_test.py decimal_orphan_contract_test.py -k "test_named_sleout_components_preserve_ids_values_and_source_labels or test_incomplete_or_extra_orphan_numeric_records_are_not_titles or test_decimal_orphan_numeric_records_are_not_titles" -q --tb=short -p no:cacheprovider --basetemp "$env:LSPP_TEST_TEMP/sleout-contract"
```

`LSPP_TEST_TEMP` 使用本次新测试父目录；三个 basetemp 均指其下不同的新子目录，
不能直接指向保留审计资料的 scratch 根。缺 SDK 命令如下。

```powershell
Set-Location $env:LSPP_REPO
@'
import importlib.abc, os, sys
class NoOptionalSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('lasso', 'ansys'):
            raise ModuleNotFoundError('Optional result/native SDK deliberately unavailable', name=fullname)
sys.meta_path.insert(0, NoOptionalSDK())
import pytest
raise SystemExit(pytest.main(['tests/test_ascii_sleout_parser.py', 'tests/test_ascii_sleout_database.py',
                             '-q', '--tb=short', '-p', 'no:cacheprovider', '--basetemp',
                             os.path.join(os.environ['LSPP_TEST_TEMP'], 'sleout-no-sdk')]))
'@ | & $env:LSPP_PYTHON -B -
```
外置三合同 SHA 与各 red/green 日志 hash 见 `evidence.json`；旧产品负控使用对应独立干净
checkout 作为 `PYTHONPATH`，没有 mock missing feature。

内部 Codex peer / Root 复核已修复所报告 P1/P2，未冒充外部独立评审。
当前证据不覆盖其他 SLEOUT 格式、具名原生比较、MPP/SMP 等价或完整 Q06 验收，任务仍 partial。
