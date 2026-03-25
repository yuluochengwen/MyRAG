"""混合检索服务 - 结合向量、关键词和图谱检索"""
import hashlib
import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from app.services.vector_store_service import VectorStoreService
from app.services.neo4j_graph_service import Neo4jGraphService
from app.services.entity_extraction_service import EntityExtractionService
from app.services.embedding_service import EmbeddingService
from app.core.config import settings
from app.core.database import db_manager
from app.utils.logger import get_logger
from app.utils.similarity import normalize_l2_distance_to_similarity

logger = get_logger(__name__)


class HybridRetrievalService:
    """混合检索服务 - 融合向量检索、关键词检索和知识图谱"""
    
    def __init__(
        self,
        vector_store: VectorStoreService = None,
        graph_service: Neo4jGraphService = None,
        entity_service: EntityExtractionService = None,
        embedding_service: EmbeddingService = None
    ):
        """
        初始化混合检索服务
        
        Args:
            vector_store: 向量存储服务
            graph_service: 图谱服务
            entity_service: 实体提取服务
            embedding_service: 嵌入服务
        """
        from app.services.vector_store_service import get_vector_store_service
        from app.services.neo4j_graph_service import get_neo4j_graph_service
        from app.services.entity_extraction_service import get_entity_extraction_service
        from app.services.embedding_service import get_embedding_service
        
        self.vector_store = vector_store or get_vector_store_service()
        self.graph_service = graph_service or get_neo4j_graph_service()
        self.entity_service = entity_service or get_entity_extraction_service()
        self.embedding_service = embedding_service or get_embedding_service()
        
        self.config = settings.hybrid_retrieval
        
        logger.info(
            "混合检索服务初始化: vector_weight=%s, keyword_weight=%s, graph_weight=%s",
            self.config.vector_weight,
            getattr(self.config, 'keyword_weight', 0.5),
            self.config.graph_weight
        )
    
    async def hybrid_search(
        self,
        kb_id: int,
        query: str,
        top_k: int = 5,
        vector_weight: float = None,
        graph_weight: float = None,
        keyword_weight: float = None,
        enable_graph: bool = True
    ) -> Dict[str, Any]:
        """
        混合检索：结合向量检索和图谱检索
        
        Args:
            kb_id: 知识库ID
            query: 查询文本
            top_k: 返回结果数量
            vector_weight: 向量检索权重
            graph_weight: 图谱检索权重
            enable_graph: 是否启用图谱检索
            
        Returns:
            融合后的检索结果
        """
        vector_weight = vector_weight if vector_weight is not None else self.config.vector_weight
        graph_weight = graph_weight if graph_weight is not None else self.config.graph_weight
        keyword_weight = keyword_weight if keyword_weight is not None else getattr(self.config, 'keyword_weight', 0.5)
        
        logger.info(f"开始混合检索: kb_id={kb_id}, query={query[:50]}..., "
                   f"enable_graph={enable_graph}")
        
        # 1. 多路召回（向量 + 关键词 + 图谱）
        recall_k = max(top_k * 4, int(getattr(self.config, 'rrf_window_size', 50) or 50))
        vector_results = await self._vector_search(kb_id, query, recall_k)

        keyword_results: List[Dict[str, Any]] = []
        if getattr(self.config, 'enable_keyword_search', True):
            keyword_results = await self._keyword_search(kb_id, query, recall_k)
        
        # 2. 图谱检索（如果启用且服务可用）
        graph_results = []
        graph_diagnostics: Dict[str, Any] = {
            "query": query,
            "extracted_entities": [],
            "normalized_entities": [],
            "matched_entities": [],
            "unmatched_entities": [],
            "match_details": [],
            "fallback_used": False
        }
        if enable_graph and settings.knowledge_graph.enabled:
            try:
                if self.graph_service.is_available():
                    graph_results, graph_diagnostics = await self._graph_search(kb_id, query, recall_k)
                else:
                    logger.warning("Neo4j服务不可用，跳过图谱检索")
            except Exception as e:
                logger.error(f"图谱检索失败: {str(e)}")
        
        # 3. 结果融合 + 轻量重排
        fused_results = self._fuse_results(
            vector_results,
            keyword_results,
            graph_results,
            vector_weight,
            keyword_weight,
            graph_weight,
            query,
            top_k
        )
        
        logger.info(
            "混合检索完成: vector=%s, keyword=%s, graph=%s, fused=%s",
            len(vector_results),
            len(keyword_results),
            len(graph_results),
            len(fused_results)
        )
        
        return {
            "results": fused_results,
            "diagnostics": {
                **graph_diagnostics,
                "vector_result_count": len(vector_results),
                "keyword_result_count": len(keyword_results),
                "graph_result_count": len(graph_results),
                "fused_result_count": len(fused_results)
            }
        }

    def _tokenize_query(self, query: str) -> List[str]:
        stopwords = set(self.config.query_stopwords or [])
        pieces = re.split(r"[\s,，。！？!?:：;；()（）\[\]{}<>《》、/\\\-|_]+", query or "")
        tokens: List[str] = []
        for piece in pieces:
            current = piece.strip().lower()
            if not current or current in stopwords:
                continue
            if len(current) == 1 and not self._is_all_cjk(current):
                continue
            if current not in tokens:
                tokens.append(current)
        return tokens

    def _normalize_entity_text(self, value: str) -> str:
        if not value:
            return ""

        text = unicodedata.normalize("NFKC", str(value)).strip().lower()
        text = text.replace("（", "(").replace("）", ")")
        text = re.sub(r"[\s\-_/\\|·•,，。！？!?:：;；'\"“”‘’()（）\[\]{}<>《》、]+", "", text)
        return text

    def _is_all_cjk(self, value: str) -> bool:
        if not value:
            return False
        return all('\u4e00' <= ch <= '\u9fff' for ch in value)

    def _build_entity_fallback_candidates(self, entity: str) -> List[str]:
        if not entity:
            return []

        candidates: List[str] = []
        stopwords = set(self.config.query_stopwords or [])
        split_tokens = self.config.compound_split_tokens or []

        replaced = entity
        for token in split_tokens:
            if token:
                replaced = replaced.replace(token, " ")

        for part in re.split(r"[\s,，;；/|]+", replaced):
            part = part.strip()
            if not part or part in stopwords:
                continue
            if len(part) < settings.knowledge_graph.min_entity_length:
                continue
            if part not in candidates:
                candidates.append(part)

        compact = re.sub(r"\s+", "", entity)
        if self._is_all_cjk(compact) and len(compact) >= 4:
            for fragment in [compact[:2], compact[-2:], compact[:3], compact[-3:]]:
                if fragment and fragment not in stopwords and fragment not in candidates:
                    candidates.append(fragment)

        max_candidates = max(0, int(self.config.max_fallback_candidates or 0))
        if max_candidates > 0:
            return candidates[:max_candidates]
        return candidates
    
    async def _vector_search(
        self,
        kb_id: int,
        query: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        向量检索
        
        Args:
            kb_id: 知识库ID
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            检索结果列表
        """
        try:
            # 获取知识库的嵌入模型配置
            from app.services.knowledge_base_service import KnowledgeBaseService
            from app.core.database import db_manager
            
            kb_service = KnowledgeBaseService(db_manager)
            kb = await kb_service.get_knowledge_base(kb_id)
            if not kb:
                logger.error(f"知识库不存在: {kb_id}")
                return []
            
            # 生成查询向量（使用知识库的嵌入模型）
            query_embedding = self.embedding_service.encode_single(
                query, 
                model_name=kb.embedding_model,
                provider=kb.embedding_provider
            )
            
            # 向量检索
            collection_name = f"kb_{kb_id}"
            search_results = self.vector_store.search(
                collection_name=collection_name,
                query_embeddings=[query_embedding],
                n_results=top_k
            )
            
            # 格式化结果
            results = []
            if search_results and 'documents' in search_results and len(search_results['documents']) > 0:
                for i in range(len(search_results['documents'][0])):
                    # 统一使用normalize_l2_distance_to_similarity
                    distance = search_results['distances'][0][i] if 'distances' in search_results else 0
                    similarity = normalize_l2_distance_to_similarity(distance)
                    
                    results.append({
                        'content': search_results['documents'][0][i],
                        'score': max(0, similarity),  # 确保非负
                        'metadata': search_results['metadatas'][0][i] if 'metadatas' in search_results else {},
                        'source': 'vector',
                        'chunk_id': search_results['ids'][0][i] if 'ids' in search_results else None
                    })
            
            logger.debug(f"向量检索完成: found={len(results)}")
            return results
            
        except Exception as e:
            logger.error(f"向量检索失败: {str(e)}")
            return []

    async def _keyword_search(self, kb_id: int, query: str, top_k: int) -> List[Dict[str, Any]]:
        """关键词召回（轻量实现，基于text_chunks内容匹配）。"""
        try:
            tokens = self._tokenize_query(query)
            if not tokens:
                return []

            like_clauses = " OR ".join(["tc.content LIKE %s" for _ in tokens])
            params: List[Any] = [kb_id]
            params.extend([f"%{token}%" for token in tokens])
            params.append(max(top_k * 3, 30))

            sql = f"""
            SELECT tc.vector_id as chunk_id,
                   tc.content as content,
                   tc.file_id as file_id,
                   tc.chunk_index as chunk_index
            FROM text_chunks tc
            WHERE tc.kb_id = %s AND ({like_clauses})
            ORDER BY tc.id DESC
            LIMIT %s
            """

            rows = await db_manager.execute_query(sql, tuple(params))
            if not rows:
                return []

            scored: List[Dict[str, Any]] = []
            max_score = 0.0
            for row in rows:
                content = row.get("content") or ""
                content_lower = content.lower()

                hit_count = 0
                tf_sum = 0.0
                for token in tokens:
                    count = content_lower.count(token)
                    if count > 0:
                        hit_count += 1
                        tf_sum += min(3, count)

                if hit_count == 0:
                    continue

                coverage = hit_count / len(tokens)
                length_penalty = max(0.6, min(1.0, 300.0 / max(300.0, len(content))))
                score = (0.7 * coverage + 0.3 * (tf_sum / (tf_sum + 2.0))) * length_penalty
                max_score = max(max_score, score)

                scored.append({
                    "content": content,
                    "raw_score": score,
                    "metadata": {
                        "kb_id": kb_id,
                        "file_id": row.get("file_id"),
                        "chunk_index": row.get("chunk_index")
                    },
                    "source": "keyword",
                    "chunk_id": row.get("chunk_id")
                })

            if max_score <= 0:
                return []

            for item in scored:
                item["score"] = round(item.pop("raw_score") / max_score, 6)

            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:top_k]
        except Exception as error:
            logger.error("关键词检索失败: %s", str(error))
            return []
    
    async def _graph_search(
        self,
        kb_id: int,
        query: str,
        top_k: int
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        图谱检索：提取查询中的实体，查找相关知识
        
        Args:
            kb_id: 知识库ID
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            图谱检索结果
        """
        try:
            diagnostics: Dict[str, Any] = {
                "query": query,
                "extracted_entities": [],
                "normalized_entities": [],
                "matched_entities": [],
                "unmatched_entities": [],
                "match_details": [],
                "fallback_used": False
            }

            # 1. 从查询中提取实体（查询通常较短，降低长度限制）
            logger.info(f"[图谱检索] 开始实体提取: query='{query}'")
            extraction_result = await self.entity_service.extract_from_text(
                query, 
                min_length_override=5  # 查询文本允许较短
            )
            entities = extraction_result.get('entities', [])
            
            if not entities:
                logger.warning(f"[图谱检索] 查询中未提取到实体: query='{query}'")
                return [], diagnostics
            
            entity_names = [e['name'] for e in entities]
            diagnostics["extracted_entities"] = entity_names
            logger.info(f"[图谱检索] 提取到实体: {entity_names}")
            
            # 2. 对每个实体进行图遍历
            graph_results = []
            max_hops = settings.knowledge_graph.max_hops
            
            for entity_info in entities:
                entity = entity_info['name']
                normalized_entity = self._normalize_entity_text(entity)
                if normalized_entity and normalized_entity not in diagnostics["normalized_entities"]:
                    diagnostics["normalized_entities"].append(normalized_entity)

                fallback_candidates: List[str] = []
                if self.config.enable_compound_entity_split:
                    fallback_candidates = self._build_entity_fallback_candidates(entity)
                    if fallback_candidates:
                        diagnostics["fallback_used"] = True

                logger.debug(f"[图谱检索] 查询实体: {entity}")
                
                # 获取实体详细信息
                entity_data = self.graph_service.get_entity_info(kb_id, entity, candidates=fallback_candidates)
                if entity_data:
                    match_stage = entity_data.get('match_stage', 'exact')
                    matched_entity = entity_data.get('matched_entity') or entity_data.get('name')
                    diagnostics["matched_entities"].append(entity)
                    diagnostics["match_details"].append({
                        "query_entity": entity,
                        "matched_entity": matched_entity,
                        "match_stage": match_stage,
                        "fallback_candidates": fallback_candidates
                    })

                    logger.info(f"[图谱检索] 命中实体: {entity} -> {matched_entity}, stage={match_stage}, type={entity_data.get('type')}")
                    # 直接命中实体
                    content = self._format_entity_info(entity_data)
                    evidence_chunks = list(dict.fromkeys((entity_data.get('attributes') or {}).get('chunk_ids') or []))[:5]
                    graph_results.append({
                        'content': content,
                        'score': 0.9,  # 直接命中实体，高分
                        'metadata': {
                            'entity': matched_entity,
                            'type': entity_data.get('type', 'Unknown'),
                            'labels': entity_data.get('labels', []),
                            'query_entity': entity,
                            'match_stage': match_stage,
                            'evidence_chunks': evidence_chunks,
                            'source_type': 'direct_match'
                        },
                        'source': 'graph_direct',
                        'entity': matched_entity
                    })
                else:
                    diagnostics["unmatched_entities"].append(entity)
                    diagnostics["match_details"].append({
                        "query_entity": entity,
                        "matched_entity": None,
                        "match_stage": "none",
                        "fallback_candidates": fallback_candidates
                    })
                    logger.warning(f"[图谱检索] 未找到实体: {entity} in kb_{kb_id}")
                
                # 查找相关实体
                traversal_anchor = entity_data.get('name') if entity_data else entity
                related = self.graph_service.find_related_entities(
                    kb_id=kb_id,
                    entity=traversal_anchor,
                    max_hops=max_hops,
                    max_results=5
                )
                
                if related:
                    logger.info(f"[图谱检索] 找到 {len(related)} 个相关实体: {[r['entity'] for r in related[:3]]}")
                
                for rel in related:
                    content = self._format_relation_info(entity, rel)
                    # 跳数越多分数越低
                    score = 0.7 / rel['hop'] if rel['hop'] > 0 else 0.7
                    
                    graph_results.append({
                        'content': content,
                        'score': score,
                        'metadata': {
                            'source_entity': entity,
                            'source_entity_matched': traversal_anchor,
                            'target_entity': rel['entity'],
                            'target_type': rel.get('type', 'Unknown'),
                            'target_labels': rel.get('labels', []),
                            'relations': rel['relations'],
                            'evidence_chunks': rel.get('evidence_chunks', []),
                            'hop': rel['hop'],
                            'source_type': 'graph_traversal'
                        },
                        'source': 'graph_related',
                        'entity': rel['entity']
                    })
            
            # 3. 去重和排序
            seen = set()
            unique_results = []
            for result in sorted(graph_results, key=lambda x: x['score'], reverse=True):
                # 基于来源与实体维度去重，避免截断文本导致误去重
                key = self._make_result_key(result)
                if key not in seen:
                    seen.add(key)
                    unique_results.append(result)
                    if len(unique_results) >= top_k:
                        break
            
            logger.debug(f"图谱检索完成: found={len(unique_results)}")
            diagnostics["matched_entities"] = list(dict.fromkeys(diagnostics["matched_entities"]))
            diagnostics["unmatched_entities"] = list(dict.fromkeys(diagnostics["unmatched_entities"]))
            return unique_results, diagnostics
            
        except Exception as e:
            logger.error(f"图谱检索失败: {str(e)}")
            return [], {
                "query": query,
                "extracted_entities": [],
                "normalized_entities": [],
                "matched_entities": [],
                "unmatched_entities": [],
                "match_details": [],
                "fallback_used": False,
                "error": str(e)
            }
    
    def _make_result_key(self, result: Dict[str, Any]) -> str:
        chunk_id = result.get("chunk_id")
        if chunk_id:
            return f"chunk::{chunk_id}"

        metadata = result.get("metadata") or {}
        if metadata.get("entity"):
            return f"entity::{metadata.get('entity')}::{result.get('source', 'unknown')}"
        if metadata.get("target_entity") and metadata.get("source_entity_matched"):
            return f"path::{metadata.get('source_entity_matched')}::{metadata.get('target_entity')}::{','.join(metadata.get('relations', []))}"

        content = str(result.get("content") or "")
        digest = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
        return f"content::{digest}"

    def _merge_result_payload(self, existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        existing.setdefault("channels", set())
        incoming_channel = incoming.get("weight_type") or incoming.get("source")
        if incoming_channel:
            existing["channels"].add(incoming_channel)

        existing_score = float(existing.get("score", 0.0) or 0.0)
        incoming_score = float(incoming.get("score", 0.0) or 0.0)
        if incoming_score > existing_score:
            existing["score"] = incoming_score
            existing["content"] = incoming.get("content", existing.get("content", ""))
            existing["metadata"] = incoming.get("metadata", existing.get("metadata", {}))
            existing["source"] = incoming.get("source", existing.get("source", "unknown"))
            existing["chunk_id"] = incoming.get("chunk_id", existing.get("chunk_id"))

        return existing

    def _apply_rrf(
        self,
        channel_results: Dict[str, List[Dict[str, Any]]],
        channel_weights: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        rrf_k = max(1, int(getattr(self.config, 'rrf_k', 60) or 60))
        window_size = max(1, int(getattr(self.config, 'rrf_window_size', 50) or 50))

        fusion_map: Dict[str, Dict[str, Any]] = {}
        rrf_scores: Dict[str, float] = {}

        for channel_name, results in channel_results.items():
            if not results:
                continue
            weight = float(channel_weights.get(channel_name, 1.0) or 1.0)

            sorted_results = sorted(results, key=lambda x: x.get("score", 0.0), reverse=True)[:window_size]
            for rank, result in enumerate(sorted_results, start=1):
                key = self._make_result_key(result)
                contribution = weight / (rrf_k + rank)
                rrf_scores[key] = rrf_scores.get(key, 0.0) + contribution

                tagged = dict(result)
                tagged["weight_type"] = channel_name
                if key not in fusion_map:
                    fusion_map[key] = {
                        "content": tagged.get("content", ""),
                        "score": tagged.get("score", 0.0),
                        "metadata": tagged.get("metadata", {}),
                        "source": tagged.get("source", channel_name),
                        "chunk_id": tagged.get("chunk_id"),
                        "channels": {channel_name}
                    }
                else:
                    fusion_map[key] = self._merge_result_payload(fusion_map[key], tagged)

        fused: List[Dict[str, Any]] = []
        for key, payload in fusion_map.items():
            payload["final_score"] = rrf_scores.get(key, 0.0)
            payload["channels"] = sorted(list(payload.get("channels", set())))
            fused.append(payload)

        fused.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
        return fused

    def _light_rerank(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not results:
            return []

        query_tokens = set(self._tokenize_query(query))
        if not query_tokens:
            return results

        alpha = float(getattr(self.config, 'rerank_alpha', 0.7) or 0.7)
        alpha = max(0.0, min(1.0, alpha))

        reranked: List[Dict[str, Any]] = []
        for item in results:
            content_tokens = set(self._tokenize_query(item.get("content", "")))
            overlap = 0.0 if not content_tokens else len(query_tokens & content_tokens) / len(query_tokens)

            rerank_score = alpha * float(item.get("final_score", 0.0) or 0.0) + (1 - alpha) * overlap
            boosted = dict(item)
            boosted["rerank_score"] = rerank_score
            reranked.append(boosted)

        reranked.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        for item in reranked:
            item["final_score"] = item.get("rerank_score", item.get("final_score", 0.0))
        return reranked

    def _fuse_results(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]],
        vector_weight: float,
        keyword_weight: float,
        graph_weight: float,
        query: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        融合向量检索和图谱检索结果
        
        使用加权融合策略：
        - 向量检索提供语义相似的文档
        - 图谱检索提供结构化的实体关系知识
        
        Args:
            vector_results: 向量检索结果
            graph_results: 图谱检索结果
            vector_weight: 向量权重
            graph_weight: 图谱权重
            top_k: 最终返回数量
            
        Returns:
            融合后的结果列表
        """
        if getattr(self.config, 'enable_rrf_fusion', True):
            all_results = self._apply_rrf(
                {
                    'vector': vector_results,
                    'keyword': keyword_results,
                    'graph': graph_results
                },
                {
                    'vector': vector_weight,
                    'keyword': keyword_weight,
                    'graph': graph_weight
                }
            )
        else:
            all_results = []
            for result in vector_results:
                copied = dict(result)
                copied['final_score'] = copied.get('score', 0.0) * vector_weight
                copied['weight_type'] = 'vector'
                all_results.append(copied)
            for result in keyword_results:
                copied = dict(result)
                copied['final_score'] = copied.get('score', 0.0) * keyword_weight
                copied['weight_type'] = 'keyword'
                all_results.append(copied)
            for result in graph_results:
                copied = dict(result)
                copied['final_score'] = copied.get('score', 0.0) * graph_weight
                copied['weight_type'] = 'graph'
                all_results.append(copied)
            all_results.sort(key=lambda x: x.get('final_score', 0.0), reverse=True)

        if getattr(self.config, 'enable_light_rerank', True):
            all_results = self._light_rerank(query, all_results)

        top_results = all_results[:top_k]

        # 图结果保底（仅在有图结果时生效）
        graph_min_results = max(0, int(getattr(self.config, 'graph_min_results', 0) or 0))
        if graph_min_results > 0:
            current_graph_count = sum(
                1 for item in top_results
                if item.get('weight_type') == 'graph' or 'graph' in (item.get('channels') or [])
            )
            required_graph_count = min(graph_min_results, len(graph_results), top_k)

            if current_graph_count < required_graph_count:
                graph_candidates = [
                    item for item in all_results
                    if item.get('weight_type') == 'graph' or 'graph' in (item.get('channels') or [])
                ]
                for candidate in graph_candidates:
                    if current_graph_count >= required_graph_count:
                        break
                    if candidate in top_results:
                        continue

                    replace_index = None
                    for idx in range(len(top_results) - 1, -1, -1):
                        current = top_results[idx]
                        is_graph = current.get('weight_type') == 'graph' or 'graph' in (current.get('channels') or [])
                        if not is_graph:
                            replace_index = idx
                            break

                    if replace_index is None:
                        break

                    top_results[replace_index] = candidate
                    current_graph_count += 1

                top_results.sort(key=lambda x: x.get('final_score', x.get('score', 0)), reverse=True)
        
        # 添加排名信息
        for i, result in enumerate(top_results):
            result['rank'] = i + 1
        
        return top_results
    
    def _format_entity_info(self, entity_data: Dict[str, Any]) -> str:
        """
        格式化实体信息为文本
        
        Args:
            entity_data: 实体数据
            
        Returns:
            格式化的文本
        """
        parts = [f"实体: {entity_data['name']} (类型: {entity_data['type']})"]
        
        # 添加属性
        attrs = entity_data.get('attributes', {})
        if attrs:
            # 过滤掉系统字段
            user_attrs = {k: v for k, v in attrs.items() 
                         if k not in ['name', 'type', 'kb_id', 'updated_at']}
            if user_attrs:
                parts.append(f"属性: {user_attrs}")

        evidence_chunks = list(dict.fromkeys((attrs or {}).get('chunk_ids') or []))[:5]
        if evidence_chunks:
            parts.append(f"证据块: {', '.join(evidence_chunks)}")
        
        # 添加出边关系
        out_relations = entity_data.get('out_relations', [])
        if out_relations:
            relations = [f"{r['relation']}->{r['target']}" for r in out_relations[:3]]
            if relations:
                parts.append(f"关系: {', '.join(relations)}")
        
        # 添加入边关系
        in_relations = entity_data.get('in_relations', [])
        if in_relations:
            relations = [f"{r['source']}-{r['relation']}->此实体" for r in in_relations[:3]]
            if relations:
                parts.append(f"相关: {', '.join(relations)}")
        
        return "\n".join(parts)
    
    def _format_relation_info(self, source: str, relation_data: Dict[str, Any]) -> str:
        """
        格式化关系信息为文本
        
        Args:
            source: 源实体
            relation_data: 关系数据
            
        Returns:
            格式化的文本
        """
        entity = relation_data['entity']
        entity_type = relation_data['type']
        relations = relation_data.get('relations', [])
        hop = relation_data.get('hop', 1)
        evidence_chunks = relation_data.get('evidence_chunks', []) or []
        
        # 构建关系路径描述
        if relations:
            relation_path = ' -> '.join(relations)
            text = f"{source} 通过 [{relation_path}] 关联到 {entity} (类型: {entity_type}, {hop}跳)"
        else:
            text = f"{source} 关联到 {entity} (类型: {entity_type}, {hop}跳)"
        
        if evidence_chunks:
            text += f"\n证据块: {', '.join(evidence_chunks[:5])}"

        return text


# 工厂函数
def create_hybrid_retrieval_service() -> HybridRetrievalService:
    """创建混合检索服务实例"""
    return HybridRetrievalService()


# 全局单例
_hybrid_retrieval_service_instance = None


def get_hybrid_retrieval_service() -> HybridRetrievalService:
    """获取混合检索服务单例"""
    global _hybrid_retrieval_service_instance
    if _hybrid_retrieval_service_instance is None:
        _hybrid_retrieval_service_instance = HybridRetrievalService()
    return _hybrid_retrieval_service_instance
