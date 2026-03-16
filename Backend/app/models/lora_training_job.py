"""LoRA 训练任务数据模型"""
from datetime import datetime
from typing import Optional, Dict, List, Any
import json


class LoRATrainingJob:
    """LoRA 训练任务模型"""
    
    def __init__(
        self,
        id: int = None,
        lora_model_id: int = None,
        base_model_id: int = None,
        base_model_name: str = None,
        dataset_path: str = None,
        dataset_format: str = None,
        training_mode: str = 'qlora',
        parameters: Dict[str, Any] = None,
        status: str = 'pending',
        progress: float = 0.0,
        current_epoch: int = 0,
        total_epochs: int = 3,
        loss_history: List[Dict] = None,
        log_file_path: str = None,
        error_message: str = None,
        created_at: datetime = None,
        started_at: datetime = None,
        completed_at: datetime = None
    ):
        self.id = id
        self.lora_model_id = lora_model_id
        self.base_model_id = base_model_id
        self.base_model_name = base_model_name
        self.dataset_path = dataset_path
        self.dataset_format = dataset_format
        self.training_mode = training_mode
        self.parameters = parameters or {}
        self.status = status
        self.progress = progress
        self.current_epoch = current_epoch
        self.total_epochs = total_epochs
        self.loss_history = loss_history or []
        self.log_file_path = log_file_path
        self.error_message = error_message
        self.created_at = created_at
        self.started_at = started_at
        self.completed_at = completed_at
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'lora_model_id': self.lora_model_id,
            'base_model_id': self.base_model_id,
            'base_model_name': self.base_model_name,
            'dataset_path': self.dataset_path,
            'dataset_format': self.dataset_format,
            'training_mode': self.training_mode,
            'parameters': self.parameters,
            'status': self.status,
            'progress': self.progress,
            'current_epoch': self.current_epoch,
            'total_epochs': self.total_epochs,
            'loss_history': self.loss_history,
            'log_file_path': self.log_file_path,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建"""
        # 处理 JSON 字段
        if isinstance(data.get('parameters'), str):
            data['parameters'] = json.loads(data['parameters'])
        if isinstance(data.get('loss_history'), str):
            data['loss_history'] = json.loads(data['loss_history'])
        return cls(**data)
