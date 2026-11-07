# Q06 ASCII SPCFORC：原始局部节点力与力矩

当前证据是实际干净 `d86edd64b0b293dc8b6826a647db075d8ded95ab` 的 **L1 / partial** Service 读取：两份已登记文件，
9 个已存分量导出、270,192 个已写值与独立 Decimal/token 参考逐 CSV 时间/ID/值相等；
其中 130,506 个非零、139,686 个真实零。另 3 个缺失力矩请求实际失败且没有产物或数值 payload。
没有启动 LS-PrePost、GUI 或求解器，不构成具名原生比较或 Q06 完整验收。

| 记录 | actual HEAD / 状态 | 结果 | 当前 / 历史与范围 |
|---|---|---|---|
| 实际 Service 公共读取 | `d86edd6` / clean | 9 成功导出、270,192 值 exact；另 3 预期失败 | 当前 Service L1 |
| 相关 ASCII、源守卫、模拟原生输出、同 SHA 外置合同 | `d86edd6` / clean | 774 passed、3 skipped | 当前有界测试；不是 full suite |
| SPC parser / Service / corpus 与外置合同窄运行 | `d86edd6` / clean | 229 passed、2 skipped | 与 774 范围重叠 |
| 同 SHA 私有合同 | `d86edd6` / clean | 13 passed，包含旧版的 6 个正例 | 包含于上述两个运行，不相加 |
| 旧 SLEOUT/NODOUT current 来源门禁 | `d86edd6` / clean | 2 个 expected-stale failure | wrapper 字节变化的历史记录；不改门禁、不计产品通过 |
| stage1 parser-only 原文件核对 | `95a5474` / clean | 9 个可用分量、270,192 值 exact；3 个缺失力矩拒绝 | 历史 parser L1；从未冒领 Service，不与当前轮相加 |
| stage1 parser / bounded lexer | `95a5474` / clean | 188 passed（170 + 18） | 历史测试，不与当前轮相加 |
| 新功能旧版 Service 负控 | `5fb08eb` / clean | 6 个正例均因文件名白名单拒绝而 red；7 deselected | 实际旧产品，不 mock missing feature |

当前 774 范围中，21 项原生比较回归使用模拟输出，没有运行原生程序；两个 SPC 公共
pytest 用例未启用而跳过，真实公共读取由单独释放的 Service CLI 完成。另一个跳过来自既有力库测试。
`lasso` 不可导入的专属测试是进程内阻断，不是一次实际完整最小依赖环境运行；不作 full-min 声称。
当前 Ruff、任务/生成文档/链接检查通过。测试范围重叠，表中数字不可相加。

## 两份输入与数量

| 已登记 ID / member | 字节 | 帧 × 节点 | 已存分量导出 | 比较值 | 非零 / 真实零 | SHA256 | 当前 / 历史 |
|---|---:|---:|---:|---:|---:|---|---|
| `result.jascott4427__PILLARS-LSDyna.Bolt_B_Explicit` / `spcforc` | 8568179 | 1000 × 45 | 6 | 270000 | 130410 / 139590 | `614a8fbc6f4b650e7c6dc68dd5567a92389f1e79b9ef7119323523317e2ef82d` | current_for_recorded_source |
| `result.node997__dyna_pladebuk.Plade_300_150_4.BB` / `spcforc` | 6283 | 2 × 32 | 3 | 192 | 96 / 96 | `c6cb30a74e4b40b9bc98cfdc1b4b1082817766782e463f06cf67ad7301c87808` | current_for_recorded_source |

大源每个 force 分量为 43,470 非零、1,530 零；每个 moment 分量的 45,000 值全部是源中
明确写出的真实零，三个 moment 共 135,000 零。真实非零力矩正确性目前只由自有正负合成
oracle 支持。小源每个 force 为 32 非零、32 零，三个 moment 均未存储，不能填成零或算作正例。
每帧 force resultants 只校验完整语法与数值表示，不输出、不计入这 270,192 值、不计算守恒。

大源未声明许可证；小源也只登记 ID、hash 与数量。原始文本、逐行 CSV、绝对路径、
完整日志和目录 listing 均不入 Git。12 个 job 的角色/UUID、成功 CSV hash、失败上下文及
输入 SHA 在 [evidence.json](evidence.json) 分列，失败不混入 positive 列表。

## 捕获身份与源守卫

