# A08：配方定义与兼容入口

配方以 recipe.yaml + 原生模板保存，声明任务 ID、通道、参数 JSON Schema、
输出合同、版本证据、L2 用例和两种批处理模式。参数先校验，未知属性和
布尔充当数值均拒绝；schema 不读取远程引用。模板不能逃出配方目录。

find_recipe 默认列出带验证记录的内置配方；include_candidates=true 可检索
工作目录中的旧 JSON 模板。run_recipe 接收内置 ID 或授权的 YAML/JSON 路径，
通过现有 run_script/程序引擎执行，保留定义、模板、参数与产物身份。
旧 create_native_macro/run_native_macro 是此配方模块的兼容别名，保留原 JSON
和返回方式至 v0.6；不会将这些 JSON 模板称作原生 .mac，也不改写用户旧文件。

五个示范配方：Block Mesher 建盒、整体节点平移、PNG、SCL 坐标 CSV、Python
模型计数。当前内置配方只登记 batch/keyword，保持可核对的验收范围。
每项均有独立 L2 检查；建盒另测参数变体。

| 模式 | 4.13.4 | 4.10.1 |
|---|---|---|
| c= -nographics | 五配方及参数变体通过 | 五配方及参数变体通过 |
| runc= | 建盒、平移、CSV、计数通过；PNG 失败 | 建盒通过；其余四项失败 |

失败模式标为 evidence_only/xfail，不计为能力通过；不同版本结果不得互相
替代。[原生报告和身份记录](evidence/a08/report.md) 不含原生日志正文或私有路径。
公共默认仍是 c= -nographics；显式 runc 请求不会自动回退。

A02 的逐配方模式登记已收口。A08 保持 partial：M1 的五配方退出条件已达成，
v0.5 发布前的三十配方及全部安装过滤器/模板归并仍须完成。
