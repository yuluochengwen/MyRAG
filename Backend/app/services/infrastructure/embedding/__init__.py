"""嵌入模型服务"""
from app.services.infrastructure.embedding.embedding_service import EmbeddingService, get_embedding_service
from app.services.infrastructure.embedding.ollama_embedding_service import OllamaEmbeddingService, get_ollama_embedding_service

__all__ = [
    'EmbeddingService', 'get_embedding_service',
    'OllamaEmbeddingService', 'get_ollama_embedding_service',
]
