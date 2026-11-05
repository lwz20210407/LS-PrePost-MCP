# P11：typed keyword matching 后的新两版捕获

实际产品 `be3244df3073c6e9b99ac052c093015bbf0419e5`；P11保持partial，仅复验既有12项范围。新r2每版12pytest通过，业务为10 succeeded / 1 partial / 1预期failed，各23个真实无图形进程。
4.13与4.10分别见[报告413](report-413.md)、[报告410](report-410.md)，完整来源、profile和SHA见[evidence](evidence.json)。

| 捕获 | pytest与实际进程 | 整体身份守卫 | 有效性 |
|---|---|---|---|
| r1，原两版本 | 各12断言通过/23进程 | source410配置真实hash变化，总guard=false | 历史失败，不作current |
| r2，4.13 |12 passed/23进程|两版profile程序/配置SHA、完整stat与私有字节测量均保持|当前列明14产品blob/原12case |
| r2，4.10 |12 passed/23进程|同上；4.10资源fixed4.9/string4.10冲突仍在|当前有限regression_subset |

旧r1 source410配置从`f59e5aad3dec287ead099170e82dc85ee891706e4e605989c956bb980cf0be43`变到`f5ed6231d4b4595ea8a4e482b936b835ffaf833262350b55aca1f28cc7e06cce`，writer与确切归属未证；没有修改/回填旧raw。历史私有副本可作差异审计，完整batch-before源字节没有保存，缺测不补true。
r2是自然变化后新输入的新捕获，保存before/after字节并对每版边界和整批核对；其通过不证明任意全局配置写隔离，也不等于I02代码造成或修复了r1变化。
旧p11-family-refresh与p11-raw-review02所有run对象原样保留，新active指针只选本目录r2。

产品原12路径加matching/_identity=14，完整snapshot不代表所有模块功能覆盖。业务预期failed已启动一次原生计数检查，不是预分发拒绝；placeholder的partial不计完整成功。GUI/4.8/广泛变体与物理验收不扩张。

## 原范围复跑与环境

先在授权串行窗口保存两版源配置的完整私有字节副本及SHA/size/mtime/device/inode，并在每版边界和整批末尾复测两版程序/config；任何漂移停止，不自动第三轮。监控runner SHA见evidence，原测量与备份仅留本地。
以下是既有12case的实际pytest范围；单独运行pytest不能替代上述跨版本监控。

```powershell
$env:PYTHONPATH = "<worktree>\src;<worktree>"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTEST_ADDOPTS = ""
$env:LSPP_CORPUS_DIR = "<已登记公共corpus>"
$env:TEMP = "<本任务仓库外scratch>"
$env:TMP = $env:TEMP
python -B -m pytest tests/test_save_model_native.py tests/test_save_search_paths_native.py -x -q -p no:cacheprovider --run-native --native-strict --native-executable "<已登记4.13程序>" --native-output "<全新413输出>"
# 4.13完整结束、无live native且两profile守卫通过后，再执行：
python -B -m pytest tests/test_save_model_native.py tests/test_save_search_paths_native.py -x -q -p no:cacheprovider --run-native --native-strict --native-executable "<已登记4.10程序>" --native-output "<全新410输出>"
```

### 2026-11-05 后续旁证（不改旧 r1 结论）

用户明确报告13:24:59未手工更改LSPP配置。独立外部4.10渲染任务的owned进程回执（PID2344，13:24:50.182）、版本banner/日志末尾（13:24:59.594）与配置mtime（13:24:59.502）及最近命令标记相符；该launcher没有显式MCP偏好隔离，仅设置TEMP/TMP。证据级别为corroborated inference，无内核WriteFile归属审计，不能据此认定MCP4.13写入全局配置。旧r1仍为failed，r2是独立的新成功窗口；外项目路径、模型和原始日志不公开。
