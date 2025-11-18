"""WebSocket API路由"""
from fastapi import APIRouter, WebSocket
from app.websocket.handlers import handle_websocket_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket连接端点"""
    await handle_websocket_connection(websocket, client_id)
