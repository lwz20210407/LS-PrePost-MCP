# I01：六项公开 Win32 面板原生回归

在干净 3939b5b 上，LS-PrePost 4.13.4 的节点/壳/部件重编号、Keyword Check、
壳质量、Hex8 实体质量六项全部通过。每项检查关联 engine-result.json、模型/ID/坐标
或失败单元结果、保存重开、PNG 和原始输入字节，并关闭本次创建的会话。

[证据 JSON](evidence.json)包含实际 Git revision、working_tree_dirty=false、空 diff 的 SHA256、
源码快照、六项状态及原始报告指纹。原生保存的自产小模型在 PyDYNA 读回时产生 12 条
卡片尾部字符提示；实际断言范围以上述六项为准，原始输出在外部报告保留。
I01 仍 partial：大结果族与 Include 路径限制保留。此次没有 UU 断开和 4.10 面板验收。
