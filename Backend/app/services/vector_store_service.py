"""向量存储服务"""
import os
from typing import List, Optional, Dict, Any
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class VectorStoreService:
    """向量存储服务（ChromaDB）"""
    
    def __init__(self):
        self.persist_dir = settings.vector_db.persist_dir
        
        # 确保存储目录存在
        os.makedirs(self.persist_dir, exist_ok=True)
        
        # 初始化ChromaDB持久化客户端
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(
                anonymized_telemetry=False
            )
        )
        
        logger.info(f"向量存储初始化: persist_dir={self.persist_dir}")
    
    def get_or_create_collection(
        self,
        collection_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        获取或创建集合
        
        Args:
            collection_name: 集合名称
            metadata: 元数据
            
        Returns:
            集合对象
        """
        try:
            # ChromaDB 不接受空字典作为 metadata,使用 None 代替
            collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata=metadata if metadata else None
            )
            
            logger.debug(f"获取集合: {collection_name}, count={collection.count()}")
            return collection
            
        except Exception as e:
            logger.error(f"获取集合失败: {str(e)}")
            raise
    
    def add_vectors(
        self,
        collection_name: str,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        添加向量到集合
        
        Args:
            collection_name: 集合名称
            ids: ID列表
            embeddings: 向量列表
            documents: 文档列表
            metadatas: 元数据列表
            
        Returns:
            是否成功
        """
        try:
            collection = self.get_or_create_collection(collection_name)
            
            # 确保元数据中的所有值都是字符串类型(ChromaDB要求)
            if metadatas:
                processed_metadatas = [
                    {k: str(v) for k, v in meta.items()}
                    for meta in metadatas
                ]
            else:
                processed_metadatas = None
            
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=processed_metadatas
            )
            
            logger.info(f"向量添加成功: collection={collection_name}, count={len(ids)}")
            return True
            
        except Exception as e:
            logger.error(f"添加向量失败: {str(e)}")
            raise
    
    def search(
        self,
        collection_name: str,
        query_embeddings: List[List[float]],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        搜索相似向量
        
        Args:
            collection_name: 集合名称
            query_embeddings: 查询向量列表
            n_results: 返回结果数量
            where: 元数据过滤条件
            where_document: 文档过滤条件
            
        Returns:
            搜索结果
        """
        try:
            collection = self.get_or_create_collection(collection_name)
            
            results = collection.query(
                query_embeddings=query_embeddings,
                n_results=n_results,
                where=where,
                where_document=where_document
            )
            
            logger.info(f"向量搜索完成: collection={collection_name}, "
                       f"queries={len(query_embeddings)}, n_results={n_results}")
            
            return results
            
        except Exception as e:
            logger.error(f"向量搜索失败: {str(e)}")
            raise
    
    def delete_by_ids(
        self,
        collection_name: str,
        ids: List[str]
    ) -> bool:
        """
        根据ID删除向量
        
        Args:
            collection_name: 集合名称
            ids: ID列表
            
        Returns:
            是否成功
        """
        try:
            collection = self.get_or_create_collection(collection_name)
            
            collection.delete(ids=ids)
            
            logger.info(f"向量删除成功: collection={collection_name}, count={len(ids)}")
            return True
            
        except Exception as e:
            logger.error(f"删除向量失败: {str(e)}")
            raise
    
    def delete_collection(self, collection_name: str) -> bool:
        """
        删除整个集合
        
        Args:
            collection_name: 集合名称
            
        Returns:
            是否成功
        """
        try:
            self.client.delete_collection(name=collection_name)
            
            logger.info(f"集合删除成功: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"删除集合失败: {str(e)}")
            raise
    
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """
        获取集合统计信息
        
        Args:
            collection_name: 集合名称
            
        Returns:
            统计信息
        """
        try:
            collection = self.get_or_create_collection(collection_name)
            
            return {
                'name': collection_name,
                'count': collection.count(),
                'metadata': collection.metadata
            }
            
        except Exception as e:
            logger.error(f"获取集合统计失败: {str(e)}")
            raise
    
    def list_collections(self) -> List[str]:
        """
        列出所有集合
        
        Returns:
            集合名称列表
        """
        try:
            collections = self.client.list_collections()
            return [col.name for col in collections]
            
        except Exception as e:
            logger.error(f"列出集合失败: {str(e)}")
            raise
    
    def update_metadata(
        self,
        collection_name: str,
        ids: List[str],
        metadatas: List[Dict[str, Any]]
    ) -> bool:
        """
        更新向量元数据
        
        Args:
            collection_name: 集合名称
            ids: ID列表
            metadatas: 新的元数据列表
            
        Returns:
            是否成功
        """
        try:
            collection = self.get_or_create_collection(collection_name)
            
            collection.update(
                ids=ids,
                metadatas=metadatas
            )
            
            logger.info(f"元数据更新成功: collection={collection_name}, count={len(ids)}")
            return True
            
        except Exception as e:
            logger.error(f"更新元数据失败: {str(e)}")
            raise
    
    def get_by_ids(
        self,
        collection_name: str,
        ids: List[str]
    ) -> Dict[str, Any]:
        """
        根据ID获取向量
        
        Args:
            collection_name: 集合名称
            ids: ID列表
            
        Returns:
            向量数据
        """
        try:
            collection = self.get_or_create_collection(collection_name)
            
            results = collection.get(ids=ids)
            
            logger.debug(f"获取向量: collection={collection_name}, count={len(ids)}")
            return results
            
        except Exception as e:
            logger.error(f"获取向量失败: {str(e)}")
            raise