Service lease 是 `root-q06-spcforc-d86-two-public-service-r1`，首次执行 exit 0，无自动重试。
实际捕获前后 HEAD 均为 `d86edd64b0b293dc8b6826a647db075d8ded95ab`，tracked diff 为空且工作树 clean；
完整 **695** 个源码文件映射相同，snapshot 均为
`d54e34170abcd37b9838651aeb1715e9250c6fe77bb2568688c5c4018c0a3518`。
两输入 full SHA、稳定 stat、完整父目录 namespace 以及登记 manifest 的 full SHA/stat 前后相同。
manifest SHA 是 `ce3e64e2810604e44dab8149816d4540e38495e8878f87a092cc8be8c032131f`。
实际 Service raw 报告 SHA 是 `7d2dd617ed8d11c0cafc11e460a87ceecab707f011bc521c220cda74c9a218b5`。
JSON 将本文的 LF SHA 与实际捕获 raw 报告 SHA 分开记录，并列运行时 reader/wrapper/bounded scanner、
四个测试文件及独立 verifier/身份工具的 Git blob、LF SHA 和 captured-raw SHA。
774 测试有独立 clean Git before/after 记录；没有为每一条测试命令另捕获完整 695 文件映射，
不可把公共 capture 的完整源码旁证改写成每项测试独立测量。

## 读取与实体选择合同

只支持六个别名 `x_force/y_force/z_force/x_moment/y_moment/z_moment`，读取原文
`local x,y,z` 位置和 forces/moments 记录 kind。原始局部基底未知，不认证为 global，
不将 setid 当 CSID，也不进行坐标或单位转换。节点只按打印 raw ID 对齐，不认证 keyword/UI 映射。
首个 force 表的原始节点顺序作为 source 列顺序；后帧可乱序但集合必须一致。允许负值并保留真实零。
全文件 force-only 合法；一旦出现 moment，每帧每节点必须有成对完整记录，模式与 setid 必须稳定。

**选择顺序与元数据数组采用既有 wrapper 约定**：`data.ids` 和 CSV 按 `entity_ids` 请求顺序
输出；`entity_metadata.setid`、`raw_node_id_tokens`、`raw_setid_tokens` 等数组始终保留完整
source 列顺序，`column_order = first force table`。应以 `data.stored_columns` 索引这些数组，
不能直接把已选择的 `data.ids` 与完整 metadata 数组 zip。此说明不改变 parser、数学或捕获代码。

曲线为 raw/unmasked，alive/deletion validity unknown。重复节点/kind、多 setid、成员变化、
重复/下降时间、缺配对、缺/重复 summary、summary 后节点、孤立或歧义数字前导、畸形数值、
非 finite、非零 float64 下溢、源变化或预算超限明确拒绝，不排序去重、不插值、不补零。
这是一套受支持布局与 float64 表示边界，不把未知布局或有歧义标题宣称为非法 LS-DYNA。
`native_check=True` 沿既有 RCFORC/SECFORC 白名单在创建 job 前拒绝，数字 native code 不证明具名映射。

## 可移植复现命令

以下是实际命令的可移植等价写法，原始 argv、controller、JUnit、raw 报告保留在外部 scratch。
配置 `LSPP_REPO` 为冻结 d86 checkout，`LSPP_STAGE1_REPO` 为冻结 95a checkout，
`LSPP_BASELINE_REPO` 为冻结 5fb checkout；`LSPP_PYTHON` 指已有共享 Python 3.11，
`LSPP_CORPUS_DIR` 指已有只读 corpus，`LSPP_CONTRACT_DIR` 指保留同 SHA 合同的外部目录，
`LSPP_RUN_ROOT` 与 `LSPP_TEST_TEMP` 是本次全新外部父目录。所有输出子目录与 basetemp 均须新建且互异，
不得把保存历史证据的 scratch 根本身交给 `--basetemp`。无需下载、环境安装或 native opt-in。

