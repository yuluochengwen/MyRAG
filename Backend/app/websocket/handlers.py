"""WebSocket消息处理"""
from fastapi import WebSocket, WebSocketDisconnect
from app.websocket.manager import ws_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def handle_websocket_connection(websocket: WebSocket, client_id: str):
    """
    处理WebSocket连接
    
    Args:
        websocket: WebSocket连接
        client_id: 客户端ID
    """
    await ws_manager.connect(websocket, client_id)
    
    try:
        while True:
            # 接收客户端消息（保持连接活跃）
            data = await websocket.receive_text()
            
            # 处理心跳包,返回JSON格式
            if data == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        logger.info(f"客户端主动断开连接: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket连接异常: {client_id}, {str(e)}")
    finally:
        await ws_manager.disconnect(websocket, client_id)
