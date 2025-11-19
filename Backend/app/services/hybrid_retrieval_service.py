"""混合检索服务 - 结合向量检索和图谱检索"""
from typing import List, Dict, Any, Optional
from app.services.vector_store_service import VectorStoreService
from app.services.neo4j_graph_service import Neo4jGraphService
from app.services.entity_extraction_service import EntityExtractionService
from app.services.embedding_service import EmbeddingService
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class HybridRetrievalService:
    """混合检索服务 - 融合向量检索和知识图谱"""
    
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
        
        logger.info(f"混合检索服务初始化: vector_weight={self.config.vector_weight}, "
                   f"graph_weight={self.config.graph_weight}")
    
    async def hybrid_search(
        self,
        kb_id: int,
        query: str,
        top_k: int = 5,
        vector_weight: float = None,
        graph_weight: float = None,
        enable_graph: bool = True
    ) -> List[Dict[str, Any]]:
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
        vector_weight = vector_weight or self.config.vector_weight
        graph_weight = graph_weight or self.config.graph_weight
        
        logger.info(f"开始混合检索: kb_id={kb_id}, query={query[:50]}..., "
                   f"enable_graph={enable_graph}")
        
        # 1. 向量检索
        vector_results = await self._vector_search(kb_id, query, top_k * 2)
        
        # 2. 图谱检索（如果启用且服务可用）
        graph_results = []
        if enable_graph and settings.knowledge_graph.enabled:
            try:
                if self.graph_service.is_available():
                    graph_results = await self._graph_search(kb_id, query, top_k)
                else:
                    logger.warning("Neo4j服务不可用，跳过图谱检索")
            except Exception as e:
                logger.error(f"图谱检索失败: {str(e)}")
        
        # 3. 结果融合
        fused_results = self._fuse_results(
            vector_results,
            graph_results,
            vector_weight,
            graph_weight,
            top_k
        )
        
        logger.info(f"混合检索完成: vector={len(vector_results)}, "
                   f"graph={len(graph_results)}, fused={len(fused_results)}")
        
        return fused_results
    
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
                    # 计算相似度分数（距离越小越相似）
                    distance = search_results['distances'][0][i] if 'distances' in search_results else 0
                    similarity = 1 - distance  # 转换为相似度
                    
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
    
    async def _graph_search(
        self,
        kb_id: int,
        query: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
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
            # 1. 从查询中提取实体（查询通常较短，降低长度限制）
            logger.info(f"[图谱检索] 开始实体提取: query='{query}'")
            extraction_result = await self.entity_service.extract_from_text(
                query, 
                min_length_override=5  # 查询文本允许较短
            )
            entities = extraction_result.get('entities', [])
            
            if not entities:
                logger.warning(f"[图谱检索] 查询中未提取到实体: query='{query}'")
                return []
            
            entity_names = [e['name'] for e in entities]
            logger.info(f"[图谱检索] 提取到实体: {entity_names}")
            
            # 2. 对每个实体进行图遍历
            graph_results = []
            max_hops = settings.knowledge_graph.max_hops
            
            for entity_info in entities:
                entity = entity_info['name']
                logger.debug(f"[图谱检索] 查询实体: {entity}")
                
                # 获取实体详细信息
                entity_data = self.graph_service.get_entity_info(kb_id, entity)
                if entity_data:
                    logger.info(f"[图谱检索] 直接命中实体: {entity}, type={entity_data.get('type')}")
                    # 直接命中实体
                    content = self._format_entity_info(entity_data)
                    graph_results.append({
                        'content': content,
                        'score': 0.9,  # 直接命中实体，高分
                        'metadata': {
                            'entity': entity,
                            'type': entity_data.get('type', 'Unknown'),
                            'source_type': 'direct_match'
                        },
                        'source': 'graph_direct',
                        'entity': entity
                    })
                else:
                    logger.warning(f"[图谱检索] 未找到实体: {entity} in kb_{kb_id}")
                
                # 查找相关实体
                related = self.graph_service.find_related_entities(
                    kb_id=kb_id,
                    entity=entity,
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
                            'target_entity': rel['entity'],
                            'relations': rel['relations'],
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
                # 使用内容前100字符作为去重键
                key = result['content'][:100]
                if key not in seen:
                    seen.add(key)
                    unique_results.append(result)
                    if len(unique_results) >= top_k:
                        break
            
            logger.debug(f"图谱检索完成: found={len(unique_results)}")
            return unique_results
            
        except Exception as e:
            logger.error(f"图谱检索失败: {str(e)}")
            return []
    
    def _fuse_results(
        self,
        vector_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]],
        vector_weight: float,
        graph_weight: float,
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
        all_results = []
        
        # 标准化向量检索结果的分数
        for result in vector_results:
            result['final_score'] = result['score'] * vector_weight
            result['weight_type'] = 'vector'
            all_results.append(result)
        
        # 标准化图谱检索结果的分数
        for result in graph_results:
            result['final_score'] = result['score'] * graph_weight
            result['weight_type'] = 'graph'
            all_results.append(result)
        
        # 按最终分数排序
        all_results.sort(key=lambda x: x['final_score'], reverse=True)
        
        # 返回Top-K
        top_results = all_results[:top_k]
        
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
        
        # 构建关系路径描述
        if relations:
            relation_path = ' -> '.join(relations)
            text = f"{source} 通过 [{relation_path}] 关联到 {entity} (类型: {entity_type}, {hop}跳)"
        else:
            text = f"{source} 关联到 {entity} (类型: {entity_type}, {hop}跳)"
        
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
