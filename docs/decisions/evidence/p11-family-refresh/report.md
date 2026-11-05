# P11：I01结果族修复后的原生证据刷新

本目录独立登记干净a20d70e8b609f1c00a78b48266a3d4ff516f6f29的两轮原有P11验收，不改写旧p11-raw-review02任何run对象或validity，不把旧run改绑新源码。
service.py整blob因I01守卫修复变化，旧active P11证据已不再匹配；本次用原scope真跑，未修改/放宽test_raw_save_evidence_review02门禁。

| 版本 | P11 pytest | P11业务结果 | P11真实原生job | 额外范围 | 有效性 |
|---|---|---|---|---|---|
| 4.13 | 12 passed / 0 skipped | 10 succeeded、1 partial、1 expected failed | 23 | 同轮另2个beam passed，非P11正例 | 当前有限证据（a20产品blob） |
| 4.10 | 12 passed / 0 skipped | 10 succeeded、1 partial、1 expected failed | 23 | 无beam | 当前有限证据（a20产品blob） |

4.13原始合并pytest为14 passed，4.10为12 passed。不能写“24个正向保存成功”；mismatch负例每版仍实际运行1次before-save观察，随后按计数守卫拒绝，非启动前拒绝；placeholder每版为partial。
源、目录、二进制及配置守卫均通过；两个版本串行执行，没有GUI/UU/solver，结束无残留进程，lease已释放。

分版记录：[4.13](report-413.md)、[4.10](report-410.md)，紧凑数据及LF报告校验：[evidence.json](evidence.json)。
只复用旧active r05原12条相关产品源码路径，均按a20 Git对象记录；原始完整source snapshot SHA保留为审计，不能据此声称每个文件都执行过。
active_product_evidence指针由根协调步骤处理，本目录不改旧指针、旧记录、q01/q05共享JSON或任务状态。
不将此capture外推为Q01/MATSUM/NODOUT原生、所有场景支持、用户安排的外部独立审阅或task-done。原始语料/日志/本机路径留本地。
