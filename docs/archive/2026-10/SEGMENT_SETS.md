# 选择驱动的原生 Segment 集

`create_gui_segment_set` 创建原生 `SET_SEGMENT`，接收明确的单元ID或同会话、同模型加载代次的 `selection_job`。随后用 `inspect_gui_entity_sets(entity_type="segment")` 分页查询有方向的节点连接和属性。

三种来源：

- `solid_exterior`：标准线性Hex8/Tet4的外表面；相邻面计数覆盖整个实体域，包括未选择/隐藏的相邻单元，不把截取选区的内部界面误作模型外表面。
- `shell_faces`：Tri3/Quad4壳面，方向继承连接顺序。
- `shell_boundary_2d`：XY平面Tri3/Quad4的边界线段，排除共享内边，有向边使域位于左侧；完整外边界因此为逆时针。

`normal_direction` 和 `cosine_min` 根据原始外法向/壳连接法向筛选；`reverse=True` 在筛选后反向，不改变选中的几何面。`length_unit` 显式声明坐标单位；面积/长度来自原生导出坐标，不做隐藏换算。输出完整几何审计文件，包括所有者单元、部件、节点顺序、法向及面积/长度。

创建走受控原生keyword片段导入，几何所有权和方向在新鲜的原生导出上计算，并非声称调用了全部General Selection/Entity Creation面板按钮。导入后核对原生输出的连接顺序、集合属性、完整网格摘要、状态与单元/部件显示标志，以及其他卡片未变。三角形写N4=N3，二维边写N3=N4=0；有向环按循环起点归一，反向不会被当作同一方向。

当前边界：同域标准短格式线性单元；最多20000个请求单元和20000个生成Segment，不是全模型大小限制。邻接依赖共节点拓扑，不检测断开但几何重合的表面，也不认证非匹配网格交界；退化、倒置、重复/非流形及不支持的单元变体拒绝。壳翘曲上限显式可配，默认15度。只支持新建，已有SID拒绝覆盖。Segment创建不等于载荷或无反射边界已建立，二维几何通过也不等于其单元公式适用于无反射条件。

## 原生验收

`tools/run_segment_creation_acceptance.py` 已在最大化可见4.13.4通过：相邻Hex8共10个外表面、局部单元外表面不含未选/隐藏邻居的共享面、法向过滤、改选区/方向的录制回放、Tet4四个三角面、壳面、ELFORM13平面应变模型的六条有向边界边、名称/属性/连接读回、ID冲突/空过滤拒绝及两种模型保存重开。合成原文件字节未变。壳三角路径有代码与几何测试，当前独立原生壳面例以Quad4为主；无求解物理认证。

## 手册依据与版本边界

- [R11关键词手册](https://lsdyna.ansys.com/wp-content/uploads/2026/08/LS-DYNA_Manual_Volume_I_R11.pdf)：SET_SEGMENT、LOAD_SEGMENT及无反射章节；三维三角/四边面与二维二节点线段分别处理。
- [R16关键词手册](https://lsdyna.ansys.com/wp-content/uploads/2026/08/LS-DYNA_Manual_Vol_I_R16.pdf)：已下载并按书签读取相关章节，旧搜索索引中的2025文件地址已失效。
- [R14官方发布说明](https://lsdyna.ansys.com/ls-dyna-r14-0-0-released-2023-05/)：二维无反射条件以负NSID引用Segment集是新增路径。不能用LS-PrePost4.13能保存该卡，推断用户R11求解器也支持它。

3D无反射手册允许两种面片绕序；2D则明确要求逆时针节点链。后续边界工具必须按实际关键词语义判断，不能把某条ALE版本说明推广成所有边界都要反转法向。
