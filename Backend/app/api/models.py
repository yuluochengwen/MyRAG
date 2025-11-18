"""模型管理API路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel

from app.core.dependencies import get_database
from app.core.database import DatabaseManager
from app.services.model_scanner import model_scanner
from app.services.model_manager import get_model_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/models", tags=["模型管理"])


# ==================== 请求/响应模型 ====================

class ModelDetailResponse(BaseModel):
    """模型详情响应"""
    name: str
    path: str
    type: str
    status: str
    size: str
    created_at: str
    usage: Optional[dict] = None


class DeleteRequest(BaseModel):
    """删除请求"""
    force: bool = False


# ==================== 嵌入模型API ====================

@router.get("/embedding")
async def get_embedding_models(db: DatabaseManager = Depends(get_database)):
    """获取所有嵌入模型列表"""
    try:
        models = model_scanner.scan_embedding_models()
        
        # 为每个模型添加使用情况
        model_manager = get_model_manager(db)
        for model in models:
            try:
                usage = await model_manager.check_embedding_model_usage(model["name"])
                model["usage"] = usage
            except Exception as e:
                logger.warning(f"获取模型使用情况失败: {model['name']}, {e}")
                model["usage"] = {"is_used": False, "total_usage": 0}
        
        return {
            "success": True,
            "total": len(models),
            "models": models
        }
    except Exception as e:
        logger.error(f"获取嵌入模型列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/embedding/{model_name}")
async def get_embedding_model_detail(
    model_name: str,
    db: DatabaseManager = Depends(get_database)
):
    """获取单个嵌入模型详情"""
    try:
        models = model_scanner.scan_embedding_models()
        model = next((m for m in models if m["name"] == model_name), None)
        
        if not model:
            raise HTTPException(status_code=404, detail=f"模型 '{model_name}' 不存在")
        
        # 获取使用情况
        model_manager = get_model_manager(db)
        usage = await model_manager.check_embedding_model_usage(model_name)
        model["usage"] = usage
        
        return {
            "success": True,
            "model": model
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取嵌入模型详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/embedding/{model_name}")
async def delete_embedding_model(
    model_name: str,
    force: bool = Query(False, description="是否强制删除"),
    db: DatabaseManager = Depends(get_database)
):
    """删除嵌入模型"""
    try:
        model_manager = get_model_manager(db)
        result = await model_manager.delete_embedding_model(model_name, force)
        
        if not result["success"]:
            return result
        
        return result
    except Exception as e:
        logger.error(f"删除嵌入模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embedding/scan")
async def scan_embedding_models():
    """重新扫描嵌入模型目录"""
    try:
        models = model_scanner.scan_embedding_models()
        return {
            "success": True,
            "message": "扫描完成",
            "total": len(models),
            "models": models
        }
    except Exception as e:
        logger.error(f"扫描嵌入模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== LLM模型API ====================

@router.get("/llm")
async def get_llm_models(db: DatabaseManager = Depends(get_database)):
    """获取所有LLM模型列表（本地+远程）"""
    try:
        all_models = model_scanner.get_all_llm_models()
        local_models = all_models["local"]
        remote_models = all_models["remote"]
        
        # 为本地模型添加使用情况
        model_manager = get_model_manager(db)
        for model in local_models:
            try:
                usage = await model_manager.check_llm_model_usage(model["name"])
                model["usage"] = usage
            except Exception as e:
                logger.warning(f"获取模型使用情况失败: {model['name']}, {e}")
                model["usage"] = {"is_used": False, "total_usage": 0}
        
        # 远程模型标记为不可删除
        for model in remote_models:
            model["can_delete"] = False
            model["status"] = "available"
        
        return {
            "success": True,
            "local_count": len(local_models),
            "remote_count": len(remote_models),
            "total": len(local_models) + len(remote_models),
            "local": local_models,
            "remote": remote_models
        }
    except Exception as e:
        logger.error(f"获取LLM模型列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/llm/{model_name}")
async def get_llm_model_detail(
    model_name: str,
    db: DatabaseManager = Depends(get_database)
):
    """获取单个LLM模型详情"""
    try:
        all_models = model_scanner.get_all_llm_models()
        local_models = all_models["local"]
        remote_models = all_models["remote"]
        
        # 先在本地模型中查找
        model = next((m for m in local_models if m["name"] == model_name), None)
        
        if model:
            # 获取使用情况
            model_manager = get_model_manager(db)
            usage = await model_manager.check_llm_model_usage(model_name)
            model["usage"] = usage
        else:
            # 在远程模型中查找
            model = next((m for m in remote_models if m["name"] == model_name), None)
            if model:
                model["can_delete"] = False
        
        if not model:
            raise HTTPException(status_code=404, detail=f"模型 '{model_name}' 不存在")
        
        return {
            "success": True,
            "model": model
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取LLM模型详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/llm/{model_name}")
async def delete_llm_model(
    model_name: str,
    force: bool = Query(False, description="是否强制删除"),
    db: DatabaseManager = Depends(get_database)
):
    """删除本地LLM模型"""
    try:
        # 检查是否是远程模型
        remote_models = model_scanner.get_remote_llm_models()
        if any(m["name"] == model_name for m in remote_models):
            raise HTTPException(status_code=400, detail="远程模型不可删除")
        
        model_manager = get_model_manager(db)
        result = await model_manager.delete_llm_model(model_name, force)
        
        if not result["success"]:
            return result
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除LLM模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/llm/scan")
async def scan_llm_models():
    """重新扫描LLM模型目录"""
    try:
        models = model_scanner.scan_llm_models()
        return {
            "success": True,
            "message": "扫描完成",
            "total": len(models),
            "models": models
        }
    except Exception as e:
        logger.error(f"扫描LLM模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== LoRA模型API ====================

@router.get("/lora")
async def get_lora_models():
    """获取所有LoRA模型列表"""
    try:
        models = model_scanner.scan_lora_models()
        return {
            "success": True,
            "total": len(models),
            "models": models
        }
    except Exception as e:
        logger.error(f"获取LoRA模型列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lora/{model_name}")
async def get_lora_model_detail(model_name: str):
    """获取单个LoRA模型详情"""
    try:
        models = model_scanner.scan_lora_models()
        model = next((m for m in models if m["name"] == model_name), None)
        
        if not model:
            raise HTTPException(status_code=404, detail=f"LoRA模型 '{model_name}' 不存在")
        
        return {
            "success": True,
            "model": model
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取LoRA模型详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/lora/{model_name}")
async def delete_lora_model(
    model_name: str,
    db: DatabaseManager = Depends(get_database)
):
    """删除LoRA模型"""
    try:
        model_manager = get_model_manager(db)
        result = await model_manager.delete_lora_model(model_name)
        
        if not result["success"]:
            return result
        
        return result
    except Exception as e:
        logger.error(f"删除LoRA模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lora/scan")
async def scan_lora_models():
    """重新扫描LoRA模型目录"""
    try:
        models = model_scanner.scan_lora_models()
        return {
            "success": True,
            "message": "扫描完成",
            "total": len(models),
            "models": models
        }
    except Exception as e:
        logger.error(f"扫描LoRA模型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 统计信息API ====================

@router.get("/statistics")
async def get_model_statistics(db: DatabaseManager = Depends(get_database)):
    """获取模型统计信息"""
    try:
        model_manager = get_model_manager(db)
        stats = await model_manager.get_statistics()
        return {
            "success": True,
            "statistics": stats
        }
    except Exception as e:
        logger.error(f"获取统计信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
