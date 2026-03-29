"""服务层模块

子包结构:
  embedding/       - 嵌入模型服务
  llm/             - LLM 推理服务
  retrieval/       - 检索服务
  knowledge_base/  - 知识库服务
  knowledge_graph/ - 知识图谱服务
  lora/            - LoRA 微调服务
  model/           - 模型管理服务
  chat_service     - RAG 对话服务 (顶层)
  agent_service    - Agent 智能体服务 (顶层)
"""

from app.services.domain.knowledge_base.knowledge_base_service import KnowledgeBaseService
from app.services.domain.knowledge_base.file_service import FileService
from app.services.domain.knowledge_base.metadata_service import MetadataService
from app.services.infrastructure.embedding.embedding_service import EmbeddingService
from app.services.infrastructure.retrieval.vector_store_service import VectorStoreService
from app.services.core.chat_service import ChatService

__all__ = [
    'KnowledgeBaseService',
    'FileService',
    'MetadataService',
    'EmbeddingService',
    'VectorStoreService',
    'ChatService',
]
