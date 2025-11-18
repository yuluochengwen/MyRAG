"""知识库数据模型"""
from datetime import datetime
from typing import Optional


class KnowledgeBase:
    """知识库模型"""
    
    def __init__(
        self,
        id: int = None,
        name: str = None,
        embedding_model: str = None,
        embedding_provider: str = "transformers",
        description: str = None,
        file_count: int = 0,
        chunk_count: int = 0,
        status: str = 'creating',
        created_at: datetime = None,
        updated_at: datetime = None
    ):
        self.id = id
        self.name = name
        self.embedding_model = embedding_model
        self.embedding_provider = embedding_provider
        self.description = description
        self.file_count = file_count
        self.chunk_count = chunk_count
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'embedding_model': self.embedding_model,
            'embedding_provider': self.embedding_provider,
            'description': self.description,
            'file_count': self.file_count,
            'chunk_count': self.chunk_count,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建"""
        return cls(**data)
