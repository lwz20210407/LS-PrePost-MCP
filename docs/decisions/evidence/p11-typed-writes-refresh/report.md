# P11：typed named writes 后不可变私有配置源的两版复验

实际源`1289eb4edadb77b71d3ee90928d3fec0716e8465`，snapshot `611d3bbb306a082a370743dfe5e722ab0e847dc450d3a8185c7343216c3af2a8`。两版各原12断言、业务10success/1partial/1expectedfailed、各23真实进程；见[413](report-413.md)、[410](report-410.md)与[evidence](evidence.json)。

实际输入是已批准、只读的私有snapshot（413 b07、410 d018），逐job配置source的路径关系与SHA在私有审计中核对。两源完整before/after字节/stat、程序、公开输入与源保持；live globals仅passive observation，即便变化也不冒为这些输入的变化，亦不反推全局写保护成立。
老r1 global guard失败、后续外部并发渲染关联推断及旧be324/其他live记录均照原事实保留；这不是重构f59 before或倒改旧结果。最初Root169 preflight因live410已变化而0native停止，保留为单独准备失败，不当成这轮case。

Source40是本统一批次的31关键源码+9辅助，P11仍对其原十四路径及两native测试精确绑定。65个底层job.succeeded不等于P11外层24个业务全成功。
4.10资源fixed4.9.0.1/string4.10.0.1/conflict=true原样；不把一段有限回归升为全版本认证。

## 复跑合同

仅在root单一串行授权下，用相同已批准的私有readonly配置源，设置`LSPP_CONFIG_SOURCE`为该版本snapshot（不使用live global为输入）。同时显式PYTHONPATH为worktree的src与root、PYTHONDONTWRITEBYTECODE=1、LSPP_CORPUS_DIR为已有公开登记根，TEMP/TMP与输出在仓库外新目录。
运行`python -B -m pytest tests/test_save_model_native.py tests/test_save_search_paths_native.py --run-native --native-strict --native-executable <已登记程序> --native-output <新目录> -q -p no:cacheprovider`。
每版结束及整批后核全部私有input bytes/stat和程序，核逐manifest source对应正确版本；global变化另记被动观察，不替代input守卫。原生日志/配置正文/绝对路径留本地。
