"""FastAPI依赖注入"""
from typing import Generator
from app.core.database import db_manager, DatabaseManager
from app.services import (
    KnowledgeBaseService,
    FileService,
    EmbeddingService,
    VectorStoreService,
    ChatService
)


def get_database() -> Generator[DatabaseManager, None, None]:
    """
    获取数据库管理器
    
    用于FastAPI路由的依赖注入:
        @router.get("/users")
        async def get_users(db: DatabaseManager = Depends(get_database)):
            ...
    """
    try:
        yield db_manager
    finally:
        pass


def get_db_connection():
    """获取数据库连接"""
    return db_manager.get_connection()


def get_db_cursor():
    """获取数据库游标"""
    return db_manager.get_cursor()


# 服务依赖注入
def get_kb_service() -> KnowledgeBaseService:
    """获取知识库服务"""
    return KnowledgeBaseService(db_manager)


def get_file_service() -> FileService:
    """获取文件服务"""
    return FileService(db_manager)


def get_embedding_service() -> EmbeddingService:
    """获取向量化服务"""
    return EmbeddingService()


def get_vector_service() -> VectorStoreService:
    """获取向量存储服务"""
    return VectorStoreService()


def get_chat_service() -> ChatService:
    """获取对话服务"""
    return ChatService(db_manager)


# 别名兼容
get_vector_store_service = get_vector_service
