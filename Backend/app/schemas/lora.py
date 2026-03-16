"""LoRA 相关的 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============ LoRA 模型相关 ============

class LoRAModelResponse(BaseModel):
    """LoRA 模型响应"""
    id: int
    name: str
    base_model_id: Optional[int] = None
    base_model_name: str
    file_path: str
    file_size: int
    training_job_id: Optional[int] = None
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LoRAModelListResponse(BaseModel):
    """LoRA 模型列表响应"""
    total: int
    models: List[LoRAModelResponse]


class BaseModelInfo(BaseModel):
    """基座模型信息"""
    id: Optional[int] = None
    name: str
    display_name: str
    model_type: str
    file_size: Optional[int] = None


class BaseModelListResponse(BaseModel):
    """基座模型列表响应"""
    total: int
    models: List[BaseModelInfo]


# ============ 训练配置相关 ============

class TrainingParameters(BaseModel):
    """训练参数"""
    r: int = Field(default=8, description="LoRA rank")
    lora_alpha: int = Field(default=16, description="LoRA alpha")
    lora_dropout: float = Field(default=0.05, description="LoRA dropout")
    learning_rate: float = Field(default=2e-4, description="学习率")
    per_device_train_batch_size: int = Field(default=4, description="Batch size")
    num_train_epochs: int = Field(default=3, description="训练轮数")
    max_seq_length: int = Field(default=512, description="最大序列长度")
    gradient_accumulation_steps: int = Field(default=1, description="梯度累积步数")
    warmup_steps: int = Field(default=100, description="预热步数")
    logging_steps: int = Field(default=10, description="日志记录步数")
    save_steps: int = Field(default=500, description="保存步数")
    fp16: bool = Field(default=True, description="是否使用 fp16")
    optim: str = Field(default="adamw_torch", description="优化器")


class TrainingConfigRequest(BaseModel):
    """训练配置请求"""
    base_model_name: str = Field(..., description="基座模型名称")
    lora_name: str = Field(..., description="LoRA 权重名称")
    training_mode: str = Field(default="qlora", description="训练模式: lora 或 qlora")
    dataset_file: str = Field(..., description="训练数据集文件路径（临时文件）")
    parameters: Optional[TrainingParameters] = Field(default_factory=TrainingParameters, description="训练参数")


class TrainingJobResponse(BaseModel):
    """训练任务响应"""
    job_id: int
    status: str
    message: str
    client_id: Optional[str] = None


# ============ 训练任务详情相关 ============

class LossRecord(BaseModel):
    """Loss 记录"""
    epoch: int
    step: int
    loss: float
    timestamp: str


class TrainingJobDetailResponse(BaseModel):
    """训练任务详情响应"""
    id: int
    lora_model_id: Optional[int] = None
    base_model_id: Optional[int] = None
    base_model_name: str
    dataset_path: str
    dataset_format: str
    training_mode: str
    parameters: Dict[str, Any]
    status: str
    progress: float
    current_epoch: int
    total_epochs: int
    loss_history: List[Dict[str, Any]]
    log_file_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TrainingJobListResponse(BaseModel):
    """训练任务列表响应"""
    total: int
    jobs: List[TrainingJobDetailResponse]


# ============ 数据验证相关 ============

class DatasetValidationResponse(BaseModel):
    """数据集验证响应"""
    valid: bool
    format: str  # "alpaca" | "conversation" | "unknown"
    sample_count: int
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ============ WebSocket 消息相关 ============

class TrainingProgressData(BaseModel):
    """训练进度数据"""
    progress: float  # 0-100
    epoch: int
    step: int
    loss: Optional[float] = None
    eta: Optional[int] = None  # 预计剩余秒数
    message: Optional[str] = None


class WSTrainingMessage(BaseModel):
    """WebSocket 训练消息"""
    type: str  # "progress" | "log" | "complete" | "error"
    job_id: int
    data: Optional[Dict[str, Any]] = None


# ============ 通用响应 ============

class MessageResponse(BaseModel):
    """通用消息响应"""
    message: str
    success: bool = True
