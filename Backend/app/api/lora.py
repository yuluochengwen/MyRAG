"""LoRA 模型管理 API"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Form
from typing import Optional, List
import os
import shutil
from pathlib import Path
import uuid
import json

from app.core.dependencies import get_database
from app.core.database import DatabaseManager
from app.services.lora_service import LoRAService
from app.services.lora_training_service import LoRATrainingService
from app.services.dataset_validator_service import DatasetValidatorService
from app.websocket.manager import ws_manager
from app.schemas.lora import (
    LoRAModelResponse,
    LoRAModelListResponse,
    BaseModelInfo,
    BaseModelListResponse,
    TrainingConfigRequest,
    TrainingJobResponse,
    TrainingJobDetailResponse,
    TrainingJobListResponse,
    DatasetValidationResponse,
    MessageResponse
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/lora", tags=["LoRA 管理"])


# ============ LoRA 模型管理端点 ============

@router.get("/models", response_model=LoRAModelListResponse)
async def list_lora_models(
    base_model_name: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: DatabaseManager = Depends(get_database)
):
    """
    获取 LoRA 模型列表
    
    Args:
        base_model_name: 基座模型名称（可选，用于筛选）
        skip: 跳过数量
        limit: 返回数量
    """
    try:
        service = LoRAService(db)
        models = await service.list_lora_models(base_model_name, skip, limit)
        
        model_responses = [
            LoRAModelResponse(**model.to_dict())
            for model in models
        ]
        
        return LoRAModelListResponse(
            total=len(model_responses),
            models=model_responses
        )
        
    except Exception as e:
        logger.error(f"获取 LoRA 模型列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{lora_id}", response_model=LoRAModelResponse)
async def get_lora_model(
    lora_id: int,
    db: DatabaseManager = Depends(get_database)
):
    """获取 LoRA 模型详情"""
    try:
        service = LoRAService(db)
        model = await service.get_lora_model(lora_id)
        
        if not model:
            raise HTTPException(status_code=404, detail="LoRA 模型不存在")
        
        return LoRAModelResponse(**model.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 LoRA 模型详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/models/{lora_id}", response_model=MessageResponse)
async def delete_lora_model(
    lora_id: int,
    db: DatabaseManager = Depends(get_database)
):
    """删除 LoRA 模型"""
    try:
        service = LoRAService(db)
        result = await service.delete_lora_model(lora_id)
        
        if not result["success"]:
            raise HTTPException(status_code=404, detail=result["message"])
        
        return MessageResponse(
            message=result["message"],
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除 LoRA 模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/base-models", response_model=BaseModelListResponse)
async def list_base_models():
    """
    获取可用的基座模型列表
    
    注意：这是一个简化实现，实际应该扫描 Models/LLM/ 目录
    """
    try:
        # TODO: 实际实现应该扫描 Models/LLM/ 目录
        # 这里返回示例数据
        models = [
            BaseModelInfo(
                name="Qwen2.5-3B-Instruct",
                display_name="Qwen2.5-3B-Instruct",
                model_type="llm"
            ),
            BaseModelInfo(
                name="DeepSeek-OCR-3B",
                display_name="DeepSeek-OCR-3B",
                model_type="llm"
            )
        ]
        
        return BaseModelListResponse(
            total=len(models),
            models=models
        )
        
    except Exception as e:
        logger.error(f"获取基座模型列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ 训练任务端点 ============

@router.post("/validate-dataset", response_model=DatasetValidationResponse)
async def validate_training_dataset(
    file: UploadFile = File(...)
):
    """
    验证训练数据集格式
    
    Args:
        file: 训练数据集文件（JSON 格式）
    """
    try:
        # 保存临时文件
        temp_dir = Path("data/training_data/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        temp_file_path = temp_dir / f"{uuid.uuid4()}_{file.filename}"
        
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 验证数据集
        validator = DatasetValidatorService()
        result = validator.validate_dataset(str(temp_file_path))
        
        # 删除临时文件
        temp_file_path.unlink()
        
        return DatasetValidationResponse(**result)
        
    except Exception as e:
        logger.error(f"验证数据集失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train", response_model=TrainingJobResponse)
async def submit_training_job(
    file: UploadFile = File(...),
    config: str = Form(...),
    background_tasks: BackgroundTasks = None,
    db: DatabaseManager = Depends(get_database)
):
    """
    提交训练任务
    
    Args:
        config: 训练配置
    """
    try:
        # 保存训练数据集到临时目录
        temp_dir = Path("data/training_data/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        dataset_path = temp_dir / f"{uuid.uuid4()}_{file.filename}"
        with open(dataset_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 解析前端传入的配置（JSON 字符串）
        raw_config = json.loads(config)

        # 兼容前端现有字段并归一化为训练服务所需结构
        runtime_parameters = {
            "lora_name": raw_config.get("lora_name"),
            "description": raw_config.get("description", ""),
            "lora_rank": raw_config.get("lora_rank", 8),
            "lora_alpha": raw_config.get("lora_alpha", 16),
            "lora_dropout": raw_config.get("lora_dropout", 0.05),
            "learning_rate": raw_config.get("learning_rate", 2e-4),
            "per_device_train_batch_size": raw_config.get("batch_size", 4),
            "num_train_epochs": raw_config.get("epochs", 3),
            "max_seq_length": raw_config.get("max_seq_length", 512),
            "gradient_accumulation_steps": raw_config.get("gradient_accumulation_steps", 1),
            "warmup_steps": raw_config.get("warmup_steps", 100),
            "logging_steps": raw_config.get("logging_steps", 10),
            "save_steps": raw_config.get("save_steps", 500),
            "fp16": raw_config.get("fp16", True),
            "optim": raw_config.get("optim", "adamw_torch")
        }

        service_config = {
            "base_model_name": raw_config.get("base_model") or raw_config.get("base_model_name"),
            "lora_name": raw_config.get("lora_name"),
            "training_mode": raw_config.get("training_mode", "qlora"),
            "dataset_file": str(dataset_path),
            "parameters": runtime_parameters
        }

        service = LoRATrainingService(db, ws_manager)

        # 提交训练任务
        result = await service.submit_training_job(service_config)
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        
        return TrainingJobResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提交训练任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training-jobs", response_model=TrainingJobListResponse)
async def list_training_jobs(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: DatabaseManager = Depends(get_database)
):
    """
    获取训练任务列表
    
    Args:
        status: 任务状态（可选）
        skip: 跳过数量
        limit: 返回数量
    """
    try:
        service = LoRATrainingService(db, ws_manager)
        jobs = await service.list_training_jobs(status, skip, limit)
        
        job_responses = [
            TrainingJobDetailResponse(**job.to_dict())
            for job in jobs
        ]
        
        return TrainingJobListResponse(
            total=len(job_responses),
            jobs=job_responses
        )
        
    except Exception as e:
        logger.error(f"获取训练任务列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training-jobs/{job_id}", response_model=TrainingJobDetailResponse)
async def get_training_job(
    job_id: int,
    db: DatabaseManager = Depends(get_database)
):
    """获取训练任务详情"""
    try:
        service = LoRATrainingService(db, ws_manager)
        job = await service.get_training_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="训练任务不存在")
        
        return TrainingJobDetailResponse(**job.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取训练任务详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/training-jobs/{job_id}/cancel", response_model=MessageResponse)
async def cancel_training_job(
    job_id: int,
    db: DatabaseManager = Depends(get_database)
):
    """取消训练任务"""
    try:
        service = LoRATrainingService(db, ws_manager)
        result = await service.cancel_training(job_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return MessageResponse(
            message=result["message"],
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消训练任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
