"""混合检索服务 - 结合向量、关键词和图谱检索"""
import hashlib
import json
from datetime import datetime
from pathlib import Path
import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from app.services.retrieval.vector_store_service import VectorStoreService
from app.services.knowledge_graph.neo4j_graph_service import Neo4jGraphService
from app.services.knowledge_graph.entity_extraction_service import EntityExtractionService
from app.services.embedding.embedding_service import EmbeddingService
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
        from app.services.retrieval.vector_store_service import get_vector_store_service
        from app.services.knowledge_graph.neo4j_graph_service import get_neo4j_graph_service
        from app.services.knowledge_graph.entity_extraction_service import get_entity_extraction_service
        from app.services.embedding.embedding_service import get_embedding_service
        
        self.vector_store = vector_store or get_vector_store_service()
        self.graph_service = graph_service or get_neo4j_graph_service()
        self.entity_service = entity_service or get_entity_extraction_service()
        self.embedding_service = embedding_service or get_embedding_service()
        
        from app.services.knowledge_base.knowledge_base_service import KnowledgeBaseService
        self._kb_service = KnowledgeBaseService(db_manager)
        
        self.config = settings.hybrid_retrieval
        
        logger.info(
            "混合检索服务初始化: vector_weight=%s, keyword_weight=%s, graph_weight=%s",
            self.config.vector_weight,
            getattr(self.config, 'keyword_weight', 0.5),
            self.config.graph_weight
        )

    def _record_hybrid_metrics(self, payload: Dict[str, Any]) -> None:
        if not getattr(self.config, "monitoring_enabled", True):
            return
        metrics_file_raw = str(getattr(self.config, "hybrid_metrics_log_file", "") or "").strip()
        if not metrics_file_raw:
            return
        try:
            metrics_file = Path(metrics_file_raw)
            metrics_file.parent.mkdir(parents=True, exist_ok=True)
            with metrics_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as error:
            logger.warning("记录混合检索指标失败: %s", str(error))

    def _is_question_complex(self, query: str) -> bool:
        text = (query or "").strip()
        tokens = self._tokenize_query(text)
        markers = ["以及", "并且", "区别", "对比", "流程", "步骤", "如何", "为什么"]
        marker_hit = sum(1 for marker in markers if marker in text)
        return len(tokens) >= 6 or marker_hit >= 2

    def _compute_recall_k(self, query: str, top_k: int) -> int:
        base_k = max(top_k * 4, int(getattr(self.config, "rrf_window_size", 50) or 50))
        if not getattr(self.config, "adaptive_recall_enabled", True):
            return base_k

        min_factor = float(getattr(self.config, "adaptive_recall_min_factor", 1.0) or 1.0)
        max_factor = float(getattr(self.config, "adaptive_recall_max_factor", 1.8) or 1.8)
        complexity_factor = 1.0

        token_count = len(self._tokenize_query(query))
        if token_count >= 10:
            complexity_factor += 0.5
        elif token_count >= 6:
            complexity_factor += 0.25

        if self._is_question_complex(query):
            complexity_factor += 0.2

        complexity_factor = max(min_factor, min(max_factor, complexity_factor))
        return max(1, int(base_k * complexity_factor))

    def _build_query_variants(self, query: str) -> List[str]:
        query = (query or "").strip()
        if not query:
            return []

        variants = [query]
        if not getattr(self.config, "enable_vector_query_rewrite", True):
            return variants

        normalized = unicodedata.normalize("NFKC", query)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized and normalized not in variants:
            variants.append(normalized)

        tokens = self._tokenize_query(query)
        if tokens:
            keyword_query = " ".join(tokens)
            if keyword_query and keyword_query not in variants:
                variants.append(keyword_query)

        max_variants = max(1, int(getattr(self.config, "vector_query_max_variants", 3) or 3))
        return variants[:max_variants]

    def _fuse_vector_variant_results(self, variant_results: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        if not variant_results:
            return []
        if len(variant_results) == 1:
            return variant_results[0]

        method = str(getattr(self.config, "vector_fusion_method", "rrf") or "rrf").lower()
        rrf_k = max(1, int(getattr(self.config, "rrf_k", 60) or 60))
        score_map: Dict[str, float] = {}
        payload_map: Dict[str, Dict[str, Any]] = {}

        for results in variant_results:
            ranked = sorted(results, key=lambda x: float(x.get("score", 0.0) or 0.0), reverse=True)
            for rank, item in enumerate(ranked, start=1):
                key = self._make_result_key(item)
                score = float(item.get("score", 0.0) or 0.0)
                if method == "max":
                    score_map[key] = max(score_map.get(key, 0.0), score)
                else:
                    score_map[key] = score_map.get(key, 0.0) + 1.0 / (rrf_k + rank)

                if key not in payload_map:
                    payload_map[key] = dict(item)
                elif score > float(payload_map[key].get("score", 0.0) or 0.0):
                    payload_map[key] = dict(item)

        fused: List[Dict[str, Any]] = []
        for key, payload in payload_map.items():
            copied = dict(payload)
            copied["score"] = float(score_map.get(key, copied.get("score", 0.0) or 0.0))
            fused.append(copied)

        fused.sort(key=lambda x: float(x.get("score", 0.0) or 0.0), reverse=True)
        return fused

    def _normalized_fusion_score(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not results or not getattr(self.config, "normalize_fusion_scores", True):
            return results

        values = [float(item.get("final_score", 0.0) or 0.0) for item in results]
        min_value = min(values)
        max_value = max(values)
        if max_value <= min_value:
            for item in results:
                item["normalized_final_score"] = 1.0
            return results

        scale = max_value - min_value
        for item in results:
            val = float(item.get("final_score", 0.0) or 0.0)
            item["normalized_final_score"] = (val - min_value) / scale
        return results

    def _score_graph_candidate(self, hop: int, confidence: float, evidence_count: int, mention_count: int, is_direct: bool) -> float:
        direct_base = float(getattr(self.config, "graph_direct_base_score", 0.82) or 0.82)
        hop_base = float(getattr(self.config, "graph_hop_base_score", 0.62) or 0.62)
        confidence_weight = float(getattr(self.config, "graph_confidence_weight", 0.22) or 0.22)
        evidence_weight = float(getattr(self.config, "graph_evidence_weight", 0.16) or 0.16)
        mention_weight = float(getattr(self.config, "graph_mention_weight", 0.08) or 0.08)
        hop_decay = float(getattr(self.config, "graph_hop_decay", 0.25) or 0.25)

        base = direct_base if is_direct else max(0.0, hop_base - max(0, hop - 1) * hop_decay)
        evidence_factor = min(1.0, evidence_count / 5.0)
        mention_factor = min(1.0, mention_count / 8.0)
        score = base + confidence_weight * max(0.0, min(1.0, confidence)) + evidence_weight * evidence_factor + mention_weight * mention_factor
        return max(0.0, min(1.0, score))
    
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
        
        import asyncio as _asyncio

        logger.info(f"开始混合检索: kb_id={kb_id}, query={query[:50]}..., "
                   f"enable_graph={enable_graph}")
        
        # 三路并行召回：向量 + 关键词 + 图谱同时发起，大幅减少总延迟
        recall_k = self._compute_recall_k(query=query, top_k=top_k)

        tasks: Dict[str, _asyncio.Task] = {}
        tasks['vector'] = _asyncio.create_task(self._vector_search(kb_id, query, recall_k))
        if getattr(self.config, 'enable_keyword_search', True):
            tasks['keyword'] = _asyncio.create_task(self._keyword_search(kb_id, query, recall_k))
        if enable_graph and settings.knowledge_graph.enabled:
            try:
                if self.graph_service.is_available():
                    tasks['graph'] = _asyncio.create_task(self._graph_search(kb_id, query, recall_k))
            except Exception:
                pass

        await _asyncio.gather(*tasks.values(), return_exceptions=True)

        vector_results = []
        vector_task = tasks.get('vector')
        if vector_task and not vector_task.cancelled():
            result = vector_task.result() if not isinstance(vector_task.result(), Exception) else []
            vector_results = result if isinstance(result, list) else []

        keyword_results: List[Dict[str, Any]] = []
        keyword_task = tasks.get('keyword')
        if keyword_task and not keyword_task.cancelled():
            result = keyword_task.result() if not isinstance(keyword_task.result(), Exception) else []
            keyword_results = result if isinstance(result, list) else []

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
        graph_task = tasks.get('graph')
        if graph_task and not graph_task.cancelled():
            result = graph_task.result() if not isinstance(graph_task.result(), Exception) else ([], graph_diagnostics)
            if isinstance(result, tuple) and len(result) == 2:
                graph_results, graph_diagnostics = result
            elif isinstance(result, Exception):
                logger.error(f"图谱检索失败: {str(result)}")
        
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

        self._record_hybrid_metrics({
            "timestamp": datetime.utcnow().isoformat(),
            "kb_id": kb_id,
            "query": query,
            "top_k": top_k,
            "recall_k": recall_k,
            "vector_result_count": len(vector_results),
            "keyword_result_count": len(keyword_results),
            "graph_result_count": len(graph_results),
            "fused_result_count": len(fused_results),
            "graph_matched_entities": len(graph_diagnostics.get("matched_entities", [])),
            "graph_unmatched_entities": len(graph_diagnostics.get("unmatched_entities", [])),
            "fallback_used": graph_diagnostics.get("fallback_used", False)
        })
        
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

    def _extract_code_like_entities_from_query(self, query: str) -> List[str]:
        """从原始查询中补充代码型实体候选（如 N-47、P-1127）。"""
        text = str(query or "")
        if not text.strip():
            return []

        patterns = [
            # 字母前缀+数字，允许中间分隔符：N-47, P_1127, AB/2024
            r"\b[a-zA-Z]{1,4}\s*[-_/]?\s*\d{2,10}[a-zA-Z]{0,2}\b",
            # 数字后缀+字母：1127A
            r"\b\d{2,10}[a-zA-Z]{1,4}\b"
        ]

        found: List[str] = []
        for pattern in patterns:
            for match in re.findall(pattern, text):
                candidate = str(match or "").strip()
                if candidate and candidate not in found:
                    found.append(candidate)
        return found

    def _resolve_query_extraction_min_length(self, query: str) -> int:
        """为短码查询动态降低实体抽取长度门槛，避免 N-47 这类被提前过滤。"""
        query_text = str(query or "").strip()
        if not query_text:
            return 5

        code_like = bool(re.search(r"\b[a-zA-Z]{1,4}\s*[-_/]?\s*\d{2,10}[a-zA-Z]{0,2}\b", query_text))
        if code_like:
            return 2

        if len(query_text) <= 8:
            return 3

        return 5
    
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
            kb = await self._kb_service.get_knowledge_base(kb_id)
            if not kb:
                logger.error(f"知识库不存在: {kb_id}")
                return []
            
            query_variants = self._build_query_variants(query)
            if not query_variants:
                return []

            collection_name = f"kb_{kb_id}"
            variant_results: List[List[Dict[str, Any]]] = []

            for variant_query in query_variants:
                query_embedding = self.embedding_service.encode_single(
                    variant_query,
                    model_name=kb.embedding_model,
                    provider=kb.embedding_provider,
                    text_role='query'
                )

                search_results = self.vector_store.search(
                    collection_name=collection_name,
                    query_embeddings=[query_embedding],
                    n_results=top_k
                )

                results: List[Dict[str, Any]] = []
                if search_results and 'documents' in search_results and len(search_results['documents']) > 0:
                    for i in range(len(search_results['documents'][0])):
                        distance = search_results['distances'][0][i] if 'distances' in search_results else 0
                        similarity = normalize_l2_distance_to_similarity(distance)

                        metadata = search_results['metadatas'][0][i] if 'metadatas' in search_results else {}
                        metadata = dict(metadata or {})
                        metadata['kb_id'] = kb_id

                        results.append({
                            'content': search_results['documents'][0][i],
                            'score': max(0.0, float(similarity)),
                            'metadata': metadata,
                            'source': 'vector',
                            'chunk_id': search_results['ids'][0][i] if 'ids' in search_results else None
                        })
                variant_results.append(results)

            fused_results = self._fuse_vector_variant_results(variant_results)
            logger.debug("向量检索完成: variants=%s, found=%s", len(query_variants), len(fused_results))
            return fused_results[:top_k]
            
        except Exception as e:
            logger.error(f"向量检索失败: {str(e)}")
            return []

    async def _keyword_search(self, kb_id: int, query: str, top_k: int) -> List[Dict[str, Any]]:
        """关键词召回（轻量实现，基于text_chunks内容匹配）。"""
        try:
            tokens = self._tokenize_query(query)
            if not tokens:
                return []

            rows: List[Dict[str, Any]] = []
            candidate_limit = max(
                int(getattr(self.config, "keyword_min_candidates", 60) or 60),
                top_k * max(2, int(getattr(self.config, "keyword_candidate_factor", 8) or 8))
            )

            if getattr(self.config, "keyword_use_fulltext_first", True):
                try:
                    fulltext_query = " ".join(tokens)
                    sql_fulltext = """
                    SELECT tc.vector_id as chunk_id,
                           tc.content as content,
                           tc.file_id as file_id,
                           tc.chunk_index as chunk_index,
                           MATCH(tc.content) AGAINST (%s IN NATURAL LANGUAGE MODE) as ft_score
                    FROM text_chunks tc
                    WHERE tc.kb_id = %s AND MATCH(tc.content) AGAINST (%s IN NATURAL LANGUAGE MODE)
                    ORDER BY ft_score DESC
                    LIMIT %s
                    """
                    rows = await db_manager.execute_query(sql_fulltext, (fulltext_query, kb_id, fulltext_query, candidate_limit))
                except Exception as error:
                    logger.debug("关键词 fulltext 查询不可用，回退 LIKE: %s", str(error))

            if not rows:
                like_clauses = " OR ".join(["tc.content LIKE %s" for _ in tokens])
                params: List[Any] = [kb_id]
                params.extend([f"%{token}%" for token in tokens])
                params.append(candidate_limit)

                sql = f"""
                SELECT tc.vector_id as chunk_id,
                       tc.content as content,
                       tc.file_id as file_id,
                       tc.chunk_index as chunk_index
                FROM text_chunks tc
                WHERE tc.kb_id = %s AND ({like_clauses})
                LIMIT %s
                """
                rows = await db_manager.execute_query(sql, tuple(params))

            if not rows:
                return []

            scored: List[Dict[str, Any]] = []
            max_score = 0.0
            score_power = max(0.5, float(getattr(self.config, "keyword_score_power", 1.0) or 1.0))
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
                ft_score = float(row.get("ft_score", 0.0) or 0.0)
                if ft_score > 0:
                    score = score * 0.75 + min(1.0, ft_score / (ft_score + 5.0)) * 0.25
                score = max(0.0, min(1.0, score)) ** score_power
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
            extraction_min_length = self._resolve_query_extraction_min_length(query)
            extraction_result = await self.entity_service.extract_from_text(
                query,
                min_length_override=extraction_min_length
            )
            entities = extraction_result.get('entities', [])

            # 若LLM未抽到实体，尝试从原查询补充代码型实体（如 N-47 / P-1127）。
            code_like_entities = self._extract_code_like_entities_from_query(query)
            existing_entity_names = {
                str(item.get('name', '')).strip()
                for item in entities
                if isinstance(item, dict)
            }
            for item in code_like_entities:
                if item not in existing_entity_names:
                    entities.append({'name': item})
            
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
                    stage_weights = getattr(self.config, 'graph_match_stage_weights', {}) or {}
                    default_stage_weight = float(stage_weights.get('normalized', 0.95) or 0.95)
                    stage_weight = float(stage_weights.get(match_stage, default_stage_weight) or default_stage_weight)
                    stage_weight = max(0.0, min(1.0, stage_weight))
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
                    base_direct_score = self._score_graph_candidate(
                        hop=1,
                        confidence=float((entity_data.get('attributes') or {}).get('confidence', 0.7) or 0.7),
                        evidence_count=len(evidence_chunks),
                        mention_count=int((entity_data.get('attributes') or {}).get('mention_count', 1) or 1),
                        is_direct=True
                    )
                    graph_results.append({
                        'content': content,
                        'score': max(0.0, min(1.0, base_direct_score * stage_weight)),
                        'metadata': {
                            'kb_id': kb_id,
                            'entity': matched_entity,
                            'type': entity_data.get('type', 'Unknown'),
                            'labels': entity_data.get('labels', []),
                            'canonical_name': entity_data.get('canonical_name'),
                            'entity_attributes': entity_data.get('attributes') or {},
                            'query_entity': entity,
                            'match_stage': match_stage,
                            'match_stage_weight': stage_weight,
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
                    continue
                
                # 查找相关实体
                traversal_anchor = entity_data.get('name')
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
                    evidence = rel.get('evidence_chunks', []) or []
                    score = self._score_graph_candidate(
                        hop=max(1, int(rel.get('hop', 1) or 1)),
                        confidence=0.65,
                        evidence_count=len(evidence),
                        mention_count=1,
                        is_direct=False
                    )
                    
                    graph_results.append({
                        'content': content,
                        'score': score,
                        'metadata': {
                            'kb_id': kb_id,
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
            hop = metadata.get('hop', 1)
            evidence_key = hashlib.md5(
                "|".join(sorted([str(item) for item in metadata.get('evidence_chunks', [])[:5]])).encode("utf-8")
            ).hexdigest()[:8]
            return (
                f"path::{metadata.get('source_entity_matched')}::{metadata.get('target_entity')}::"
                f"{','.join(metadata.get('relations', []))}::hop{hop}::ev{evidence_key}"
            )

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

        results = self._normalized_fusion_score(results)

        reranked: List[Dict[str, Any]] = []
        for item in results:
            content_tokens = set(self._tokenize_query(item.get("content", "")))
            overlap = 0.0 if not content_tokens else len(query_tokens & content_tokens) / len(query_tokens)

            fusion_score = float(item.get("normalized_final_score", item.get("final_score", 0.0)) or 0.0)
            metadata = item.get("metadata", {}) or {}
            channels = item.get("channels") or []
            is_graph = item.get("weight_type") == "graph" or "graph" in channels or str(item.get("source", "")).startswith("graph_")
            is_graph_direct = str(item.get("source", "")) == "graph_direct"
            match_stage = str(metadata.get("match_stage", "") or "").lower()

            channel_bonus = 0.0
            if is_graph:
                channel_bonus += 0.08
            if is_graph_direct:
                channel_bonus += 0.12
            if match_stage == "exact":
                channel_bonus += 0.08

            rerank_score = alpha * fusion_score + (1 - alpha) * overlap + channel_bonus

            # 对词面重合度极低且非图谱证据的结果做轻惩罚，减少“高分但不相关”片段置顶
            if not is_graph and overlap < 0.05:
                rerank_score *= 0.68

            rerank_score = max(0.0, min(1.0, rerank_score))
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
                    if (
                        item.get('weight_type') == 'graph' or 'graph' in (item.get('channels') or [])
                    ) and float(item.get('final_score', item.get('score', 0.0)) or 0.0) >= float(getattr(self.config, 'graph_min_quality_score', 0.12) or 0.12)
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
