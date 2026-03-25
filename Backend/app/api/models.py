"""模型管理API路由"""
import asyncio
import time
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.utils import HfHubHTTPError
from tqdm.auto import tqdm

from app.core.dependencies import get_database
from app.core.database import DatabaseManager
from app.services.model.model_scanner import model_scanner
from app.services.model.model_manager import get_model_manager
from app.websocket.manager import ws_manager
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


class DownloadModelRequest(BaseModel):
    """下载模型请求"""
    model_name: str
    model_type: str  # embedding | llm
    client_id: Optional[str] = None


def _safe_model_folder_name(model_name: str) -> str:
    """将HF模型名称转为本地安全目录名"""
    return model_name.strip().replace("/", "--").replace("\\", "--")


def _build_friendly_download_error(error: Exception) -> str:
    """构建友好的下载失败提示"""
    error_text = str(error)
    error_lower = error_text.lower()

    if isinstance(error, HfHubHTTPError):
        status_code = getattr(error.response, "status_code", None)
        if status_code == 401:
            return (
                "下载失败：该模型需要登录或授权访问（401）。"
                "如果是受限模型，请先在 HuggingFace 页面申请权限并配置访问令牌后重试。"
            )
        if status_code == 403:
            return (
                "下载失败：该模型当前无访问权限（403）。"
                "请先在 HuggingFace 申请访问权限或检查令牌权限。"
            )
        if status_code == 404:
            return "下载失败：未找到该模型，请检查模型名称是否正确（例如 org/model_name）。"

    if "gated" in error_lower or "access" in error_lower or "permission" in error_lower:
        return "下载失败：该模型可能需要申请访问权限，请先在 HuggingFace 页面申请后再试。"

    if (
        "timed out" in error_lower
        or "timeout" in error_lower
        or "connection" in error_lower
        or "nameresolutionerror" in error_lower
        or "temporary failure" in error_lower
    ):
        return (
            "下载失败：网络连接不稳定或无法访问 HuggingFace。"
            "请稍后重试，或使用网络代理后再试。"
        )

    return f"下载失败：{error_text}"


async def _send_download_event(
    client_id: Optional[str],
    task_id: str,
    model_name: str,
    model_type: str,
    event: str,
    progress: float,
    message: str,
    **kwargs
):
    """向客户端发送模型下载事件"""
    if not client_id:
        return

    payload = {
        "type": "model_download",
        "event": event,
        "task_id": task_id,
        "model_name": model_name,
        "model_type": model_type,
        "progress": float(progress),
        "message": message,
        **kwargs
    }

    await ws_manager.send_message(client_id, payload)


def _download_model_with_progress(
    model_name: str,
    target_dir: Path,
    model_type: str,
    client_id: Optional[str],
    task_id: str,
    loop: asyncio.AbstractEventLoop
):
    """在线程中执行模型下载，并通过WebSocket推送真实进度"""
    last_emit_time = 0.0
    last_progress = -1.0

    def emit_progress(progress: float, message: str):
        nonlocal last_emit_time, last_progress

        progress = max(0.0, min(99.0, float(progress)))
        now = time.time()

        if progress <= last_progress and (now - last_emit_time) < 0.5:
            return

        last_progress = progress
        last_emit_time = now

        future = asyncio.run_coroutine_threadsafe(
            _send_download_event(
                client_id=client_id,
                task_id=task_id,
                model_name=model_name,
                model_type=model_type,
                event="progress",
                progress=progress,
                message=message
            ),
            loop
        )
        try:
            future.result(timeout=5)
        except Exception as ws_error:
            logger.debug(f"发送下载进度失败(忽略，不中断下载): {str(ws_error)}")

    class DownloadTqdm(tqdm):
        def update(self, n=1):
            super().update(n)
            total = float(self.total or 0)
            if total > 0:
                current_progress = (float(self.n) / total) * 99.0
                emit_progress(current_progress, "正在下载模型文件...")

    snapshot_download(
        repo_id=model_name,
        local_dir=str(target_dir),
        local_dir_use_symlinks=False,
        resume_download=True,
        tqdm_class=DownloadTqdm
    )


