# Review02 P0-1: Part title identity

The previous title-ID join silently mislabeled real Parts. The fix first distinguishes complete user-ID tables from 1..n internal ordinals; a nonidentity permutation of 1..n Part IDs uses the ordinal rule. Other/malformed associations yield null titles and warnings rather than a false label or a fatal inventory failure. Mapping source and user-ID scope are returned explicitly.

Without part_ids, title IDs are display-only and unconfirmed. They cannot silently drive Part filters or Part histories. Public result_info reports partial with a missing identity check. Positive synthetic fixtures now write real Part-ID tables; a separate title-only refusal regression retains that previously unsafe case.

The same-algorithm zip oracle was removed. Three external d3plot headers are compared with paired keyword definitions using KeywordDeck.get(PART.heading / PART_CONTACT.title). No result-title-array zip produces the expected values. All keyword-tree and result-family bytes remained unchanged.

| Independent case | Parts checked | Mapping | 当前有效 / 已被取代 |
|---|---:|---|---|
| result.jascott4427__PILLARS-LSDyna.pillars_v2_airbag_open.keyfiles.100.30 | 7 | internal_ordinal | 对登记产品 blob 当前有效 |
| result.saudbinayed__binout.LS-DYNA-sample | 2 | internal_ordinal | 对登记产品 blob 当前有效 |
| result.hu-shuhan__editOpeniGame.test.Format_Validation_Test.lsdyna.Bolt_B_Explicit | 7 | internal_ordinal | 对登记产品 blob 当前有效 |

Initial clean execution revision: `7c5d8018a136ed4815fa4a91fd2f14bc97fc0063`. [evidence.json](evidence.json) binds key product-module blobs as well as the test blob. This evidence is not automatically extended to later product changes. The old q01-validity title claims are revoked (null, with historical values retained); inventory/time/file-identity history remains separately scoped.

Baseline 0563045: 11 new identity regressions failed / one genuine direct-ID control passed; all three paired-keyword tests failed with actual title mismatches. One initial baseline harness attempt imported a newer helper and failed to import; it is retained locally but is not counted as a product regression. Corrected tests use keyword APIs available on both revisions. Current identity contract: 12 passed; paired public keyword checks: 3 passed. No LS-PrePost or solver run is claimed.

Reproduce from a clean checkout with the shared full environment, PYTHONPATH=src plus repository root, PYTHONDONTWRITEBYTECODE=1 and OPENBLAS_NUM_THREADS=1. Set LSPP_CORPUS_DIR to the external registered corpus; optionally set LSPP_TITLE_EVIDENCE_DIR to a fresh directory outside the repository.

```text
python -m pytest tests/test_part_title_identity_review02.py tests/test_part_title_keyword_oracle.py -q
```

Q01 remains partial pending broader native/HSV/deletion checks and independent review. Unconfirmed user-PID tables remain an explicit operational limitation; they are not treated as certified identifiers. No raw corpus, title text or local absolute path is published.

## Q05 shared-reader refresh

After history validity/filter changes in lasso_backend, the three paired public keyword/title cases were rerun on clean 8c972f58f45344fbd45543b2dc85dfd0c6f9e4c5: 3 passed, 16 Parts, all input bytes unchanged. The initial 7c5d801 capture is retained in previous_captures; active product blobs/cases refer to this fresh run. No native title claim is added.

Review02 wrapper refresh: the three independent keyword oracles were rerun at `35df3aa1fc87dea130d9dc3bfa75f8225dd38512` (3 passed, 16 Parts). The active product blobs and prior captures are in evidence.json; the initial revision above remains historical.

History-point follow-up refreshed the shared-reader blob and three independent paired-keyword oracles at clean 2ccdc34 (16 Parts); active source identities and flat history are in evidence.json.

Beam-force follow-up: the independent title suite was genuinely rerun on clean `eda59350720f8ebf89e1120ba1cc657f542dfb9e`: 15 tests passed, three paired-keyword cases/16 Parts matched, keyword trees and result families unchanged. Active product blobs and cases now bind that run; the preceding 2ccdc34 capture is preserved unchanged in previous_captures. This is not native title verification or a Q01 done upgrade.

2026-11-05 Q05原生接入更新共享读取层后，在干净0a9d74145ac4a6bb6b73a1afe29cc6bd6dfcc82e实际重跑三份独立关键字标题oracle：15通过、16Parts，标题/关键字树/结果族均不变。此前eda5935及更早捕获完整保留；仍非原生证据、Q01仍partial。

2026-11-05 I01结果族防护后，在干净f31b06eb047ed3d97d58b2c8e1ab23424951997c真实再跑15项标题测试、3配对输入/16Parts，标题与源树/结果族均不变。源身份现列入真实依赖family.py，存在性及active blob门禁均要求覆盖它；旧e5及更早捕获保留在独有I01台账与previous_captures，不改写执行revision，仍不是原生标题验收。

2026-11-05 CI路径分类修复后，在干净a20d70e8b609f1c00a78b48266a3d4ff516f6f29再次真实15测试/3捕获通过，16Parts与配对关键字一致、源不变；新增family源blob由本次实跑绑定，旧f31等全部捕获保留，不将旧数据改绑新代码。

2026-11-05：named numeric写入修复后，在干净eeff496c168cf5f02afee66e76bb97adc5d2744f实际15测试/3公开捕获通过（12.79s），16个Part与独立配对关键字标题一致、原树/结果族未变。8个产品blob绑定本次实际源，合并1246f72的对应blob相同；旧be324及以前所有对象追加保留。这是host/LASSO公共oracle，不是新native测试。
