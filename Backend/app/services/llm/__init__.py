"""LLM 推理服务"""
from app.services.llm.ollama_llm_service import OllamaLLMService, get_ollama_llm_service
from app.services.llm.transformers_service import TransformersService, get_transformers_service

__all__ = [
    'OllamaLLMService', 'get_ollama_llm_service',
    'TransformersService', 'get_transformers_service',
]
