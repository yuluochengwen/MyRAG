# MyRAG 参数调优与文本切分指南

本文面向当前项目实现，覆盖两部分：
- 传统 RAG 的参数调优顺序与推荐档位
- 文本切分策略的选择、参数与排障

关联实现文件：
- [Backend/config.yaml](Backend/config.yaml)
- [Backend/app/core/config.py](Backend/app/core/config.py)
- [Backend/app/services/knowledge_base_service.py](Backend/app/services/knowledge_base_service.py)
- [Backend/app/utils/text_splitter.py](Backend/app/utils/text_splitter.py)
- [Backend/app/utils/semantic_splitter.py](Backend/app/utils/semantic_splitter.py)
- [Backend/app/api/knowledge_base.py](Backend/app/api/knowledge_base.py)

## 1. 参数调优总原则

1. 先调召回，再调重排，最后调阈值。
2. 每次只改一组参数，观察 50 到 100 条真实问答样本。
3. 以业务指标为准：命中率、空召回率、回答可用率、延迟。
4. 先保障稳定性，再追求极限效果。

## 2. 先看四个核心指标

建议从检索监控文件观察：
- 文件路径：data/logs/retrieval_metrics.jsonl

关键指标解释：
1. candidate_count 过小：召回不足，优先提高 recall_k。
2. returned_count 过小：阈值偏严，放宽 base_score_threshold 或 relative_margin。
3. after_rerank 与 returned_count 差异大：说明重排作用强，需重点调 rerank_alpha、mmr_lambda。
4. elapsed_ms 过高：减少 query rewrite 变体、降低 recall_k、关闭 cross-encoder。

## 3. 传统 RAG 参数调优顺序

第一步：召回池大小（决定上限）
- vector_retrieval.enable_two_stage
- vector_retrieval.recall_factor
- vector_retrieval.min_recall_k
- vector_retrieval.max_recall_k

调优建议：
1. 先固定 top_k=5。
2. 让 candidate_count 稳定在 20 到 80 区间。
3. 若知识库很大且问题复杂，可上探到 100+；若延迟敏感，控制在 30 到 60。

第二步：阈值策略（控制噪声）
- vector_retrieval.base_score_threshold
- vector_retrieval.relative_margin
- vector_retrieval.min_keep_results

调优建议：
1. 空召回高：下调 base_score_threshold 到 0.15 到 0.2。
2. 误召回高：上调 base_score_threshold 到 0.25 到 0.35。
3. 如果 top1 波动大，优先调整 relative_margin（0.05 到 0.12 常用）。

第三步：轻量重排（控制排序质量）
- vector_retrieval.enable_light_rerank
- vector_retrieval.rerank_alpha

调优建议：
1. 文档术语精确且格式化强：适当降低 rerank_alpha（0.6 到 0.7），让词法信号更有权重。
2. 语义表达多样：提高 rerank_alpha（0.75 到 0.85），优先语义相似度。

第四步：去冗余与覆盖度
- vector_retrieval.enable_mmr
- vector_retrieval.mmr_lambda
- vector_retrieval.enable_cluster_dedup
- vector_retrieval.cluster_adjacent_window
- vector_retrieval.max_chunks_per_cluster
- vector_retrieval.max_clusters_per_file

调优建议：
1. 如果返回内容重复：降低 mmr_lambda（0.6 到 0.7）。
2. 如果返回离题：提高 mmr_lambda（0.75 到 0.85）。
3. 资料很碎时增大 cluster_adjacent_window（1 到 2）。

第五步：查询改写与融合
- vector_retrieval.enable_query_rewrite
- vector_retrieval.query_rewrite_max_variants
- vector_retrieval.enable_multi_query_fusion
- vector_retrieval.fusion_method
- vector_retrieval.rrf_k

调优建议：
1. 口语化提问多：开启 query rewrite，变体数 2 到 3。
2. 延迟敏感：变体数控制在 1 到 2。
3. 默认 fusion_method 使用 rrf 更稳。

第六步：可选 cross-encoder 重排
- vector_retrieval.enable_cross_encoder_rerank
- vector_retrieval.cross_encoder_model
- vector_retrieval.cross_encoder_top_n
- vector_retrieval.cross_encoder_alpha

调优建议：
1. 先在离线评测开，不要一开始全量线上开。
2. cross_encoder_top_n 推荐 10 到 20。
3. 延迟超预算时先降 top_n，再考虑关掉。

