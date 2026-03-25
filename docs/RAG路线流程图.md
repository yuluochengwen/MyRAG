# MyRAG 项目中传统 RAG 与 GraphRAG 流程梳理

本文基于当前代码实现整理两条问答路线：
- 传统 RAG（纯向量检索）
- GraphRAG（混合检索：向量 + 关键词 + 图谱）

## 1. 传统 RAG 路线（Vector RAG）

主要入口：
- 对话入口：`/api/conversations/{conversation_id}/chat`
- 关键开关：`use_hybrid_retrieval = false`

```mermaid
flowchart TD
    A["用户请求 /api/conversations/{id}/chat"] --> B["conversation.py 读取 assistant 配置和历史消息"]
    B --> C["调用 ChatService.chat_with_assistant"]
    C --> D{"有 kb_ids 吗?"}
    D -- "否" --> Z["纯对话模式 直接LLM"]
    D -- "是" --> E["KnowledgeBaseService.search_knowledge_bases"]

    E --> E1["校验多个知识库 embedding 配置一致"]
    E1 --> E2["并发调用每个库 search_knowledge_base"]
    E2 --> E3["按知识库 embedding 模型编码 query"]
    E3 --> E4["Chroma 集合 kb_{kb_id} 向量检索"]
    E4 --> E5["格式化结果 + 阈值过滤 + 多库合并排序"]

    E5 --> F{"检索结果为空?"}
    F -- "是" --> F1["返回 未找到相关信息"]
    F -- "否" --> G["ChatService._build_context 构建上下文"]
    G --> H["释放 embedding 显存"]
    H --> I["ChatService._generate_answer 调用 LLM"]
    I --> J["保存 assistant 消息和 sources 到 messages"]
    J --> K["返回 answer + sources + retrieval_count"]

    Z --> J
```

## 2. GraphRAG 路线（Hybrid Retrieval）

主要入口：
- 对话入口：`/api/conversations/{conversation_id}/chat` 或 `/chat/stream`
- 关键开关：`use_hybrid_retrieval = true`
- 关键前提：图谱能力开启且 Neo4j 可用

```mermaid
flowchart TD
    A[用户请求并启用 use_hybrid_retrieval] --> B[ChatService.chat_with_assistant]
    B --> C[ChatService._hybrid_search]
    C --> D{knowledge_graph.enabled?}
    D -- 否 --> D1[降级为 KnowledgeBaseService 向量检索]
    D -- 是 --> E[按 kb_id 循环调用 HybridRetrievalService.hybrid_search]

    E --> V[通道1 向量召回 _vector_search]
    E --> K[通道2 关键词召回 _keyword_search]
    E --> G{通道3 图谱召回可用?}

    G -- 否 --> G1[跳过图谱通道]
    G -- 是 --> G2[_graph_search]
    G2 --> G3[EntityExtractionService.extract_from_text 提取查询实体]
    G3 --> G4[Neo4jGraphService.get_entity_info
精确匹配 -> 归一化匹配 -> 拆分候选匹配]
    G4 --> G5[Neo4jGraphService.find_related_entities 图遍历 max_hops]
    G5 --> G6[格式化实体/关系文本 + 证据块]

    V --> F[Fusion 融合与重排]
    K --> F
    G1 --> F
    G6 --> F

    F --> F1[RRF 融合: vector/keyword/graph 权重]
    F1 --> F2[light rerank 基于 query token overlap]
    F2 --> F3[graph_min_results 图结果保底]
    F3 --> F4[输出 top_k + diagnostics]

    F4 --> H[ChatService 构建上下文并调用 LLM]
    H --> I[返回 answer + sources + diagnostics]
    D1 --> H
```

## 3. GraphRAG 的图谱构建（离线/入库阶段）

GraphRAG 检索依赖上传时构建的图谱，流程在文件上传后台任务中完成。

```mermaid
flowchart TD
    U["上传文件 /api/knowledge-bases/{kb_id}/upload"] --> P["process_file_background"]
    P --> P1["解析文件 parse_file"]
    P1 --> P2["文本切块 semantic_split 或 TextSplitter"]
    P2 --> P3["embedding_service.encode 生成向量"]
    P3 --> P4["写入 Chroma: collection kb_{kb_id}"]
    P4 --> P5["写入 MySQL text_chunks"]
    P5 --> P6["更新文件状态/知识库统计"]
    P6 --> P7["KnowledgeBaseService.build_knowledge_graph"]

    P7 --> Q1["批量导入 Chunk 节点"]
    Q1 --> Q2["EntityExtractionService.batch_extract"]
    Q2 --> Q3["merge_extraction_results 合并实体关系"]
    Q3 --> Q4["Neo4j batch_import_entities"]
    Q4 --> Q5["Neo4j batch_import_relations"]
    Q5 --> Q6["图谱就绪 支撑 GraphRAG 检索"]
```

## 4. 两条路线的核心差异总结

- 召回通道：传统 RAG 仅向量；GraphRAG 为向量 + 关键词 + 图谱三通道。
- 依赖数据：传统 RAG 依赖 Chroma 向量库；GraphRAG 额外依赖 Neo4j 图谱和实体关系。
- 融合策略：GraphRAG 使用 RRF + 轻量重排 + 图结果保底，并输出 diagnostics。
- 兜底机制：GraphRAG 在图谱关闭/异常时自动回退到纯向量检索。

## 5. 关键代码定位

- 对话入口与开关：`Backend/app/api/conversation.py`
- 文件上传与图谱构建触发：`Backend/app/api/knowledge_base.py`
- 传统 RAG 检索：`Backend/app/services/knowledge_base_service.py`
- 混合检索主流程：`Backend/app/services/hybrid_retrieval_service.py`
- 图数据库与图遍历：`Backend/app/services/neo4j_graph_service.py`
- 对话编排与 LLM 生成：`Backend/app/services/chat_service.py`
