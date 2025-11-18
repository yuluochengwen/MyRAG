"""WebSocket连接管理器"""
import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # client_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """
        接受WebSocket连接
        
        Args:
            websocket: WebSocket连接
            client_id: 客户端ID
        """
        await websocket.accept()
        
        async with self._lock:
            if client_id not in self.active_connections:
                self.active_connections[client_id] = set()
            self.active_connections[client_id].add(websocket)
        
        logger.info(f"WebSocket连接建立: client_id={client_id}, "
                   f"总连接数={self.get_connection_count()}")
    
    async def disconnect(self, websocket: WebSocket, client_id: str):
        """
        断开WebSocket连接
        
        Args:
            websocket: WebSocket连接
            client_id: 客户端ID
        """
        async with self._lock:
            if client_id in self.active_connections:
                self.active_connections[client_id].discard(websocket)
                
                # 如果该客户端没有连接了，删除键
                if not self.active_connections[client_id]:
                    del self.active_connections[client_id]
        
        logger.info(f"WebSocket连接断开: client_id={client_id}, "
                   f"剩余连接数={self.get_connection_count()}")
    
    async def send_message(self, client_id: str, message: dict):
        """
        向指定客户端发送消息
        
        Args:
            client_id: 客户端ID
            message: 消息内容（字典）
        """
        if client_id not in self.active_connections:
            logger.warning(f"客户端不存在: {client_id}")
            return
        
        message_str = json.dumps(message, ensure_ascii=False, default=str)
        
        # 复制连接集合，避免在发送时修改
        connections = list(self.active_connections[client_id])
        
        for connection in connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.error(f"发送消息失败: {str(e)}")
                # 如果发送失败，断开连接
                await self.disconnect(connection, client_id)
    
    async def send_progress(
        self,
        client_id: str,
        kb_id: int,
        stage: str,
        progress: float,
        message: str,
        **kwargs
    ):
        """
        发送处理进度
        
        Args:
            client_id: 客户端ID
            kb_id: 知识库ID
            stage: 当前阶段
            progress: 进度（0-100）
            message: 进度消息
            **kwargs: 其他参数
        """
        data = {
            'type': 'progress',
            'kb_id': kb_id,
            'stage': stage,
            'progress': progress,
            'message': message,
            **kwargs
        }
        
        await self.send_message(client_id, data)
        logger.debug(f"发送进度: client_id={client_id}, stage={stage}, progress={progress}%")
    
    async def send_error(
        self,
        client_id: str,
        kb_id: int,
        error: str,
        detail: str = None
    ):
        """
        发送错误消息
        
        Args:
            client_id: 客户端ID
            kb_id: 知识库ID
            error: 错误信息
            detail: 详细信息
        """
        data = {
            'type': 'error',
            'kb_id': kb_id,
            'error': error,
            'detail': detail
        }
        
        await self.send_message(client_id, data)
        logger.error(f"发送错误: client_id={client_id}, error={error}")
    
    async def send_complete(
        self,
        client_id: str,
        kb_id: int,
        message: str,
        **kwargs
    ):
        """
        发送完成消息
        
        Args:
            client_id: 客户端ID
            kb_id: 知识库ID
            message: 完成消息
            **kwargs: 其他参数
        """
        data = {
            'type': 'complete',
            'kb_id': kb_id,
            'message': message,
            **kwargs
        }
        
        await self.send_message(client_id, data)
        logger.info(f"发送完成: client_id={client_id}, message={message}")
    
    async def broadcast(self, message: dict):
        """
        广播消息给所有连接
        
        Args:
            message: 消息内容
        """
        message_str = json.dumps(message, ensure_ascii=False, default=str)
        
        for client_id, connections in self.active_connections.items():
            for connection in list(connections):
                try:
                    await connection.send_text(message_str)
                except Exception as e:
                    logger.error(f"广播消息失败: {str(e)}")
                    await self.disconnect(connection, client_id)
    
    def get_connection_count(self) -> int:
        """获取当前连接总数"""
        return sum(len(conns) for conns in self.active_connections.values())
    
    def get_client_count(self) -> int:
        """获取客户端数量"""
        return len(self.active_connections)
    
    def is_connected(self, client_id: str) -> bool:
        """检查客户端是否在线"""
        return client_id in self.active_connections and len(self.active_connections[client_id]) > 0


# 全局WebSocket管理器
ws_manager = ConnectionManager()