```powershell
$env:PYTHONDONTWRITEBYTECODE="1"
Set-Location $env:LSPP_REPO
$env:PYTHONPATH="$env:LSPP_REPO/src;$env:LSPP_REPO"
& $env:LSPP_PYTHON -B tools/verify_ascii_spcforc_corpus.py --corpus $env:LSPP_CORPUS_DIR --output "$env:LSPP_RUN_ROOT/service-two-public-r1" --reader service --expect-head d86edd64b0b293dc8b6826a647db075d8ded95ab --lease root-q06-spcforc-d86-two-public-service-r1
Remove-Item Env:LSPP_CORPUS_DIR -ErrorAction SilentlyContinue
& $env:LSPP_PYTHON -B -m pytest tests/test_ascii_record_lexer.py tests/test_ascii_force_database.py tests/test_ascii_metadata_review02.py tests/test_ascii_glstat_database.py tests/test_ascii_matsum_database.py tests/test_ascii_nodout_database.py tests/test_ascii_nodout_parser.py tests/test_ascii_sleout_database.py tests/test_ascii_sleout_parser.py tests/test_ascii_spcforc_database.py tests/test_ascii_spcforc_parser.py tests/test_ascii_spcforc_corpus.py tests/test_database_native_check.py "$env:LSPP_CONTRACT_DIR/service_contract_draft.py" -m "not native" -q -p no:cacheprovider --basetemp "$env:LSPP_TEST_TEMP/stage2-clean-related" --junitxml "$env:LSPP_RUN_ROOT/stage2-clean-related.xml"
& $env:LSPP_PYTHON -B -m pytest tests/test_ascii_spcforc_database.py tests/test_ascii_spcforc_parser.py tests/test_ascii_spcforc_corpus.py "$env:LSPP_CONTRACT_DIR/service_contract_draft.py" -q -p no:cacheprovider --basetemp "$env:LSPP_TEST_TEMP/stage2-clean-narrow"
& $env:LSPP_PYTHON -B -m pytest tests/test_ascii_sleout_evidence.py::test_sleout_capture_matches_current_product_and_verifier_lf_sources tests/test_ascii_nodout_evidence.py::test_nodout_public_evidence_binds_the_reader_wrapper_and_scanner -q -p no:cacheprovider --basetemp "$env:LSPP_TEST_TEMP/stage2-stale-gates"
```

最后一条只复现 d86 的两项旧来源门禁过期，不是目标通过命令。完整源码 before/after 由
`tools.native_regression.execution_identity(Path(LSPP_REPO))` 在一次 Service CLI 前后测量；
私有 one-shot controller 的 SHA 和两份原始身份 JSON SHA 在 evidence 中保留。可移植等价包装如下。

```powershell
@'
import json, os, subprocess, sys
from pathlib import Path
from tools.native_regression import execution_identity
root = Path(os.environ["LSPP_REPO"])
run = Path(os.environ["LSPP_RUN_ROOT"])
before = execution_identity(root)
assert before["actual_git_head"] == "d86edd64b0b293dc8b6826a647db075d8ded95ab" and not before["working_tree_dirty"]
assert len(before["source_files"]) == 695
(run / "source-before.json").write_text(json.dumps(before, indent=2), encoding="utf8")
code = subprocess.call([sys.executable, "-B", "tools/verify_ascii_spcforc_corpus.py", "--corpus",
    os.environ["LSPP_CORPUS_DIR"], "--output", str(run / "service-with-source-guards"), "--reader", "service",
    "--expect-head", "d86edd64b0b293dc8b6826a647db075d8ded95ab", "--lease", "root-q06-spcforc-d86-two-public-service-r1"], cwd=root)
after = execution_identity(root)
(run / "source-after.json").write_text(json.dumps(after, indent=2), encoding="utf8")
assert before == after
raise SystemExit(code)
'@ | & $env:LSPP_PYTHON -B -
```

上面 CLI 与包装是两种可选复现入口，本次实际只通过私有 controller 运行一次。
包装前须重新设置只读 `LSPP_CORPUS_DIR`，不能在移除该变量后的测试环境直接执行。
历史入口如下，不改绑到 d86。

```powershell
Set-Location $env:LSPP_STAGE1_REPO
$env:PYTHONPATH="$env:LSPP_STAGE1_REPO/src;$env:LSPP_STAGE1_REPO"
& $env:LSPP_PYTHON -B tools/verify_ascii_spcforc_corpus.py --corpus $env:LSPP_CORPUS_DIR --output "$env:LSPP_RUN_ROOT/stage1-parser-only" --reader parser --expect-head 95a5474d675d84bfe9dbc0c64b66361b090b5191 --lease root-q06-spcforc-stage1-parser-two-public-r1
& $env:LSPP_PYTHON -B -m pytest tests/test_ascii_spcforc_parser.py tests/test_ascii_record_lexer.py -q -p no:cacheprovider --basetemp "$env:LSPP_TEST_TEMP/stage1-clean"
Set-Location $env:LSPP_BASELINE_REPO
$env:PYTHONPATH="$env:LSPP_BASELINE_REPO/src;$env:LSPP_BASELINE_REPO"
& $env:LSPP_PYTHON -B -m pytest "$env:LSPP_CONTRACT_DIR/service_contract_draft.py" -k named_components -q -p no:cacheprovider --basetemp "$env:LSPP_TEST_TEMP/old-service-red"
```

私有合同 SHA 是 `09b64086159cd1ecd13dd918ec90875046d726c516cc269cd360430229dfbfb8`；
旧 red 与新 green 使用相同字节。内部 Codex peer / Root 复核不冒充外部独立评审。
更多 SPCFORC 布局、真实非零 moment、原生具名比较、MPP/SMP 成对一致性及完整 Q06 验收仍缺，任务保持 partial/L1。
