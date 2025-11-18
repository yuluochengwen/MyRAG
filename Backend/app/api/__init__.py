"""API路由模块"""
from app.api.knowledge_base import router as kb_router
from app.api.websocket import router as ws_router
from app.api.assistant import router as assistant_router
from app.api.conversation import router as conversation_router

__all__ = [
    'kb_router',
    'ws_router',
    'assistant_router',
    'conversation_router',
]
