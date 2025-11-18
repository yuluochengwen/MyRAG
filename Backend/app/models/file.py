"""文件数据模型"""
from datetime import datetime
from typing import Optional


class File:
    """文件模型"""
    
    def __init__(
        self,
        id: int = None,
        kb_id: int = None,
        filename: str = None,
        file_type: str = None,
        file_size: int = None,
        file_hash: str = None,
        storage_path: str = None,
        chunk_count: int = 0,
        status: str = 'uploaded',
        error_message: str = None,
        processed_at: datetime = None,
        
        created_at: datetime = None,
        updated_at: datetime = None
    ):
        self.id = id
        self.kb_id = kb_id
        self.filename = filename
        self.file_type = file_type
        self.file_size = file_size
        self.file_hash = file_hash
        self.storage_path = storage_path
        self.chunk_count = chunk_count
        self.status = status
        self.error_message = error_message
        self.processed_at = processed_at
        self.created_at = created_at
        self.updated_at = updated_at
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'kb_id': self.kb_id,
            'filename': self.filename,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'file_hash': self.file_hash,
            'storage_path': self.storage_path,
            'chunk_count': self.chunk_count,
            'status': self.status,
            'error_message': self.error_message,
            'processed_at': self.processed_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建"""
        return cls(**data)
