"""知识库服务"""
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.core.database import DatabaseManager
from app.models.knowledge_base import KnowledgeBase
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class KnowledgeBaseService:
    """知识库服务"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
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
            
        Returns:
            是否成功
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
            
            # 2. 并发检索所有知识库（每个库取 top_k*2 以确保合并后有足够结果）
            import asyncio
            per_kb_top_k = max(top_k, len(valid_kb_ids) * 2)  # 每个库多取一些
            
            search_tasks = [
                self.search_knowledge_base(
                    kb_id=kb_id,
                    query=query,
                    top_k=per_kb_top_k,
                    score_threshold=score_threshold
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
            
            # 4. 按相似度排序并返回top_k
            all_results.sort(key=lambda x: x['similarity'], reverse=True)
            return all_results[:top_k]
            
        except Exception as e:
            logger.error(f"多知识库联合检索失败: {str(e)}")
            raise
    
    async def search_knowledge_base(
        self,
        kb_id: int,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0
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
            # 1. 获取知识库信息（含嵌入模型）
            kb = await self.get_knowledge_base(kb_id)
            if not kb:
                raise ValueError(f"知识库不存在: {kb_id}")
            
            # 2. 使用知识库的嵌入模型编码查询
            from app.services.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            
            logger.info(f"使用嵌入模型 {kb.embedding_model} (provider={kb.embedding_provider}) 编码查询")
            query_vector = embedding_service.encode_single(
                query, 
                model_name=kb.embedding_model,
                provider=kb.embedding_provider
            )
            
            # 3. 向量检索
            from app.services.vector_store_service import get_vector_store_service
            vector_store = get_vector_store_service()
            collection_name = f"kb_{kb_id}"
            
            results = vector_store.search(
                collection_name=collection_name,
                query_embeddings=[query_vector],
                n_results=top_k
            )
            
            # 4. 格式化返回结果并获取文件信息
            # 批量获取所有涉及的文件信息
            file_ids = set()
            if results.get('metadatas') and len(results['metadatas']) > 0:
                for metadata in results['metadatas'][0]:
                    if metadata and 'file_id' in metadata:
                        file_ids.add(int(metadata['file_id']))
            
            # 查询文件名映射
            file_info_map = {}
            if file_ids:
                try:
                    placeholders = ','.join(['%s'] * len(file_ids))
                    file_query = f"SELECT id, filename FROM files WHERE id IN ({placeholders})"
                    file_rows = await self.db.execute_query(file_query, tuple(file_ids))
                    file_info_map = {row['id']: row['filename'] for row in file_rows}
                except Exception as e:
                    logger.warning(f"获取文件信息失败: {e}")
            
            # 使用公共函数格式化结果
            from app.utils.similarity import format_search_results
            formatted_results = format_search_results(
                results=results,
                file_info_map=file_info_map,
                kb_id=kb_id,
                score_threshold=score_threshold
            )
            
            logger.info(f"检索完成: kb_id={kb_id}, 查询='{query}', "
                       f"结果数={len(formatted_results)}, 模型={kb.embedding_model}")
            
            return formatted_results
            
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
        force_rebuild: bool = False
    ) -> Dict[str, Any]:
        """
        为知识库构建知识图谱
        
        Args:
            kb_id: 知识库ID
            chunks: 文本块列表 [{'id': '...', 'content': '...', 'metadata': {...}}, ...]
            force_rebuild: 是否强制重建（删除旧数据）
            
        Returns:
            构建统计信息
        """
        if not settings.knowledge_graph.enabled:
            logger.info("知识图谱功能未启用")
            return {'status': 'disabled'}
        
        try:
            from app.services.neo4j_graph_service import get_neo4j_graph_service
            from app.services.entity_extraction_service import get_entity_extraction_service
            
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
            texts_with_ids = [
                (chunk['content'], chunk.get('id', f"chunk_{i}")) 
                for i, chunk in enumerate(chunks)
                if chunk.get('content')
            ]
            
            if not texts_with_ids:
                logger.warning("没有可提取的文本块")
                return {'status': 'no_content'}
            
            logger.info(f"开始构建图谱: kb_id={kb_id}, chunks={len(texts_with_ids)}")
            
            # 批量提取实体和关系
            extraction_results = await entity_service.batch_extract(
                texts=texts_with_ids,
                concurrency=settings.knowledge_graph.entity_extraction.batch_size
            )
            
            # 合并提取结果
            all_entities, all_relations = entity_service.merge_extraction_results(extraction_results)
            
            if not all_entities:
                logger.warning("未提取到任何实体")
                return {
                    'status': 'no_entities',
                    'chunks_processed': len(texts_with_ids)
                }
            
            # 批量导入到Neo4j
            entity_count = graph_service.batch_import_entities(kb_id, all_entities)
            relation_count = graph_service.batch_import_relations(kb_id, all_relations)
            
            logger.info(f"图谱构建完成: kb_id={kb_id}, entities={entity_count}, relations={relation_count}")
            
            return {
                'status': 'success',
                'chunks_processed': len(texts_with_ids),
                'entity_count': entity_count,
                'relation_count': relation_count
            }
            
        except Exception as e:
            logger.error(f"构建知识图谱失败: {str(e)}")
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
            
            from app.services.neo4j_graph_service import get_neo4j_graph_service
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
            
            from app.services.neo4j_graph_service import get_neo4j_graph_service
            graph_service = get_neo4j_graph_service()
            
            deleted_count = graph_service.delete_kb_graph(kb_id)
            logger.info(f"删除图谱数据: kb_id={kb_id}, deleted={deleted_count}")
            
            return True
            
        except Exception as e:
            logger.error(f"删除图谱数据失败: {str(e)}")
            return False
