"""
简化 LoRA 训练 API 路由
"""
import os
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from app.core.database import db_manager
from app.services.simple_lora_trainer import SimpleLoRATrainer
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/simple-lora", tags=["SimpleLORA"])


# 请求/响应模型
class TrainingTaskRequest(BaseModel):
    task_name: str
    base_model: str
    dataset_type: str = "alpaca"


class TrainingTaskResponse(BaseModel):
    task_id: int
    task_name: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: int
    task_name: str
    status: str
    progress: float
    current_epoch: int
    message: str
    created_at: str = None
    completed_at: str = None


# 全局训练器实例
_trainer_instance = None


def get_trainer() -> SimpleLoRATrainer:
    """获取训练器实例"""
    global _trainer_instance
    if _trainer_instance is None:
        _trainer_instance = SimpleLoRATrainer(db_manager)
    return _trainer_instance


@router.get("/models", summary="获取可用的基座模型列表")
async def list_base_models():
    """列出 Models/LLM/ 目录下的所有模型"""
    try:
        # 使用统一的模型扫描器，支持 Hugging Face 嵌套结构
        from app.services.model_scanner import model_scanner
        
        scanned_models = model_scanner.scan_llm_models()
        
        models = []
        for m in scanned_models:
            # 优先使用 root_dir_name 作为 value，确保后端能找到文件夹
            # 如果没有 root_dir_name (旧版本 scanner)，则使用 name
            value = m.get("root_dir_name", m["name"])
            
            models.append({
                "name": m["name"],
                "value": value,
                "path": m["path"],
                "size_mb": m["size_bytes"] / (1024 * 1024)
            })
        
        return {"models": models, "count": len(models)}
    
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-dataset", summary="上传训练数据集")
async def upload_dataset(
    file: UploadFile = File(...),
    dataset_type: str = Form("alpaca")
):
    """
    上传训练数据集
    支持格式: JSON (alpaca, sharegpt)
    """
    try:
        trainer = get_trainer()
        
        # 验证文件类型
        if not file.filename.endswith(('.json', '.jsonl')):
            raise HTTPException(status_code=400, detail="仅支持 JSON 格式文件")
        
        # 保存文件
        file_path = trainer.datasets_dir / file.filename
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"数据集上传成功: {file_path}")
        
        return {
            "filename": file.filename,
            "path": str(file_path),
            "size_mb": len(content) / (1024 * 1024),
            "message": "上传成功"
        }
    
    except Exception as e:
        logger.error(f"上传数据集失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train", summary="创建并启动训练任务", response_model=TrainingTaskResponse)
