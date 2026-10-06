# I03 剩余路径构建与 SCL 编码回归

16 处调用（10 个模块）迁入 import_keyword、open_xydata、save_xypair、
modelcheck_report；九处 SCL 写入使用同一 UTF-8、LF、无 BOM 写入器。
保留嵌入式 Python 3.6 语法，AST 守卫阻止在业务模块重新拼接这些命令。

4.13.4 与 4.10.1 各三项后台原生用例通过：

- 导入节点后保存、重开，独立核对新增节点 ID 1001 及坐标 (7,8,9)。
- XY 数据读入与导出，逐项比较三个曲线点。
- UTF-8 中文注释和 CRLF 输入经 SCL 写入器后，以原生执行结果确认节点计数。

实际 revision 与运行时 git diff SHA256 见 [evidence.json](evidence.json)。
原始补丁和原生日志保留在外部 i03paths-n1；未运行 GUI/UU。
GUI 模型检查等调用的命令字符串回归已覆盖，窗口内原生复核仍为 I03 gap。