## 4. 三档推荐参数（可直接起步）

小型知识库（少于 5 万 chunk，优先低延迟）
- recall_factor: 6
- min_recall_k: 20
- max_recall_k: 60
- base_score_threshold: 0.22
- relative_margin: 0.06
- rerank_alpha: 0.78
- mmr_lambda: 0.72
- query_rewrite_max_variants: 2
- enable_cross_encoder_rerank: false

中型知识库（5 万到 50 万 chunk，均衡）
- recall_factor: 8
- min_recall_k: 30
- max_recall_k: 120
- base_score_threshold: 0.2
- relative_margin: 0.08
- rerank_alpha: 0.75
- mmr_lambda: 0.7
- query_rewrite_max_variants: 3
- enable_cross_encoder_rerank: false（评测后按需开启）

大型知识库（50 万 chunk 以上，优先效果）
- recall_factor: 10
- min_recall_k: 40
- max_recall_k: 180
- base_score_threshold: 0.18
- relative_margin: 0.1
- rerank_alpha: 0.72
- mmr_lambda: 0.65
- query_rewrite_max_variants: 3
- enable_cross_encoder_rerank: true
- cross_encoder_top_n: 20

## 5. 文本切分策略说明

当前项目采用两种切分路径：
1. 规则切分（LangChain RecursiveCharacterTextSplitter）
- 实现： [Backend/app/utils/text_splitter.py](Backend/app/utils/text_splitter.py)
- 特点：快、稳定、可控，适合大多数场景

2. 语义切分（短文本优先，LLM 辅助）
- 实现： [Backend/app/utils/semantic_splitter.py](Backend/app/utils/semantic_splitter.py)
- 调度逻辑： [Backend/app/api/knowledge_base.py](Backend/app/api/knowledge_base.py)
- 特点：语义边界更自然，但耗时高、依赖模型稳定性

### 5.1 当前切分切换逻辑

在文件入库流程中：
1. semantic_split.enabled=true 且文本长度小于 short_text_threshold 且 use_for_short_text=true
- 使用语义切分（use_llm=true）
2. semantic_split.enabled=true 且文本较长
- 使用语义切分器的规则模式（use_llm=false）
3. semantic_split.enabled=false
- 使用 TextSplitter 规则切分

### 5.2 切分参数如何影响检索

1. chunk_size
- 太小：召回更细但噪声增多，回答上下文不完整。
- 太大：语义混杂，定位不准，召回命中率下降。

2. chunk_overlap
- 太小：跨段信息断裂。
- 太大：重复内容增加，存储和检索成本上升。

3. separators
- 分隔符优先级越合理，语义完整性越好。

4. semantic_split.short_text_threshold
- 越大：更多文档走 LLM 语义分割，质量可能提升但吞吐下降。

## 6. 文本切分推荐起步值

中文知识库（通用文档）
- chunk_size: 700 到 900
- chunk_overlap: 80 到 120
- semantic_split.enabled: true
- semantic_split.short_text_threshold: 3000 到 5000

技术文档（含代码、参数表）
- chunk_size: 500 到 700
- chunk_overlap: 80 到 120
- code 文档优先用规则切分，不建议大量使用 LLM 语义切分

长报告/制度文档
- chunk_size: 900 到 1200
- chunk_overlap: 120 到 180
- 若主题跨度大，建议开启 query rewrite 和 MMR

## 7. 文本切分排障手册

问题一：检索命中但回答不完整
- 提高 chunk_overlap
- 降低 chunk_size 或优化 separators
- 观察是否出现大量截断上下文

问题二：检索结果重复很多
- 开启或加强 MMR
- 降低 max_chunks_per_cluster
- 降低 cluster_adjacent_window

问题三：空召回突然升高
- 检查切分后 chunk 数是否异常减少
- 检查文件解析质量
- 放宽 base_score_threshold 并提高 recall_k

问题四：入库太慢
- 优先规则切分
- 降低 short_text_threshold
- 减少 query rewrite 变体（检索时）

## 8. 建议的落地流程

1. 先用中型档参数上线灰度。
2. 收集 3 到 7 天 retrieval_metrics.jsonl。
3. 按业务问题类型分桶（FAQ、说明文档、流程类、技术类）。
4. 分桶调参并固化到 config.yaml。
5. 每次迭代只改 2 到 3 个参数，避免相互干扰。
