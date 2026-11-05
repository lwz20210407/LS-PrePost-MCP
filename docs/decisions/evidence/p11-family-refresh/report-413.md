# P11 family refresh — 4.13 headless

实际源码提交 `a20d70e8b609f1c00a78b48266a3d4ff516f6f29`，工作树干净，git diff为空。保留旧active r05的同一组12条产品源码路径，按本次a20的Git对象重新登记；不把无关mixins机械加入门禁。

P11 **12 passed / 0 failed / 0 skipped** 是pytest断言结果；业务结果为 **10 succeeded、1 partial、1 expected failed**，不能写成12个正向保存成功。
placeholder为带限制的partial；mismatch在真实before-save原生观察后因预期计数不一致而拒绝，不能说成启动前拒绝。
12个case均实际执行原生，共23个PID-bearing原生job；没有“无进程的通过case”。所有job均returncode=0、无超时、graphics=false且带-nographics。

本次4.13原始pytest同时顺序跑了beamip、ansys-beam两个beam用例，总计14 passed；本P11报告只登记其中原有12项，两个beam不算P11正例。

| case | pytest | 业务结果 | 角色 | 实际原生job | 输入守卫 |
|---|---|---|---|---|---|
| edited | passed | succeeded | positive_save_reopen | 2 | true |
| edited-search | passed | succeeded | positive_save_reopen | 2 | true |
| empty | passed | succeeded | positive_save_reopen | 2 | true |
| include | passed | succeeded | positive_save_reopen | 2 | true |
| mismatch | passed | failed | expected_count_mismatch_refusal_after_native_before_save | 1 | true |
| placeholder | passed | partial | placeholder_partial_roundtrip | 2 | true |
| public-edited | passed | succeeded | positive_save_reopen | 2 | true |
| public-include | passed | succeeded | positive_save_reopen | 2 | true |
| relative-search | passed | succeeded | positive_save_reopen | 2 | true |
| search | passed | succeeded | positive_save_reopen | 2 | true |
| standalone | passed | succeeded | positive_save_reopen | 2 | true |
| unused-search | passed | succeeded | positive_save_reopen | 2 | true |

正例及partial保存后均按保存根目录和相对主文件名重开，after_reopen的normalized=false，节点/单元计数一致；搜索目录case的保存树可读、没有missing_search_dir。
原始主文件/INCLUDE树字节守卫通过；整轮额外核对已登记输入SHA、目录清单及目录内文件字节，配置及二进制SHA前后不变。原生进程已全部退出，lease已释放。

程序 `lsprepost4.13.exe` / 资源版本 `4.13`，SHA256 `ce76fdf75a2f14c0a3e94964809ddd178934d04381f7f31e1e1eb05592bd5414`。
源配置SHA256 `b07a0f5466e4a3c438c4b98f78e4a8e193249c6ed1c8f8c4cb465a4d7bde4958`。不发布本机绝对路径、原生输出、输入文本或私有执行上下文。

## 产品源码身份

| 路径 | 本次Git blob |
|---|---|
| `src/ls_prepost_mcp/service.py` | `3206a328b3c93559cb8c84669bad2e068d2dd1f3` |
| `src/ls_prepost_mcp/model_save.py` | `70818a9af9e391b69a0cf60d1333ac5c9351ea75` |
| `src/ls_prepost_mcp/embedded.py` | `889f81106a339ced4a4c714535e32775ef4d408d` |
| `src/ls_prepost_mcp/keyword_staging.py` | `94123a478a9120d60fcc4a3f9a59c9940aefe256` |
| `src/ls_prepost_mcp/config.py` | `a63023b60176e4dc757e876345a0403dc55fd770` |
| `src/ls_prepost_mcp/core/contracts.py` | `43126d7c12aa28647d9c0d70e4da1edc37ac5847` |
| `src/ls_prepost_mcp/domain/model/access.py` | `a07323c01b32b0fbe282c76873b4c8bc73a4a3ad` |
| `src/ls_prepost_mcp/domain/model/includes.py` | `9d62c28cbdb610a596b275cd0c737482535c0571` |
| `src/ls_prepost_mcp/domain/model/tree.py` | `58e685c97ba5047c59de00440e5605ba77c05a4d` |
| `src/ls_prepost_mcp/domain/model/persist.py` | `cfcd83547e7c549a6ea78acf1160acdc0d16dbb8` |
| `src/ls_prepost_mcp/domain/model/deck.py` | `820294d3e873711b185bed394c77ee2c0baefbc0` |
| `src/ls_prepost_mcp/domain/model/preflight.py` | `1fda5108d3d32d0e25f9e607ce7a61ca00daf4fb` |

源码/test blob、逐case进程数和守卫、raw及LF报告SHA见 [evidence.json](evidence.json)。本文件固定UTF-8/LF；其中report_sha256按read_text后UTF-8 encode计算。
原始完整source snapshot SHA单独保留作审计，**不是所有快照文件均被执行的声明**。旧p11-raw-review02/e5等记录不改写或重绑。

## 可复跑范围

从本提交使用已有项目Python环境，设置 `PYTHONPATH=<worktree>\src;<worktree>`、`LSPP_CORPUS_DIR=<已登记corpus>`，输出必须是新的仓库外目录。

```shell
python -B -m pytest tests/test_save_model_native.py tests/test_save_search_paths_native.py -q -x --run-native --native-strict --native-executable "<4.13-exe>" --native-output "<全新仓库外目录>"
```

该命令复跑P11本身。4.13本次实际合并命令在上述两个P11文件后接tests/test_beam_native_check_native.py，以beamip→ansys-beam顺序执行；4.10不追加beam。
4.13的原始整轮pytest耗时 117.63 秒，P11/beam子集不重复累加计数。
本记录仅覆盖既有P11范围；不宣称Q01/MATSUM/NODOUT原生、所有版本/场景、外部独立审阅或task-done。
