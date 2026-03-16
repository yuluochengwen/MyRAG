"""LoRA 模型数据模型"""
from datetime import datetime
from typing import Optional


class LoRAModel:
    """LoRA 模型"""
    
    def __init__(
        self,
        id: int = None,
        name: str = None,
        base_model_id: int = None,
        base_model_name: str = None,
        file_path: str = None,
        file_size: int = 0,
        training_job_id: int = None,
        status: str = 'active',
        created_at: datetime = None,
        updated_at: datetime = None
    ):
        self.id = id
        self.name = name
        self.base_model_id = base_model_id
        self.base_model_name = base_model_name
        self.file_path = file_path
        self.file_size = file_size
        self.training_job_id = training_job_id
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'base_model_id': self.base_model_id,
            'base_model_name': self.base_model_name,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'training_job_id': self.training_job_id,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建"""
        return cls(**data)
