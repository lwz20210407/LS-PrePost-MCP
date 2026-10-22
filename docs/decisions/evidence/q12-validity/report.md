# Q12：缺项安全的能量报告（2026-10-22）

状态：partial。新 `check_energy` 读取 GLSTAT 与可选 MATSUM，经共享读取层输出
JobResult/v1、全局 CSV、部件 CSV 和紧凑摘要；不启动 LS-PrePost 或求解器。
这是对已关闭 #57 中能量问题的重新实现，不带入 Q10 剖切配方。

## 计算与缺项合同

- 八项能量逐项输出：总能量、动能、内能、沙漏能、滑移能、外功、阻尼能、侵蚀能；
  CSV 同时保留读取到的墙、钻孔、弹簧/阻尼器、接头、刚体限位和各侵蚀分量。
  缺项或某一个样本未输出时保留 null；CSV 留空，摘要记录 missing_samples，不补零。
  峰值为已记录样本的代数最大值，不是未知样本的界限。
- 总能量只用记录的 TE，不从不完整分量合成。侵蚀能单独报告；只有三个已记录侵蚀分量
  在同一时刻完整时才求和，不把它们重复加进已记录的 TE。
- 平衡残差：`TE(t)-TE(0)-(W(t)-W(0))`。需要记录的 TE 和外功；少于两帧或缺数据时
  请求的平衡检查为 not_applicable / incomplete，不能判通过。
- 相对残差分母：`max(abs(TE(0)+(W(t)-W(0))), max_t(abs(TE)))`。
  没有绝对数值 1.0 的下限；relative_floor 默认 1e-12，是相对于整个记录能量尺度的比例。
  零分母保留 undefined，摘要有 undefined_samples。
- 筛查使用 `abs(KE/HG/SI)/abs(IE)`。只在分母非零且不低于
  `ratio_floor*max(abs(IE))` 的样本计算，ratio_floor 默认 1e-3，可显式配置；
  摘要报告 defined/undefined 数。缺测与小分母区别保留，缺测不能获得 passed。
- 阈值默认均为 None，只报告指标，不给通过/失败结论。显式阈值下区分 passed、exceeded、
  incomplete；执行成功和阈值超限通过 JobResult.status / checks 分开表达。
- MATSUM 使用真实存储 ID，结果字典为字符串键；HG 续行归入当前部件。
  部件时间轴独立保留在 CSV，不插值到 GLSTAT，不把内能直接解释为材料塑性耗散。

## 读取、产物与边界

ASCII 只接受命名 time/energy 块，普通八列表格明确失败；MATSUM 跳过 legend。
binout 完全调用共享 `lasso_backend.binout_curves` / `mpp_shards.read`，新增的
MissingComponentError 区分“没有输出此量”和读取/身份冲突，后者不会变成缺项零值。
标准文件族与 continuation 均经过现有允许目录检查；非标准二进制文件名明确拒绝，
不会悄悄读取同目录的另一个 binout。ASCII 同伴缺失/读取失败明确返回 partial 和原因。

ASCII 单行最多 16384 字符，防止误输二进制或超长记录造成无界缓冲。
全局及部件 CSV 各最多一百万行，超过时明确失败。摘要只保存部件统计，避免把完整
MATSUM 数组再次复制进 JSON。输入使用现有 fingerprint：64 MiB 内含 SHA256，
更大文件用 size/mtime 并给出明确 warning；全内容实验身份仍是后续待办。
输出 Artifact 的 verified 身份只在有 SHA256 与字节数时声明。
写清单失败返回 failed；源文件族成员改变或指纹改变不会报告成功。

## 回归与实际语料

首批 14 个反例在旧 #57 的 a82cabf 能量实现上为 **13 failed / 1 passed**，
修复后通过。覆盖缺失外功/总能量、部分 HG 缺测、MATSUM 续行、普通表格误认、
单位缩放、零能量分母、无阈值和时间回退。后续补充公开接口、坏参数、磁盘写失败、
新增分片和真实 LSDA writer 的双部件回归。

```text
python -m pytest tests/test_energy_validity.py tests/test_energy_tools.py -q
LSPP_CORPUS_DIR=<existing-local-corpus> python -m pytest tests/test_energy_corpus.py -q
```

当前专属回归含 43 项；单部件 binout 曾因共享读取器压平 ID 轴而被误判为不完整，
已在真实 LSDA writer 的一部件/双部件反例上复现并修复，保留原 ID。
可选的已登记公开语料入口 **3 passed**。
该入口未设置 LSPP_CORPUS_DIR 时 skip，不含本机默认路径，不复制语料。
入口首次使用注册器的扩展路径时被输入守卫正确拒绝，后来用已有 plain_path 转回普通路径；
首轮日志保留在仓库外，没有放宽设备/网络路径守卫。

干净提交 `10bf6e0560eef4819f19dae765289dcd6c693118` 上串行读取 11 个公开输入：
6 份 ASCII GLSTAT 和 5 个 binout 入口。执行结果为 4 succeeded、6 partial、1 failed；
partial 原因包括未提供 MATSUM、缺外功、只有一帧；failed 输入实际只有 SWFORC、没有 GLSTAT，
因此保留明确拒绝。阈值 exceeded 表示所选筛查发现偏差，不是读取器执行失败。
所有源族 SHA256 和目录清单均不变，见 [evidence.json](evidence.json)。

同一 Bolt_B 输出的 1000 个时间点按原记录位置比较 ASCII 和 binout，未重采样或合并时间轴；
非缺失字段与时间的峰值归一最大误差不超过 **2.60e-6**（验证限 1e-5），
见 [配对校验](ascii-binout-comparison.json)。六份 ASCII 的非缺失字段与旧已验证块解析逐值相同。
原始输入、完整 CSV、机器路径及私有资料均留在仓库外。

本地完整回归（Python 3.11、完整依赖）：**2332 passed / 292 skipped**。
独立相关回归（能量、任务目录、文档）：**51 passed**。
Ruff、import-linter（3 个合同）及任务/生成文档/工具迁移/语料登记/文档链接检查通过。
首次完整回归发现 tasks.yaml 中未引用的 `#` 截断说明文本，已修复并重新完整运行；
没有把该失败记为通过。以上为同步最新 main 前的本地结果，PR CI 另以最终头为准。

## 尚未完成

没有新增 L2 原生运行或全量求解器交叉验证。非标准 binout 名称、多分片不同实体的
自动合并、全部求解器输出变体、材料专属塑性耗散和全内容实验身份不在本次证实范围内。
保留 Q12 原验收、版本和 partial 状态，不以这些读测替代原生证据。
