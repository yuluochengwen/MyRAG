"""WebSocket API路由"""
from fastapi import APIRouter, WebSocket
from app.websocket.handlers import handle_websocket_connection
from app.websocket.manager import ws_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket连接端点"""
    await handle_websocket_connection(websocket, client_id)


@router.websocket("/ws/training/{client_id}")
async def training_websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    训练进度 WebSocket 连接端点
    
    消息格式:
    {
        "type": "progress" | "log" | "complete" | "error",
        "job_id": int,
        "data": {
            "progress": float,  # 0-100
            "epoch": int,
            "step": int,
            "loss": float,
            "eta": int,  # 预计剩余秒数
            "message": str
        }
    }
    """
    await ws_manager.connect(websocket, client_id)
    logger.info(f"训练 WebSocket 连接建立: client_id={client_id}")
    
    try:
        while True:
            # 保持连接，等待消息
            data = await websocket.receive_text()
            logger.debug(f"收到客户端消息: {data}")
            
    except Exception as e:
        logger.info(f"训练 WebSocket 连接断开: client_id={client_id}, reason={str(e)}")
    finally:
        await ws_manager.disconnect(websocket, client_id)

