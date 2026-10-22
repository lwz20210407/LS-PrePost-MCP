# A10 重复概念与 SQL 深度（2026-10-23）

修复已登记的检索 P2：分词后的中文概念与 query_expansion 原先保留重复项。
它们既反复增加覆盖率分值，也把相同子查询堆进 SQL 表达式。

现在按首次出现顺序保留唯一概念表达式，并按中文 term 去重展开元数据。
没有截断不同概念，没有修改 1000 字输入边界、词表、词形规则、分类/私有内容守卫、
索引格式或结构化关键字字段查找。未借本次修复修改冻结题集或重新宣称 A10 完成。

## 回归

六项反例在 main `465d960` 的未修实现上全部失败：

- 重复节点/背景概念与展开元数据不唯一；
- 节点以及 MPP/节点混合查询返回数百个重复展开项；
- 1000 个“壳”字符仍在允许边界内，但 SQL 抛 Expression tree is too large；
- MPP/壳的混合重复查询也验证去重后的同等检索；
- 长节点文档原本靠重复词的覆盖率压过短背景文档，破坏与未重复查询一致的排序。

```text
python -m pytest tests/test_knowledge_cross_language.py tests/test_knowledge_index.py tests/test_knowledge_tools.py tests/test_keyword_field_lookup.py tests/test_knowledge_query_publication.py -q
66 passed
```

回归只使用通用词和合成 MIT 文档，未依据留出题面调词表。
历史留出集独立性、逐题旧证据及词形覆盖率缺口继续保留；A10 仍为 partial。
