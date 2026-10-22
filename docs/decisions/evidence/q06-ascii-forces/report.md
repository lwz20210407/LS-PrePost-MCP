# Q06：按名称读取 ASCII 接触力与截面力

`extract_database` 可直接读取显式的 `rcforc` / `secforc` 文件，输出沿用
JobResult 和已校验 CSV。保持原工具名、签名及二进制 MPP 合并入口。

- RCFORC：旧 slave/master 和新 SURFA/SURFB 格式；按写入值读取三向力、质量及存在的三向力矩。
  CSV 的键是 time/entity_id/side；即使只有一侧也保留 side。单面接触的 undefined resultant
  只作警告，不生成零曲线；请求该缺失 ID 会失败。
- SECFORC：显式三行列标题及完整 force/moment/centroid 记录；读取存储的力、力矩、模、重心与面积。
  `coordinate_system_ids` 按存储列排列，选取后的 `stored_columns` 给出对应关系；不变换坐标系。
- 不排序、不插值、不补值。各实体时间轴必须一致且严格递增；重复、截断、缺少字段、非有限值、
  坐标系变化或未知布局均失败且无 verified 产物。上限 256 MiB、单行 16384 字符、100 万实体记录。
- ASCII 不读伴随文件；显式 branch/shard 被拒绝。输入仍经过 Settings 的允许目录检查。

## 验证

- 主干 `7ec14ac` 上的八个可用性反例全部失败；新增测试使用合成数据，不包含原始求解输出。
- 相关读取器、MPP、能量工具与有效性测试：101 passed / 2 skipped；跳过项是本机不允许的符号链接。
  扩大检查发现能量工具也调用二进制路径准入函数；已保留该调用兼容性并纳入回归。
- 干净提交 `80f1ff024f896ac09a061558c8ec53553936dfe4`：六项公开语料检查通过。
  五份有数据的文件共 9012 行 x-force 与独立原始 token 核对一致；另一份只有标题的 SECFORC
  按预期失败。源 SHA256 与目录清单前后不变。逐例来源 ID、文件指纹、测试源码 blob 和报告哈希见
  [evidence.json](evidence.json) 与 [corpus-report.md](corpus-report.md)。

这是纯 Python/L1 与公开文件核对，没有运行 LS-PrePost。Q06 保持 partial：其余 ASCII 库、
MPP/SMP 同模型成对验证及与 LSPP 的原生交叉校验仍待完成。没有复制语料或公开派生曲线。