async def _download_model_task(
    model_name: str,
    model_type: str,
    client_id: Optional[str],
    task_id: str,
    target_dir: Path
):
    """后台下载任务"""
    try:
        await _send_download_event(
            client_id=client_id,
            task_id=task_id,
            model_name=model_name,
            model_type=model_type,
            event="started",
            progress=0,
            message="下载任务已开始"
        )

        loop = asyncio.get_running_loop()
        await asyncio.to_thread(
            _download_model_with_progress,
            model_name,
            target_dir,
            model_type,
            client_id,
            task_id,
            loop
        )

        await _send_download_event(
            client_id=client_id,
            task_id=task_id,
            model_name=model_name,
            model_type=model_type,
            event="complete",
            progress=100,
            message=f"模型下载成功：{model_name}",
            path=str(target_dir)
        )
    except Exception as e:
        friendly_error = _build_friendly_download_error(e)
        logger.error(f"下载模型失败: model={model_name}, type={model_type}, error={str(e)}")

        await _send_download_event(
            client_id=client_id,
            task_id=task_id,
            model_name=model_name,
            model_type=model_type,
            event="error",
            progress=0,
            message=friendly_error,
            error=friendly_error
        )


@router.post("/download")
async def download_model_from_huggingface(req: DownloadModelRequest):
    """从HuggingFace下载模型到本地目录（异步任务）"""
    model_name = req.model_name.strip()
    model_type = req.model_type.strip().lower()
    client_id = req.client_id

    if not model_name:
        raise HTTPException(status_code=400, detail="模型名称不能为空")

    if model_type not in {"embedding", "llm"}:
        raise HTTPException(status_code=400, detail="模型类型必须为 embedding 或 llm")

    try:
        target_base_dir = Path(model_scanner.embedding_dir) if model_type == "embedding" else Path(model_scanner.llm_dir)
        target_base_dir.mkdir(parents=True, exist_ok=True)

        folder_name = _safe_model_folder_name(model_name)
        target_dir = target_base_dir / folder_name
        task_id = f"download_{uuid4().hex}"

        asyncio.create_task(
            _download_model_task(
                model_name=model_name,
                model_type=model_type,
                client_id=client_id,
                task_id=task_id,
                target_dir=target_dir
            )
        )

        return {
            "success": True,
            "message": f"模型下载任务已创建：{model_name}",
            "task_id": task_id,
            "model_name": model_name,
            "model_type": model_type
        }
    except Exception as e:
        logger.error(f"创建下载任务失败: model={model_name}, type={model_type}, error={str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


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
    """获取所有LLM模型列表（仅本地）"""
    try:
        all_models = model_scanner.get_all_llm_models()
        local_models = all_models["local"]
        
        # 为本地模型添加使用情况
        model_manager = get_model_manager(db)
        for model in local_models:
            try:
                usage = await model_manager.check_llm_model_usage(model["name"])
                model["usage"] = usage
            except Exception as e:
                logger.warning(f"获取模型使用情况失败: {model['name']}, {e}")
                model["usage"] = {"is_used": False, "total_usage": 0}
        
        return {
            "success": True,
            "local_count": len(local_models),
            "remote_count": 0,
            "total": len(local_models),
            "local": local_models,
            "remote": []
        }
    except Exception as e:
        logger.error(f"获取LLM模型列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/llm/{model_name}")
async def get_llm_model_detail(
    model_name: str,
    db: DatabaseManager = Depends(get_database)
):
    """获取单个本地LLM模型详情"""
    try:
        all_models = model_scanner.get_all_llm_models()
        local_models = all_models["local"]
        
        # 在本地模型中查找
        model = next((m for m in local_models if m["name"] == model_name), None)
        
        if model:
            # 获取使用情况
            model_manager = get_model_manager(db)
            usage = await model_manager.check_llm_model_usage(model_name)
            model["usage"] = usage
        
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