async def create_training_task(
    task_name: str = Form(...),
    base_model: str = Form(...),
    dataset_filename: str = Form(...),
    dataset_type: str = Form("alpaca")
):
    """
    创建并启动训练任务
    
    Args:
        task_name: 任务名称
        base_model: 基座模型名称
        dataset_filename: 数据集文件名
        dataset_type: 数据集类型 (alpaca, sharegpt)
    """
    try:
        trainer = get_trainer()
        
        # 验证基座模型
        # 修复：支持 Hugging Face 嵌套结构
        # 如果 base_model 包含路径分隔符，说明是嵌套路径，直接使用
        # 否则，尝试在 base_models_dir 下查找
        
        # 1. 尝试直接拼接路径
        model_path = trainer.base_models_dir / base_model
        
        # 2. 如果不存在，尝试查找是否是 Hugging Face 格式的简化名
        if not model_path.exists():
            # 可能是前端传来的 root_dir_name (models--deepseek...)
            # 或者是优化后的名字 (deepseek-ai/DeepSeek...)
            
            # 尝试在目录下搜索匹配的文件夹
            found = False
            for item in trainer.base_models_dir.iterdir():
                if item.is_dir():
                    # 检查是否匹配 (忽略大小写)
                    if item.name.lower() == base_model.lower() or \
                       item.name.replace("models--", "").replace("--", "/").lower() == base_model.lower():
                        model_path = item
                        found = True
                        break
            
            if not found:
                # 如果还是没找到，且 base_model 看起来像是一个路径，尝试解析它
                # 比如 base_model 是 "models--deepseek.../snapshots/..."
                # 但这里我们假设前端传的是 root_dir_name
                pass

        # 3. 再次检查是否存在 (此时 model_path 可能是找到的目录)
        if not model_path.exists():
             # 最后尝试：如果 base_model 本身就是绝对路径（虽然不太可能）
            if Path(base_model).is_absolute() and Path(base_model).exists():
                model_path = Path(base_model)
            else:
                logger.error(f"基座模型路径不存在: {model_path}")
                raise HTTPException(status_code=404, detail=f"基座模型不存在: {base_model}")
        
        # 4. 深入检查：如果是 Hugging Face 结构，需要指向 snapshots 下的真实目录
        # 这一步很重要，因为 trainer 需要加载 config.json
        if not (model_path / "config.json").exists() and (model_path / "snapshots").exists():
            snapshots_dir = model_path / "snapshots"
            for snapshot in snapshots_dir.iterdir():
                if snapshot.is_dir() and (snapshot / "config.json").exists():
                    model_path = snapshot
                    break
        
        logger.info(f"使用基座模型路径: {model_path}")

        # 验证数据集
        dataset_path = trainer.datasets_dir / dataset_filename
        if not dataset_path.exists():
            raise HTTPException(status_code=404, detail=f"数据集不存在: {dataset_filename}")
        
        # 创建任务
        # 注意：这里传入的是 model_path 的相对路径或绝对路径，取决于 trainer 如何处理
        # 为了保险，我们传入相对于 base_models_dir 的路径，或者绝对路径
        # SimpleLoRATrainer 内部是这样处理的: base_model_path = self.base_models_dir / task['base_model']
        # 所以如果传入绝对路径，pathlib 会忽略前面的 self.base_models_dir
        
        task_id = await trainer.create_training_task(
            task_name=task_name,
            base_model_name=str(model_path), # 传入解析后的完整路径
            dataset_file=str(dataset_path),
            dataset_type=dataset_type
        )
        
        # 启动训练
        await trainer.start_training(task_id)
        
        logger.info(f"训练任务已创建并启动: ID={task_id}")
        
        return TrainingTaskResponse(
            task_id=task_id,
            task_name=task_name,
            status="running",
            message="训练任务已启动，完成后请手动扫描LoRA模型"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建训练任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", summary="获取任务状态", response_model=TaskStatusResponse)
async def get_task_status(task_id: int):
    """查询训练任务状态"""
    try:
        trainer = get_trainer()
        status = trainer.get_task_status(task_id)
        
        if "error" in status:
            raise HTTPException(status_code=404, detail=status["error"])
        
        return TaskStatusResponse(**status)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks", summary="获取所有训练任务")
async def list_tasks():
    """列出所有训练任务"""
    try:
        trainer = get_trainer()
        tasks = trainer.list_tasks()
        
        return {
            "tasks": [
                {
                    "task_id": t['id'],
                    "task_name": t['task_name'],
                    "base_model": t['base_model'],
                    "status": t['status'],
                    "progress": float(t['progress']) if t['progress'] else 0.0,
                    "created_at": t['created_at'].isoformat() if t['created_at'] else None
                }
                for t in tasks
            ],
            "count": len(tasks)
        }
    
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets", summary="获取已上传的数据集列表")
async def list_datasets():
    """列出所有已上传的数据集"""
    try:
        trainer = get_trainer()
        datasets_dir = trainer.datasets_dir
        
        if not datasets_dir.exists():
            return {"datasets": [], "count": 0}
        
        datasets = []
        for file in datasets_dir.glob("*.json"):
            datasets.append({
                "filename": file.name,
                "size_mb": file.stat().st_size / (1024 * 1024),
                "created_at": file.stat().st_ctime
            })
        
        return {"datasets": datasets, "count": len(datasets)}
    
    except Exception as e:
        logger.error(f"获取数据集列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
