"""LoRA 训练管理 API 路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel

from app.core.dependencies import get_database
from app.core.database import DatabaseManager
from app.services.llama_factory_service import get_llama_factory_service
from app.services.lora_scanner_service import LoRAScannerService
from app.services.transformers_service import TransformersService
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/lora", tags=["LoRA训练"])

# 创建全局 TransformersService 实例
transformers_service = TransformersService()


# ==================== 请求/响应模型 ====================

class ServiceStatusResponse(BaseModel):
    """服务状态响应"""
    running: bool
    message: str
    pid: Optional[int] = None
    port: Optional[int] = None
    url: Optional[str] = None
    started_at: Optional[str] = None
    log_file: Optional[str] = None


class LoRAModelResponse(BaseModel):
    """LoRA 模型响应"""
    model_config = {"protected_namespaces": ()}
    
    id: int
    model_name: str
    base_model: str
    model_path: str
    status: str
    is_deployed: bool
    ollama_model_name: Optional[str]
    lora_rank: Optional[int]
    lora_alpha: Optional[int]
    file_size_mb: float
    description: Optional[str]
    created_at: str
    deployed_at: Optional[str]


# ==================== LLaMA-Factory 服务管理 ====================

@router.post("/service/start")
async def start_training_service():
    """启动 LLaMA-Factory Web UI"""
    try:
        service = get_llama_factory_service()
        result = service.start()
        
        if not result["success"]:
            # 不抛出异常,返回失败信息即可
            return result
        
        return result
        
    except Exception as e:
        logger.error(f"启动服务失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/service/stop")
async def stop_training_service():
    """停止 LLaMA-Factory Web UI"""
    try:
        service = get_llama_factory_service()
        result = service.stop()
        
        if not result["success"]:
            return result
        
        return result
        
    except Exception as e:
        logger.error(f"停止服务失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service/status")
async def get_service_status():
    """获取服务状态"""
    try:
        service = get_llama_factory_service()
        status = service.get_status()
        return status
        
    except Exception as e:
        logger.error(f"获取服务状态失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== LoRA 模型管理 ====================

@router.get("/models")
async def list_lora_models(db: DatabaseManager = Depends(get_database)):
    """列出所有 LoRA 模型"""
    try:
        scanner = LoRAScannerService(db)
        models = scanner.list_models()
        
        return {
            "success": True,
            "total": len(models),
            "models": models
        }
        
    except Exception as e:
        logger.error(f"列出模型失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{model_id}")
async def get_lora_model(
    model_id: int,
    db: DatabaseManager = Depends(get_database)
):
    """获取单个 LoRA 模型详情"""
    try:
        scanner = LoRAScannerService(db)
        model = scanner.get_model(model_id)
        
        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: ID={model_id}")
        
        return {
            "success": True,
            "model": model
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型详情失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/scan")
async def scan_lora_models(db: DatabaseManager = Depends(get_database)):
    """扫描训练目录，发现新模型"""
    try:
        scanner = LoRAScannerService(db)
        new_models = scanner.scan_training_output()
        
        return {
            "success": True,
            "message": f"扫描完成，发现 {len(new_models)} 个新模型",
            "new_models": new_models,
            "count": len(new_models)
        }
        
    except Exception as e:
        logger.error(f"扫描模型失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/{model_id}/activate")
async def activate_lora_model(
    model_id: int,
    db: DatabaseManager = Depends(get_database)
):
    """激活 LoRA 模型"""
    try:
        scanner = LoRAScannerService(db)
        result = scanner.activate_lora(model_id)
        
        if not result["success"]:
            # 返回失败信息但不抛出异常
            return result
        
        return result
        
    except Exception as e:
        logger.error(f"激活模型失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/models/{model_id}")
async def delete_lora_model(
    model_id: int,
    force: bool = Query(False, description="是否强制删除（解除助手关联）"),
    db: DatabaseManager = Depends(get_database)
):
    """删除 LoRA 模型"""
    try:
        scanner = LoRAScannerService(db)
        result = scanner.delete_model(model_id, force=force)
        
        if not result["success"]:
            # 如果是因为在使用中，返回 409 Conflict
            if result.get("in_use"):
                raise HTTPException(
                    status_code=409,
                    detail=result["message"]
                )
            # 其他失败
            return result
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除模型失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 辅助端点 ====================

@router.get("/base-models")
async def list_base_models():
    """列出可用的基座模型（从本地 Models/LLM 目录扫描）"""
    try:
        from pathlib import Path
        from app.core.config import settings
        
        llm_dir = Path(settings.file.upload_dir).parent / "Models" / "LLM"
        
        if not llm_dir.exists():
            return {
                "success": True,
                "models": [],
                "message": "本地模型目录不存在"
            }
        
        base_models = []
        for model_path in llm_dir.iterdir():
            if model_path.is_dir():
                # 检查是否包含模型文件
                has_model = any([
                    (model_path / "pytorch_model.bin").exists(),
                    (model_path / "model.safetensors").exists(),
                    any(model_path.glob("*.safetensors"))
                ])
                
                if has_model:
                    base_models.append({
                        "name": model_path.name,
                        "path": str(model_path)
                    })
        
        return {
            "success": True,
            "models": base_models,
            "count": len(base_models)
        }
        
    except Exception as e:
        logger.error(f"列出基座模型失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== LoRA 推理测试 ====================

class LoRAInferenceRequest(BaseModel):
    """LoRA 推理请求"""
    model_id: int
    prompt: str
    max_tokens: int = 256
    temperature: float = 0.7


@router.post("/models/{model_id}/test")
async def test_lora_inference(
    model_id: int,
    request: LoRAInferenceRequest,
    db: DatabaseManager = Depends(get_database)
):
    """测试 LoRA 模型推理"""
    try:
        # 获取模型信息
        scanner = LoRAScannerService(db)
        model = scanner.get_model(model_id)
        
        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: ID={model_id}")
        
        logger.info(f"测试 LoRA 推理: {model['model_name']}")
        
        # 加载模型
        base_model = model['base_model']
        lora_path = model['model_path']
        
        success = await transformers_service.load_model_with_lora(
            base_model=base_model,
            lora_path=lora_path,
            quantize=True
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="LoRA 模型加载失败")
        
        # 执行推理
        logger.info(f"开始推理: {request.prompt[:50]}...")
        
        messages = [
            {"role": "user", "content": request.prompt}
        ]
        
        response = await transformers_service.chat(
            model=base_model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=False
        )
        
        return {
            "success": True,
            "model_id": model_id,
            "model_name": model['model_name'],
            "prompt": request.prompt,
            "response": response
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LoRA 推理测试失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

