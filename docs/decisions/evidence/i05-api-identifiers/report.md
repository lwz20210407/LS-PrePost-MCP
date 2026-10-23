# I05：API 标识符的索引侧拆词

旧主干 c0a4549 上，SCLGetDataCenterFloatArray 只有完整的小写标识符进入 FTS，
查询 data center float array 无命中。SCLSwitchStateTo、getUserNodeId 和带缩写的
VTKFileReader / XMLHTTPRequest 同样不能按普通词组检索。

仅为 API 文档的索引 token 增加大小写/下划线边界拆分，保留完整标识符、原始文本、
文档身份、SHA256、行号、locator、版本、许可及私有可见性。查询归一化与其他五类
资料的索引口径不变；没有修改词表、评测题或排序权重。

五个反例在旧实现失败、两个对照通过；修复后相关检索测试 73 passed。
测试覆盖私有资料默认隐藏/显式启用、原文及定位未改、完整函数名仍命中，
非 API 类 token 逐字相同，以及旧 schema-v2 索引仍可读且查询不写回。

schema_version 仍为 2；新建索引的 metadata.api_tokenization 为 identifier-parts-v1。
旧索引没有该列时继续按原有只读搜索运行；获得新拆词能力必须显式重建，
不会在查询时隐式升级或覆盖现有文件。构建器仍采用原子、不覆盖发布。

这是合成引用夹具的管线验证，未将真实私有 Scripting API/用户指南导入仓库，
不宣称六类真实来源已齐全，也不将调优题或上述查询视为 A10 独立留出评测。
I05/A10 保持 partial。没有启动 LS-PrePost，也没有执行被索引的文本。
