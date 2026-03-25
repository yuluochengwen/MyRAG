"""知识库服务"""
import asyncio
import hashlib
import json
import math
import re
import time
import unicodedata
from typing import List, Optional, Dict, Any, Tuple, Callable
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from app.core.database import DatabaseManager
from app.models.knowledge_base import KnowledgeBase
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_cross_encoder_cache: Dict[str, Any] = {
    "name": None,
    "model": None
}


class KnowledgeBaseService:
    """知识库服务"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.retrieval_config = settings.vector_retrieval

    def _chunk_fingerprint(self, content: str) -> str:
        text = (content or "").strip()
        return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()

    def _append_graph_metrics(self, payload: Dict[str, Any]) -> None:
        metrics_path_raw = str(getattr(settings.knowledge_graph, "run_metrics_file", "") or "").strip()
        if not metrics_path_raw:
            return
        metrics_path = Path(metrics_path_raw)
        try:
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            with metrics_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as error:
            logger.warning("图谱构建指标写入失败: %s", str(error))
    
    async def create_knowledge_base(
        self,
        name: str,
        description: Optional[str] = None,
        embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2",
        embedding_provider: str = "transformers"
    ) -> Optional[KnowledgeBase]:
        """
        创建知识库
        
        Args:
            name: 知识库名称
            description: 描述
            embedding_model: 嵌入模型
            embedding_provider: 嵌入提供方
            
        Returns:
            创建的知识库对象
        """
        try:
            sql = """
                INSERT INTO knowledge_bases (name, description, embedding_model, embedding_provider, status)
                VALUES (%s, %s, %s, %s, %s)
            """
            
            kb_id = await self.db.execute_insert(
                sql,
                (name, description, embedding_model, embedding_provider, 'ready')
            )
            
            if kb_id:
                logger.info(f"知识库创建成功: id={kb_id}, name={name}, provider={embedding_provider}")
                return await self.get_knowledge_base(kb_id)
            
            return None
            
        except Exception as e:
            logger.error(f"创建知识库失败: {str(e)}")
            raise
    
    async def get_knowledge_base(self, kb_id: int) -> Optional[KnowledgeBase]:
        """
        获取知识库
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            知识库对象
        """
        try:
            sql = "SELECT * FROM knowledge_bases WHERE id = %s"
            result = await self.db.execute_query(sql, (kb_id,))
            
            if result:
                return KnowledgeBase.from_dict(result[0])
            
            return None
            
        except Exception as e:
            logger.error(f"获取知识库失败: {str(e)}")
            raise
    
    async def list_knowledge_bases(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[KnowledgeBase]:
        """
        获取知识库列表

        Args:
            skip: 跳过数量
            limit: 返回数量
            
        Returns:
            知识库列表
        """
        try:
            sql = """
                SELECT * FROM knowledge_bases
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            
            results = await self.db.execute_query(sql, (limit, skip))
            
            return [KnowledgeBase.from_dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"获取知识库列表失败: {str(e)}")
            raise
    
    async def update_knowledge_base(
        self,
        kb_id: int,
        **kwargs
    ) -> bool:
        """
        更新知识库
        
        Args:
            kb_id: 知识库ID
            **kwargs: 要更新的字段
            
        Returns:
            是否成功
        """
        try:
            if not kwargs:
                return True
            
            # 构建更新语句
            set_clause = ", ".join([f"{k} = %s" for k in kwargs.keys()])
            values = list(kwargs.values())
            values.append(kb_id)
            
            sql = f"""
                UPDATE knowledge_bases
                SET {set_clause}, updated_at = NOW()
                WHERE id = %s
            """
            
            rows_affected = await self.db.execute_update(sql, tuple(values))
            
            logger.info(f"知识库更新成功: id={kb_id}, fields={list(kwargs.keys())}")
            return rows_affected > 0
            
        except Exception as e:
            logger.error(f"更新知识库失败: {str(e)}")
            raise
    
    async def delete_knowledge_base(self, kb_id: int) -> bool:
        """
        删除知识库
        
        Args:
            kb_id: 知识库ID

        """
        try:
            # 删除关联的文件记录
            await self.db.execute_update(
                "DELETE FROM files WHERE kb_id = %s",
                (kb_id,)
            )
            
            # 删除关联的文本块
            await self.db.execute_update(
                "DELETE FROM text_chunks WHERE kb_id = %s",
                (kb_id,)
            )
            
            # 删除知识库
            rows_affected = await self.db.execute_update(
                "DELETE FROM knowledge_bases WHERE id = %s",
                (kb_id,)
            )
            
            logger.info(f"知识库删除成功: id={kb_id}")
            return rows_affected > 0
            
        except Exception as e:
            logger.error(f"删除知识库失败: {str(e)}")
            raise
    
    async def update_stats(self, kb_id: int) -> bool:
        """
        更新知识库统计信息
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            是否成功
        """
        try:
            # 统计文件数量和文本块总数
            stats_sql = """
                SELECT 
                    COUNT(*) as file_count,
                    COALESCE(SUM(chunk_count), 0) as chunk_count
                FROM files 
                WHERE kb_id = %s AND status = 'completed'
            """
            result = await self.db.execute_query(stats_sql, (kb_id,))
            
            file_count = result[0]['file_count'] if result else 0
            chunk_count = result[0]['chunk_count'] if result else 0
            
            # 更新统计
            await self.update_knowledge_base(
                kb_id,
                file_count=file_count,
                chunk_count=chunk_count
            )
            
            logger.info(f"知识库统计更新成功: kb_id={kb_id}, files={file_count}, chunks={chunk_count}")
            return True
            
        except Exception as e:
            logger.error(f"更新知识库统计失败: {str(e)}")
            raise
    
    async def get_kb_by_name(self, name: str) -> Optional[KnowledgeBase]:
        """
        根据名称获取知识库
        
        Args:
            name: 知识库名称
            
        Returns:
            知识库对象
        """
        try:
            sql = "SELECT * FROM knowledge_bases WHERE name = %s"
            result = await self.db.execute_query(sql, (name,))
            
            if result:
                return KnowledgeBase.from_dict(result[0])
            
            return None
            
        except Exception as e:
            logger.error(f"根据名称获取知识库失败: {str(e)}")
            raise

    # ==================== 传统向量检索优化方法 ====================

    def _tokenize_query(self, query: str) -> List[str]:
        stopwords = set(self.retrieval_config.query_stopwords or [])
        pieces = re.split(r"[\s,，。！？!?:：;；()（）\[\]{}<>《》、/\\\-|_]+", query or "")
        tokens: List[str] = []
        for piece in pieces:
            current = piece.strip().lower()
            if not current or current in stopwords:
                continue
            if len(current) == 1 and not ('\u4e00' <= current <= '\u9fff'):
                continue
            if current not in tokens:
                tokens.append(current)
        return tokens

    def _rewrite_query_variants(self, query: str) -> List[str]:
        query = (query or "").strip()
        if not query:
            return []

        variants = [query]
        if not self.retrieval_config.enable_query_rewrite:
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

            intent_query = f"{keyword_query} 定义 作用 场景"
            if len(tokens) >= 2 and intent_query not in variants:
                variants.append(intent_query)

        max_variants = max(1, int(self.retrieval_config.query_rewrite_max_variants or 1))
        return variants[:max_variants]

    def _compute_recall_k(self, top_k: int) -> int:
        target_top_k = max(1, int(top_k or 1))
        if not self.retrieval_config.enable_two_stage:
            return target_top_k

        recall = target_top_k * max(1, int(self.retrieval_config.recall_factor or 1))

        # 与切分粒度联动：块更小时扩大候选池，块更大时适度收敛
        base_chunk_size = max(200, int(getattr(settings.text_processing, 'chunk_size', 800) or 800))
        baseline = 800
        size_ratio = baseline / base_chunk_size
        size_ratio = max(0.85, min(1.6, size_ratio))
        recall = int(max(1, round(recall * size_ratio)))

        recall = max(recall, max(1, int(self.retrieval_config.min_recall_k or 1)))
        recall = min(recall, max(1, int(self.retrieval_config.max_recall_k or recall)))
        return recall

    def _result_key(self, item: Dict[str, Any]) -> str:
        chunk_id = item.get('chunk_id')
        if chunk_id:
            return str(chunk_id)
        metadata = item.get('metadata', {}) or {}
        file_id = metadata.get('file_id', 'unknown')
        chunk_index = metadata.get('chunk_index', 'unknown')
        return f"{file_id}:{chunk_index}:{hash(item.get('content', ''))}"

    def _fuse_multi_query_results(
        self,
        query_variants: List[str],
        variant_results: List[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        if not variant_results:
            return []

        if len(variant_results) == 1 or not self.retrieval_config.enable_multi_query_fusion:
            return variant_results[0]

        fusion_method = str(self.retrieval_config.fusion_method or 'rrf').lower()
        rrf_k = max(1, int(self.retrieval_config.rrf_k or 60))

        score_map: Dict[str, float] = {}
        payload_map: Dict[str, Dict[str, Any]] = {}

        for variant_index, results in enumerate(variant_results):
            current_query = query_variants[variant_index] if variant_index < len(query_variants) else ''
            for rank, item in enumerate(results, start=1):
                key = self._result_key(item)
                similarity = float(item.get('similarity', 0.0) or 0.0)

                if fusion_method == 'max':
                    score_map[key] = max(score_map.get(key, 0.0), similarity)
                else:
                    score_map[key] = score_map.get(key, 0.0) + (1.0 / (rrf_k + rank))

                if key not in payload_map:
                    payload_map[key] = dict(item)
                    payload_map[key]['_query_variants'] = [current_query] if current_query else []
                else:
                    payload_map[key]['similarity'] = max(
                        float(payload_map[key].get('similarity', 0.0) or 0.0),
                        similarity
                    )
                    if current_query and current_query not in payload_map[key].get('_query_variants', []):
                        payload_map[key].setdefault('_query_variants', []).append(current_query)

        fused = []
        for key, payload in payload_map.items():
            payload['_fusion_score'] = score_map.get(key, 0.0)
            fused.append(payload)

        if fusion_method == 'max':
            fused.sort(key=lambda x: x.get('similarity', 0.0), reverse=True)
        else:
            fused.sort(key=lambda x: x.get('_fusion_score', 0.0), reverse=True)
        return fused

    def _apply_score_threshold(
        self,
        results: List[Dict[str, Any]],
        score_threshold: float,
        top_k: int
    ) -> Tuple[List[Dict[str, Any]], float]:
        if not results:
            return [], 0.0

        explicit_threshold = float(score_threshold or 0.0)
        base_threshold = explicit_threshold if explicit_threshold > 0 else float(self.retrieval_config.base_score_threshold or 0.0)

        if not self.retrieval_config.enable_dynamic_threshold:
            filtered = [item for item in results if float(item.get('similarity', 0.0)) >= base_threshold]
            return filtered, base_threshold

        top1 = float(results[0].get('similarity', 0.0) or 0.0)
        relative_threshold = max(0.0, top1 - float(self.retrieval_config.relative_margin or 0.0))
        effective_threshold = max(base_threshold, relative_threshold)

        filtered = [item for item in results if float(item.get('similarity', 0.0) or 0.0) >= effective_threshold]

        min_keep = max(1, int(self.retrieval_config.min_keep_results or 1))
        if len(filtered) < min_keep:
            filtered = results[:min(min_keep, len(results), max(1, int(top_k or 1) * 3))]

        return filtered, effective_threshold

    def _light_rerank(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not results or not self.retrieval_config.enable_light_rerank:
            return results

        query_tokens = set(self._tokenize_query(query))
        if not query_tokens:
            return results

        alpha = float(self.retrieval_config.rerank_alpha or 0.75)
        alpha = max(0.0, min(1.0, alpha))

        reranked: List[Dict[str, Any]] = []
        for item in results:
            content = str(item.get('content', '') or '')
            content_tokens = set(self._tokenize_query(content[:1200]))
            overlap = 0.0 if not content_tokens else len(query_tokens & content_tokens) / max(1, len(query_tokens))

            metadata = item.get('metadata', {}) or {}
            filename = str(metadata.get('filename', '') or '').lower()
            filename_bonus = 0.0
            if filename and any(token in filename for token in query_tokens):
                filename_bonus = 0.1

            lexical_score = max(0.0, min(1.0, overlap + filename_bonus))
            semantic_score = float(item.get('similarity', 0.0) or 0.0)
            combined = alpha * semantic_score + (1 - alpha) * lexical_score

            updated = dict(item)
            updated['_rerank_score'] = combined
            reranked.append(updated)

        reranked.sort(key=lambda x: x.get('_rerank_score', x.get('similarity', 0.0)), reverse=True)
        return reranked

    def _vector_cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        if vec_a is None or vec_b is None:
            return 0.0
        if len(vec_a) == 0 or len(vec_b) == 0 or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        return max(-1.0, min(1.0, dot))

    def _has_embedding_vector(self, vector: Any) -> bool:
        if vector is None:
            return False
        try:
            return len(vector) > 0
        except Exception:
            return False

    def _apply_mmr(
        self,
        query_vector: Optional[List[float]],
        results: List[Dict[str, Any]],
        top_k: int
    ) -> List[Dict[str, Any]]:
        if (
            not self.retrieval_config.enable_mmr
            or query_vector is None
            or len(query_vector) == 0
            or len(results) <= 1
        ):
            return results

        with_embedding = [item for item in results if self._has_embedding_vector(item.get('_embedding'))]
        without_embedding = [item for item in results if not self._has_embedding_vector(item.get('_embedding'))]
        if len(with_embedding) <= 1:
            return results

        lambda_value = float(self.retrieval_config.mmr_lambda or 0.7)
        lambda_value = max(0.0, min(1.0, lambda_value))

        target_count = max(top_k, min(len(with_embedding), self._compute_recall_k(top_k)))
        selected: List[Dict[str, Any]] = []
        remaining = with_embedding.copy()

        while remaining and len(selected) < target_count:
            best_idx = 0
            best_score = -1e9
            for index, candidate in enumerate(remaining):
                relevance = float(candidate.get('similarity', 0.0) or 0.0)
                diversity_penalty = 0.0
                if selected:
                    candidate_embedding = candidate.get('_embedding') if self._has_embedding_vector(candidate.get('_embedding')) else []
                    diversity_penalty = max(
                        self._vector_cosine_similarity(
                            candidate_embedding,
                            chosen.get('_embedding') if self._has_embedding_vector(chosen.get('_embedding')) else []
                        )
                        for chosen in selected
                    )
                mmr_score = lambda_value * relevance - (1 - lambda_value) * diversity_penalty
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = index

            selected.append(remaining.pop(best_idx))

        selected.extend(remaining)
        selected.extend(without_embedding)
        return selected

    def _cluster_and_merge_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not results or not self.retrieval_config.enable_cluster_dedup:
            return results

        window = max(0, int(self.retrieval_config.cluster_adjacent_window or 0))
        max_chunks = max(1, int(self.retrieval_config.max_chunks_per_cluster or 1))
        max_clusters_per_file = max(1, int(self.retrieval_config.max_clusters_per_file or 1))

        grouped: Dict[Any, List[Dict[str, Any]]] = {}
        for item in results:
            metadata = item.get('metadata', {}) or {}
            file_id = metadata.get('file_id', '__unknown__')
            grouped.setdefault(file_id, []).append(item)

        merged_clusters: List[Dict[str, Any]] = []

        for file_id, file_results in grouped.items():
            ordered = sorted(file_results, key=lambda x: int((x.get('metadata', {}) or {}).get('chunk_index', 0)))
            clusters: List[List[Dict[str, Any]]] = []
            current_cluster: List[Dict[str, Any]] = []
            last_chunk_index: Optional[int] = None

            for item in ordered:
                chunk_index = int((item.get('metadata', {}) or {}).get('chunk_index', 0))
                if (
                    not current_cluster
                    or last_chunk_index is None
                    or (chunk_index - last_chunk_index) <= window
                ):
                    if len(current_cluster) < max_chunks:
                        current_cluster.append(item)
                    else:
                        clusters.append(current_cluster)
                        current_cluster = [item]
                else:
                    clusters.append(current_cluster)
                    current_cluster = [item]
                last_chunk_index = chunk_index

            if current_cluster:
                clusters.append(current_cluster)

            cluster_payloads: List[Dict[str, Any]] = []
            for cluster in clusters:
                ranked = sorted(cluster, key=lambda x: float(x.get('similarity', 0.0)), reverse=True)
                best = dict(ranked[0])
                merged_content = "\n".join(item.get('content', '') for item in cluster if item.get('content'))
                best['content'] = merged_content if merged_content else best.get('content', '')
                metadata = dict(best.get('metadata', {}) or {})
                metadata['evidence_chunks'] = [item.get('chunk_id') for item in cluster if item.get('chunk_id')]
                metadata['cluster_size'] = len(cluster)
                best['metadata'] = metadata
                best['_cluster_score'] = max(float(item.get('similarity', 0.0)) for item in cluster)
                cluster_payloads.append(best)

            cluster_payloads.sort(key=lambda x: x.get('_cluster_score', x.get('similarity', 0.0)), reverse=True)
            merged_clusters.extend(cluster_payloads[:max_clusters_per_file])

        merged_clusters.sort(key=lambda x: x.get('_cluster_score', x.get('_rerank_score', x.get('similarity', 0.0))), reverse=True)
        return merged_clusters

    def _get_cross_encoder(self):
        if not self.retrieval_config.enable_cross_encoder_rerank:
            return None

        model_name = str(self.retrieval_config.cross_encoder_model or '').strip()
        if not model_name:
            return None

        if _cross_encoder_cache.get('model') is not None and _cross_encoder_cache.get('name') == model_name:
            return _cross_encoder_cache.get('model')

        try:
            from sentence_transformers import CrossEncoder
            device = 'cpu'
            try:
                import torch
                if torch.cuda.is_available():
                    device = 'cuda'
            except Exception:
                device = 'cpu'

            model = CrossEncoder(model_name, device=device)
            _cross_encoder_cache['name'] = model_name
            _cross_encoder_cache['model'] = model
            logger.info(f"CrossEncoder加载成功: model={model_name}, device={device}")
            return model
        except Exception as error:
            logger.warning(f"CrossEncoder加载失败，跳过交叉重排: {str(error)}")
            return None

    def _cross_encoder_rerank(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not results or not self.retrieval_config.enable_cross_encoder_rerank:
            return results

        model = self._get_cross_encoder()
        if model is None or len(results) < 2:
            return results

        try:
            top_n = min(max(1, int(self.retrieval_config.cross_encoder_top_n or 1)), len(results))
            alpha = float(self.retrieval_config.cross_encoder_alpha or 0.7)
            alpha = max(0.0, min(1.0, alpha))

            target = results[:top_n]
            pairs = [[query, str(item.get('content', '') or '')[:1500]] for item in target]
            raw_scores = model.predict(pairs)

            rescored = []
            for item, score in zip(target, raw_scores):
                normalized_score = 1.0 / (1.0 + math.exp(-float(score)))
                base_score = float(item.get('_rerank_score', item.get('similarity', 0.0)) or 0.0)
                final_score = alpha * normalized_score + (1 - alpha) * base_score
                updated = dict(item)
                updated['_cross_score'] = normalized_score
                updated['_cross_final_score'] = final_score
                rescored.append(updated)

            rescored.sort(key=lambda x: x.get('_cross_final_score', 0.0), reverse=True)
            return rescored + results[top_n:]
        except Exception as error:
            logger.warning(f"CrossEncoder重排失败，回退轻量结果: {str(error)}")
            return results

    def _sanitize_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sanitized = []
        for item in results:
            copied = dict(item)
            for key in list(copied.keys()):
                if key.startswith('_'):
                    copied.pop(key, None)
            copied.pop('embedding', None)
            sanitized.append(copied)
        return sanitized

    def _record_retrieval_metrics(self, payload: Dict[str, Any]) -> None:
        if not self.retrieval_config.monitoring_enabled:
            return
        try:
            metrics_file = Path(self.retrieval_config.metrics_log_file)
            metrics_file.parent.mkdir(parents=True, exist_ok=True)

            line = json.dumps(payload, ensure_ascii=False)
            with metrics_file.open('a', encoding='utf-8') as file_obj:
                file_obj.write(line + "\n")
        except Exception as error:
            logger.warning(f"记录检索监控指标失败: {str(error)}")

    def _postprocess_retrieval_results(
        self,
        query: str,
        query_vector: Optional[List[float]],
        candidates: List[Dict[str, Any]],
        top_k: int,
        score_threshold: float
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        diagnostics: Dict[str, Any] = {
            'candidate_count': len(candidates)
        }
        if not candidates:
            diagnostics['effective_threshold'] = 0.0
            return [], diagnostics

        sorted_candidates = sorted(candidates, key=lambda x: float(x.get('similarity', 0.0)), reverse=True)
        filtered, effective_threshold = self._apply_score_threshold(sorted_candidates, score_threshold, top_k)
        diagnostics['effective_threshold'] = effective_threshold
        diagnostics['after_threshold'] = len(filtered)

        reranked = self._light_rerank(query, filtered)
        reranked = self._cross_encoder_rerank(query, reranked)
        reranked = self._apply_mmr(query_vector, reranked, top_k)
        reranked = self._cluster_and_merge_results(reranked)
        diagnostics['after_rerank'] = len(reranked)

        final_results = self._sanitize_results(reranked[:top_k])
        return final_results, diagnostics
    
    async def search_knowledge_bases(
        self,
        kb_ids: List[int],
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        多知识库联合检索
        
        前提: 所有知识库必须使用相同的embedding_model和provider
        
        Args:
            kb_ids: 知识库ID列表
            query: 查询文本
            top_k: 总共返回结果数量(从所有库中选top_k)
            score_threshold: 相似度阈值(0-1)
            
        Returns:
            合并后的检索结果列表(按相似度排序)
        """
        try:
            if not kb_ids:
                return []
            
            # 1. 检查所有知识库使用相同embedding配置
            embedding_configs = set()
            valid_kb_ids = []
            for kb_id in kb_ids:
                kb = await self.get_knowledge_base(kb_id)
                if not kb:
                    logger.warning(f"知识库不存在,跳过: {kb_id}")
                    continue
                embedding_configs.add((kb.embedding_provider, kb.embedding_model))
                valid_kb_ids.append(kb_id)
            
            if len(embedding_configs) > 1:
                raise ValueError(f"知识库使用了不同的嵌入配置: {embedding_configs}")
            
            if not valid_kb_ids:
                return []

            # 2. 并发检索所有知识库（每库先取候选，最后做全局重排）
            recall_k = self._compute_recall_k(top_k)
            per_kb_top_k = max(top_k, min(recall_k, max(top_k * 2, recall_k // max(1, len(valid_kb_ids)))))

            search_tasks = [
                self.search_knowledge_base(
                    kb_id=kb_id,
                    query=query,
                    top_k=per_kb_top_k,
                    score_threshold=score_threshold,
                    apply_postprocess=False
                )
                for kb_id in valid_kb_ids
            ]
            
            results_list = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # 3. 合并结果并过滤异常
            all_results = []
            for kb_id, results in zip(valid_kb_ids, results_list):
                if isinstance(results, Exception):
                    logger.error(f"检索知识库 {kb_id} 失败: {results}")
                    continue
                all_results.extend(results)

            if not all_results:
                return []

            # 4. 全局后处理（重排/去重/裁剪）
            first_provider, first_model = next(iter(embedding_configs))
            query_vector = None
            try:
                from app.services.embedding.embedding_service import get_embedding_service
                embedding_service = get_embedding_service()
                query_vector = embedding_service.encode_single(
                    query,
                    model_name=first_model,
                    provider=first_provider,
                    text_role='query'
                )
            except Exception as error:
                logger.warning(f"全局重排查询向量生成失败，继续使用无MMR路径: {str(error)}")

            final_results, diagnostics = self._postprocess_retrieval_results(
                query=query,
                query_vector=query_vector,
                candidates=all_results,
                top_k=top_k,
                score_threshold=score_threshold
            )

            self._record_retrieval_metrics({
                'timestamp': datetime.utcnow().isoformat(),
                'scope': 'multi_kb',
                'kb_ids': valid_kb_ids,
                'query': query,
                'top_k': top_k,
                'score_threshold': score_threshold,
                'candidate_count': len(all_results),
                'returned_count': len(final_results),
                **diagnostics
            })

            return final_results
            
        except Exception as e:
            logger.error(f"多知识库联合检索失败: {str(e)}")
            raise
    
    async def search_knowledge_base(
        self,
        kb_id: int,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0,
        apply_postprocess: bool = True
    ) -> List[Dict[str, Any]]:
        """
        检索知识库
        
        自动使用知识库对应的嵌入模型进行查询向量化
        
        Args:
            kb_id: 知识库ID
            query: 查询文本
            top_k: 返回结果数量
            score_threshold: 相似度阈值(0-1)
            
        Returns:
            检索结果列表
        """
        try:
            start_time = datetime.utcnow()

            # 1. 获取知识库信息（含嵌入模型）
            kb = await self.get_knowledge_base(kb_id)
            if not kb:
                raise ValueError(f"知识库不存在: {kb_id}")
            
            # 2. 使用知识库的嵌入模型编码查询
            from app.services.embedding.embedding_service import get_embedding_service
            from app.services.retrieval.vector_store_service import get_vector_store_service
            from app.utils.similarity import format_search_results

            embedding_service = get_embedding_service()
            vector_store = get_vector_store_service()

            query_variants = self._rewrite_query_variants(query)
            if not query_variants:
                return []

            recall_k = self._compute_recall_k(top_k)
            collection_name = f"kb_{kb_id}"

            logger.info(
                "向量检索开始: kb_id=%s, model=%s, provider=%s, variants=%s, recall_k=%s",
                kb_id,
                kb.embedding_model,
                kb.embedding_provider,
                len(query_variants),
                recall_k
            )

            variant_results: List[List[Dict[str, Any]]] = []
            file_ids = set()
            base_query_vector: Optional[List[float]] = None

            for index, variant_query in enumerate(query_variants):
                query_vector = embedding_service.encode_single(
                    variant_query,
                    model_name=kb.embedding_model,
                    provider=kb.embedding_provider,
                    text_role='query'
                )
                if index == 0:
                    base_query_vector = query_vector

                raw_results = vector_store.search(
                    collection_name=collection_name,
                    query_embeddings=[query_vector],
                    n_results=recall_k,
                    include=['documents', 'metadatas', 'distances', 'embeddings']
                )

                metadatas = raw_results.get('metadatas')
                if metadatas is None:
                    metadatas = []
                if metadatas and len(metadatas) > 0:
                    for metadata in metadatas[0]:
                        if metadata and 'file_id' in metadata:
                            try:
                                file_ids.add(int(metadata['file_id']))
                            except Exception:
                                continue

                variant_results.append(format_search_results(
                    results=raw_results,
                    file_info_map={},
                    kb_id=kb_id,
                    score_threshold=0.0
                ))

                embeddings = raw_results.get('embeddings')
                if embeddings is not None and len(embeddings) > 0:
                    for row_idx, vector in enumerate(embeddings[0]):
                        if row_idx < len(variant_results[-1]):
                            variant_results[-1][row_idx]['_embedding'] = vector

            # 查询文件名映射
            file_info_map = {}
            if file_ids:
                try:
                    placeholders = ','.join(['%s'] * len(file_ids))
                    file_query = f"SELECT id, filename FROM files WHERE id IN ({placeholders})"
                    file_rows = await self.db.execute_query(file_query, tuple(file_ids))
                    file_info_map = {row['id']: row['filename'] for row in file_rows}
                except Exception as error:
                    logger.warning(f"获取文件信息失败: {error}")

            # 回填文件名
            for result_set in variant_results:
                for item in result_set:
                    metadata = item.get('metadata', {}) or {}
                    file_id = metadata.get('file_id')
                    if file_id in file_info_map:
                        metadata['filename'] = file_info_map[file_id]

            fused_results = self._fuse_multi_query_results(query_variants, variant_results)
            fused_results.sort(
                key=lambda x: x.get('_fusion_score', x.get('similarity', 0.0)),
                reverse=True
            )

            if apply_postprocess:
                final_results, diagnostics = self._postprocess_retrieval_results(
                    query=query,
                    query_vector=base_query_vector,
                    candidates=fused_results,
                    top_k=top_k,
                    score_threshold=score_threshold
                )
            else:
                final_results = fused_results[:top_k]
                diagnostics = {
                    'candidate_count': len(fused_results),
                    'effective_threshold': score_threshold,
                    'after_threshold': len(final_results),
                    'after_rerank': len(final_results)
                }

            elapsed_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            self._record_retrieval_metrics({
                'timestamp': datetime.utcnow().isoformat(),
                'scope': 'single_kb',
                'kb_id': kb_id,
                'query': query,
                'query_variants': query_variants,
                'top_k': top_k,
                'recall_k': recall_k,
                'score_threshold': score_threshold,
                'candidate_count': len(fused_results),
                'returned_count': len(final_results),
                'elapsed_ms': elapsed_ms,
                **diagnostics
            })

            logger.info(
                "检索完成: kb_id=%s, query='%s', variants=%s, candidates=%s, returned=%s, model=%s, elapsed_ms=%s",
                kb_id,
                query,
                len(query_variants),
                len(fused_results),
                len(final_results),
                kb.embedding_model,
                elapsed_ms
            )

            return final_results
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"检索知识库失败: {str(e)}")
            raise
    
    # ==================== 知识图谱相关方法 ====================
    
    async def build_knowledge_graph(
        self,
        kb_id: int,
        chunks: List[Dict[str, Any]],
        force_rebuild: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        为知识库构建知识图谱
        
        Args:
            kb_id: 知识库ID
            chunks: 文本块列表 [{'id': '...', 'content': '...', 'metadata': {...}}, ...]
            force_rebuild: 是否强制重建（删除旧数据）
            progress_callback: 可选进度回调 async def cb(stage: str, pct: int, msg: str)
            
        Returns:
            构建统计信息
        """
        if not settings.knowledge_graph.enabled:
            logger.info("知识图谱功能未启用")
            return {'status': 'disabled'}
        
        try:
            from app.services.knowledge_graph.neo4j_graph_service import get_neo4j_graph_service
            from app.services.knowledge_graph.entity_extraction_service import get_entity_extraction_service
            
            graph_service = get_neo4j_graph_service()
            entity_service = get_entity_extraction_service()
            
            # 检查Neo4j服务
            if not graph_service.is_available():
                logger.warning("Neo4j服务不可用，跳过图谱构建")
                return {'status': 'neo4j_unavailable'}
            
            # 如果强制重建，先删除旧数据
            if force_rebuild:
                logger.info(f"强制重建图谱，删除旧数据: kb_id={kb_id}")
                graph_service.delete_kb_graph(kb_id)
            
            # 准备提取数据
            texts_with_ids = []
            raw_chunk_nodes: List[Dict[str, Any]] = []
            for i, chunk in enumerate(chunks):
                content = chunk.get('content')
                chunk_id = chunk.get('id', f"chunk_{i}")
                metadata = chunk.get('metadata', {}) or {}
                if not content:
                    continue
                fingerprint = self._chunk_fingerprint(content)
                preview = str(content).strip().replace("\n", " ")[:220]
                texts_with_ids.append((content, chunk_id, fingerprint, preview, metadata))
                raw_chunk_nodes.append({
                    'chunk_id': chunk_id,
                    'file_id': metadata.get('file_id'),
                    'chunk_index': metadata.get('chunk_index'),
                    'fingerprint': fingerprint,
                    'preview': preview,
                    'char_length': len(str(content))
                })
            
            if not texts_with_ids:
                logger.warning("没有可提取的文本块")
                return {'status': 'no_content'}
            
            logger.info(f"开始构建图谱: kb_id={kb_id}, chunks={len(texts_with_ids)}")
            run_id = f"kg_{uuid4().hex[:12]}"
            run_start = time.perf_counter()
            graph_service.start_graph_build_run(
                kb_id=kb_id,
                run_id=run_id,
                total_chunks=len(texts_with_ids),
                metadata={"force_rebuild": force_rebuild}
            )

            existing_fingerprints = {}
            if settings.knowledge_graph.idempotent_ingest_enabled and not force_rebuild:
                existing_fingerprints = graph_service.get_chunk_fingerprint_map(
                    kb_id,
                    [item[1] for item in texts_with_ids]
                )

            chunk_nodes: List[Dict[str, Any]] = []
            pending_texts: List[Tuple[str, str]] = []
            skipped_by_fingerprint = 0
            pending_lookup: Dict[str, Dict[str, Any]] = {}

            for content, chunk_id, fingerprint, preview, metadata in texts_with_ids:
                chunk_nodes.append({
                    'chunk_id': chunk_id,
                    'file_id': metadata.get('file_id'),
                    'chunk_index': metadata.get('chunk_index'),
                    'fingerprint': fingerprint,
                    'preview': preview,
                    'char_length': len(str(content))
                })

                old_fp = existing_fingerprints.get(str(chunk_id))
                if old_fp and old_fp == fingerprint:
                    skipped_by_fingerprint += 1
                    continue

                pending_texts.append((content, chunk_id))
                pending_lookup[str(chunk_id)] = {
                    "preview": preview,
                    "fingerprint": fingerprint
                }

            if chunk_nodes:
                graph_service.batch_import_chunks(kb_id=kb_id, chunks=chunk_nodes, run_id=run_id)

            if not pending_texts:
                elapsed_ms = int((time.perf_counter() - run_start) * 1000)
                result = {
                    'status': 'success',
                    'chunks_processed': 0,
                    'chunks_skipped': skipped_by_fingerprint,
                    'run_id': run_id,
                    'entity_count': 0,
                    'relation_count': 0,
                    'deleted_fact_count': 0,
                    'unknown_entity_count': 0,
                    'unknown_relation_count': 0,
                    'normalized_merge_count': 0,
                    'elapsed_ms': elapsed_ms
                }
                graph_service.finish_graph_build_run(kb_id, run_id, result)
                self._append_graph_metrics({"kb_id": kb_id, **result})
                return result
            
            # 批量提取实体和关系
            if progress_callback:
                await progress_callback("extracting_entities", 91, f"正在抽取实体关系 ({len(pending_texts)} 个文本块)...")
            extraction_results = await entity_service.batch_extract(
                texts=pending_texts,
                concurrency=settings.knowledge_graph.entity_extraction.batch_size
            )

            extraction_metrics = {
                'dropped_relation_endpoints': sum(int((item.get('metrics') or {}).get('dropped_relation_endpoints', 0)) for item in extraction_results),
                'raw_entity_count': sum(int((item.get('metrics') or {}).get('raw_entity_count', 0)) for item in extraction_results),
                'raw_relation_count': sum(int((item.get('metrics') or {}).get('raw_relation_count', 0)) for item in extraction_results),
                'cache_hit_count': sum(1 for item in extraction_results if bool((item.get('metrics') or {}).get('cache_hit'))),
                'failed_chunk_count': sum(1 for item in extraction_results if bool((item.get('metrics') or {}).get('failed'))),
                'parse_failed_chunk_count': sum(1 for item in extraction_results if bool((item.get('metrics') or {}).get('parse_failed'))),
                'llm_empty_chunk_count': sum(1 for item in extraction_results if bool((item.get('metrics') or {}).get('llm_empty')))
            }
            
            # 合并提取结果
            all_entities, all_relations = entity_service.merge_extraction_results(extraction_results)

            reclassify_stats = await entity_service.reclassify_unknowns(all_entities, all_relations)

            # 为关系补充证据预览，增强可解释性
            for relation in all_relations:
                chunk_ids = relation.get('chunk_ids', []) or []
                previews: List[str] = []
                for chunk_id in chunk_ids[:5]:
                    detail = pending_lookup.get(str(chunk_id))
                    if detail and detail.get('preview'):
                        previews.append(detail['preview'])
                if previews:
                    attrs = relation.get('attributes') if isinstance(relation.get('attributes'), dict) else {}
                    attrs['evidence_previews'] = previews
                    relation['attributes'] = attrs

            unknown_entity_type = settings.knowledge_graph.entity_extraction.unknown_entity_type
            unknown_relation_type = settings.knowledge_graph.entity_extraction.unknown_relation_type
            unknown_entity_count = sum(1 for entity in all_entities if entity.get('type') == unknown_entity_type)
            unknown_relation_count = sum(1 for relation in all_relations if relation.get('relation') == unknown_relation_type)
            normalized_merge_count = sum(
                max(0, int(entity.get('attributes', {}).get('mention_count', 1)) - 1)
                for entity in all_entities
            )
            
            if not all_entities:
                has_failed_chunks = int(extraction_metrics.get('failed_chunk_count', 0) or 0) > 0
                status = 'extraction_failed' if has_failed_chunks else 'no_entities'
                if has_failed_chunks:
                    logger.warning(
                        "实体抽取失败导致无实体: kb_id=%s, failed_chunks=%s, parse_failed_chunks=%s, processed_chunks=%s",
                        kb_id,
                        extraction_metrics.get('failed_chunk_count', 0),
                        extraction_metrics.get('parse_failed_chunk_count', 0),
                        len(pending_texts),
                    )
                else:
                    logger.warning("未提取到任何实体")
                result = {
                    'status': status,
                    'chunks_processed': len(pending_texts),
                    'chunks_skipped': skipped_by_fingerprint,
                    'run_id': run_id,
                    'extraction_metrics': extraction_metrics,
                    'reclassify_stats': reclassify_stats
                }
                graph_service.finish_graph_build_run(kb_id, run_id, result)
                self._append_graph_metrics({'kb_id': kb_id, **result})
                return result
            
            # 批量导入到Neo4j
            if progress_callback:
                await progress_callback("importing_graph", 95, f"正在导入图谱: {len(all_entities)} 个实体, {len(all_relations)} 个关系...")
            entity_count = graph_service.batch_import_entities(kb_id, all_entities, run_id=run_id)
            relation_count = graph_service.batch_import_relations(
                kb_id,
                all_relations,
                run_id=run_id,
                include_fact_nodes=settings.knowledge_graph.enable_fact_nodes
            )
            relation_import_stats = graph_service.get_last_relation_import_stats()

            deleted_fact_count = 0
            if (
                not settings.knowledge_graph.enable_fact_nodes
                and settings.knowledge_graph.cleanup_fact_nodes_on_build
            ):
                deleted_fact_count = graph_service.cleanup_fact_nodes(kb_id)

            elapsed_ms = int((time.perf_counter() - run_start) * 1000)
            avg_entity_confidence = round(
                sum(float(item.get('confidence', 0.0) or 0.0) for item in all_entities) / max(1, len(all_entities)),
                4
            )
            avg_relation_confidence = round(
                sum(float(item.get('confidence', 0.0) or 0.0) for item in all_relations) / max(1, len(all_relations)),
                4
            )
            entity_unknown_ratio = round(unknown_entity_count / max(1, len(all_entities)), 4)
            relation_unknown_ratio = round(unknown_relation_count / max(1, len(all_relations)), 4)
            relation_density = round(len(all_relations) / max(1, len(pending_texts)), 4)
            
            logger.info(f"图谱构建完成: kb_id={kb_id}, entities={entity_count}, relations={relation_count}")

            result = {
                'status': 'success',
                'chunks_processed': len(pending_texts),
                'chunks_skipped': skipped_by_fingerprint,
                'run_id': run_id,
                'entity_count': entity_count,
                'relation_count': relation_count,
                'deleted_fact_count': deleted_fact_count,
                'unknown_entity_count': unknown_entity_count,
                'unknown_relation_count': unknown_relation_count,
                'normalized_merge_count': normalized_merge_count,
                'relation_import_stats': relation_import_stats,
                'extraction_metrics': extraction_metrics,
                'reclassify_stats': reclassify_stats,
                'avg_entity_confidence': avg_entity_confidence,
                'avg_relation_confidence': avg_relation_confidence,
                'entity_unknown_ratio': entity_unknown_ratio,
                'relation_unknown_ratio': relation_unknown_ratio,
                'relation_density': relation_density,
                'elapsed_ms': elapsed_ms
            }

            graph_service.finish_graph_build_run(kb_id, run_id, result)
            self._append_graph_metrics({'kb_id': kb_id, **result})
            return result
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"构建知识图谱失败: {str(e)}")
            try:
                if 'graph_service' in locals() and 'run_id' in locals():
                    graph_service.fail_graph_build_run(kb_id, run_id, error_message)
                    if settings.knowledge_graph.rollback_on_failure:
                        rollback_stats = graph_service.rollback_run(kb_id, run_id)
                        self._append_graph_metrics({
                            'kb_id': kb_id,
                            'run_id': run_id,
                            'status': 'rollback_after_error',
                            'rollback_stats': rollback_stats,
                            'error': error_message
                        })
            except Exception as rollback_error:
                logger.warning("图构建失败后回滚异常: %s", str(rollback_error))
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def get_graph_stats(self, kb_id: int) -> Dict[str, Any]:
        """
        获取知识库的图谱统计信息
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            统计信息
        """
        try:
            if not settings.knowledge_graph.enabled:
                return {'enabled': False}
            
            from app.services.knowledge_graph.neo4j_graph_service import get_neo4j_graph_service
            graph_service = get_neo4j_graph_service()
            
            if not graph_service.is_available():
                return {'enabled': True, 'available': False}
            
            stats = graph_service.get_graph_stats(kb_id)
            stats['enabled'] = True
            stats['available'] = True
            
            return stats
            
        except Exception as e:
            logger.error(f"获取图谱统计失败: {str(e)}")
            return {
                'enabled': True,
                'available': False,
                'error': str(e)
            }

    async def get_graph_preview(
        self,
        kb_id: int,
        limit_nodes: int = 80,
        limit_edges: int = 160,
        include_all: bool = False
    ) -> Dict[str, Any]:
        """获取知识库图谱预览数据。"""
        try:
            if not settings.knowledge_graph.enabled:
                return {
                    'enabled': False,
                    'available': False,
                    'kb_id': kb_id,
                    'nodes': [],
                    'links': []
                }

            from app.services.knowledge_graph.neo4j_graph_service import get_neo4j_graph_service
            graph_service = get_neo4j_graph_service()

            if not graph_service.is_available():
                return {
                    'enabled': True,
                    'available': False,
                    'kb_id': kb_id,
                    'nodes': [],
                    'links': []
                }

            preview = graph_service.get_graph_preview(
                kb_id=kb_id,
                limit_nodes=limit_nodes,
                limit_edges=limit_edges,
                include_all=include_all
            )
            preview['enabled'] = True
            preview['available'] = True
            return preview

        except Exception as e:
            logger.error(f"获取图谱预览失败: {str(e)}")
            return {
                'enabled': True,
                'available': False,
                'kb_id': kb_id,
                'nodes': [],
                'links': [],
                'error': str(e)
            }
    
    async def delete_graph(self, kb_id: int) -> bool:
        """
        删除知识库的图谱数据
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            是否成功
        """
        try:
            if not settings.knowledge_graph.enabled:
                return True
            
            from app.services.knowledge_graph.neo4j_graph_service import get_neo4j_graph_service
            graph_service = get_neo4j_graph_service()
            
            deleted_count = graph_service.delete_kb_graph(kb_id)
            logger.info(f"删除图谱数据: kb_id={kb_id}, deleted={deleted_count}")
            
            return True
            
        except Exception as e:
            logger.error(f"删除图谱数据失败: {str(e)}")
            return False

    async def cleanup_graph_facts(self, kb_id: int) -> int:
        """清理知识库图谱中的Fact节点。"""
        try:
            if not settings.knowledge_graph.enabled:
                return 0

            from app.services.knowledge_graph.neo4j_graph_service import get_neo4j_graph_service
            graph_service = get_neo4j_graph_service()
            return graph_service.cleanup_fact_nodes(kb_id)
        except Exception as e:
            logger.error(f"清理Fact节点失败: {str(e)}")
            return 0

    async def delete_file_graph(self, kb_id: int, file_id: int) -> Dict[str, Any]:
        """按文件清理图谱证据和孤立节点。"""
        try:
            if not settings.knowledge_graph.enabled:
                return {
                    'enabled': False,
                    'available': False,
                    'counters': {}
                }

            from app.services.knowledge_graph.neo4j_graph_service import get_neo4j_graph_service
            graph_service = get_neo4j_graph_service()

            if not graph_service.is_available():
                return {
                    'enabled': True,
                    'available': False,
                    'counters': {}
                }

            counters = graph_service.delete_file_graph(kb_id=kb_id, file_id=file_id)
            return {
                'enabled': True,
                'available': True,
                'counters': counters
            }
        except Exception as e:
            logger.error(f"按文件清理图谱失败: {str(e)}")
            return {
                'enabled': True,
                'available': False,
                'error': str(e),
                'counters': {}
            }
