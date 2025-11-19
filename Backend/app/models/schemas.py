"""Pydantic数据模型 - 用于API请求和响应"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator


# ==================== 知识库相关 ====================

class KnowledgeBaseCreate(BaseModel):
    """创建知识库请求"""
    name: str = Field(..., description="知识库名称", min_length=1, max_length=100)
    embedding_model: str = Field(..., description="嵌入模型")
    embedding_provider: str = Field("transformers", description="嵌入提供方: transformers, ollama")
    description: Optional[str] = Field(None, description="描述", max_length=500)
    
    @validator('name')
    def validate_name(cls, v):
        import re
        pattern = r'^[\u4e00-\u9fa5a-zA-Z0-9_-]+$'
        if not re.match(pattern, v):
            raise ValueError('知识库名称只能包含中文、英文、数字、下划线和连字符')
        return v
    
    @validator('embedding_provider')
    def validate_provider(cls, v):
        if v not in ['transformers', 'ollama']:
            raise ValueError('嵌入提供方必须是transformers或ollama')
        return v


class KnowledgeBaseResponse(BaseModel):
    """知识库响应"""
    id: int
    name: str
    embedding_model: str
    embedding_provider: str = "transformers"
    description: Optional[str] = None
    file_count: int = 0
    chunk_count: int = 0
    graph_stats: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        
    @classmethod
    def from_model(cls, kb, graph_stats=None):
        """从kb模型创建"""
        return cls(
            id=kb.id,
            name=kb.name,
            embedding_model=kb.embedding_model,
            embedding_provider=getattr(kb, 'embedding_provider', 'transformers'),
            description=kb.description,
            file_count=kb.file_count,
            chunk_count=kb.chunk_count,
            graph_stats=graph_stats,
            status=kb.status,
            created_at=kb.created_at,
            updated_at=kb.updated_at
        )


class KnowledgeBaseListResponse(BaseModel):
    """知识库列表响应"""
    total: int
    items: List[KnowledgeBaseResponse]


# ==================== 文件相关 ====================

class FileInfo(BaseModel):
    """文件信息"""
    filename: str
    file_size: int
    file_type: str


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    id: int
    filename: str
    file_type: str
    file_size: int
    status: str


class FileListResponse(BaseModel):
    """文件列表响应"""
    id: int
    kb_id: int
    filename: str
    file_type: str
    file_size: int
    chunk_count: int = 0
    status: str
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ==================== 处理进度相关 ====================

class ProcessProgress(BaseModel):
    """处理进度"""
    kb_id: int
    file_id: Optional[int] = None
    stage: str = Field(..., description="当前阶段")
    progress: float = Field(..., ge=0, le=100, description="进度百分比")
    message: str = Field(..., description="进度消息")
    current_file: Optional[str] = None
    total_files: Optional[int] = None
    processed_files: Optional[int] = None


# ==================== 嵌入模型相关 ====================

class EmbeddingModelInfo(BaseModel):
    """嵌入模型信息"""
    name: str
    path: str
    dimensions: Optional[int] = None
    available: bool = True


class EmbeddingModelListResponse(BaseModel):
    """嵌入模型列表响应"""
    models: List[EmbeddingModelInfo]


# ==================== 通用响应 ====================

class SuccessResponse(BaseModel):
    """成功响应"""
    success: bool = True
    message: str
    data: Optional[dict] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: str
    detail: Optional[str] = None


class CreateKnowledgeBaseResponse(BaseModel):
    """创建知识库响应"""
    success: bool
    kb_id: int
    message: str
    client_id: str = Field(..., description="WebSocket客户端ID，用于接收进度")


class MessageResponse(BaseModel):
    """通用消息响应（用于删除、更新等操作）"""
    message: str


class SimpleMessageResponse(BaseModel):
    """简单消息响应（别名，保持兼容性）"""
    message: str


# ==================== WebSocket消息 ====================

class WSMessage(BaseModel):
    """WebSocket消息"""
    type: str = Field(..., description="消息类型: progress, error, complete")
    data: dict = Field(..., description="消息数据")


class WSProgressMessage(BaseModel):
    """WebSocket进度消息"""
    type: str = "progress"
    kb_id: int
    stage: str
    progress: float
    message: str
    current_file: Optional[str] = None
    total_files: Optional[int] = None
    processed_files: Optional[int] = None


class WSErrorMessage(BaseModel):
    """WebSocket错误消息"""
    type: str = "error"
    kb_id: int
    error: str
    detail: Optional[str] = None


class WSCompleteMessage(BaseModel):
    """WebSocket完成消息"""
    type: str = "complete"
    kb_id: int
    message: str
    file_count: int
    chunk_count: int


# ==================== 知识库检索相关 ====================

class SearchRequest(BaseModel):
    """知识库检索请求"""
    query: str = Field(..., min_length=1, max_length=1000, description="查询文本")
    top_k: Optional[int] = Field(5, ge=1, le=20, description="返回结果数量")
    score_threshold: Optional[float] = Field(0.0, ge=0.0, le=1.0, description="相似度阈值")


class SearchResult(BaseModel):
    """单条检索结果"""
    chunk_id: str
    content: str
    similarity: float
    metadata: Dict[str, Any]


class SearchResponse(BaseModel):
    """知识库检索响应"""
    kb_id: int
    kb_name: str
    embedding_model: str = Field(..., description="使用的嵌入模型")
    query: str
    results: List[SearchResult]
    total: int


# ==================== 智能助手对话相关 ====================

class ChatRequest(BaseModel):
    """智能助手对话请求"""
    kb_id: int = Field(..., description="知识库ID")
    query: str = Field(..., min_length=1, max_length=1000, description="用户问题")
    top_k: Optional[int] = Field(5, ge=1, le=10, description="检索文档数量")
    llm_model: Optional[str] = Field(None, description="LLM模型名称")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="生成温度")


class ChatSource(BaseModel):
    """对话来源文档"""
    content: str
    similarity: float
    file_id: int


class ChatResponse(BaseModel):
    """智能助手对话响应"""
    answer: str
    sources: List[ChatSource]
    embedding_model: str = Field(..., description="使用的嵌入模型")
    retrieval_count: int


# ==================== 智能助手相关 ====================

class PromptTemplate(BaseModel):
    """提示词模板"""
    name: str
    description: str
    content: str


class AssistantCreate(BaseModel):
    """创建智能助手请求"""
    name: str = Field(..., min_length=1, max_length=255, description="助手名称")
    description: Optional[str] = Field(None, description="助手描述")
    kb_ids: Optional[List[int]] = Field(None, description="关联知识库ID列表(需相同embedding_model)")
    embedding_model: Optional[str] = Field(None, description="嵌入模型(选择KB时自动继承)")
    llm_model: str = Field(..., description="大语言模型")
    llm_provider: str = Field(default="local", description="LLM提供方: local, ollama, openai, azure")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    color_theme: str = Field(default="blue", description="卡片配色主题")
    
    @validator('kb_ids')
    def validate_kb_ids(cls, v):
        if v is not None and len(v) == 0:
            return None
        return v
    
    @validator('llm_provider')
    def validate_llm_provider(cls, v):
        if v not in ['local', 'transformers', 'ollama', 'openai', 'azure']:
            raise ValueError('LLM提供方必须是local, transformers, ollama, openai或azure之一')
        return v


class AssistantResponse(BaseModel):
    """智能助手响应"""
    id: int
    name: str
    description: Optional[str]
    kb_ids: Optional[List[int]]
    kb_names: Optional[List[str]]  # 关联知识库名称列表
    embedding_model: str
    llm_model: str
    llm_provider: str
    system_prompt: Optional[str]
    color_theme: str
    status: str
    conversation_count: int = 0  # 对话次数统计
    total_messages: int = 0  # 总消息数统计
    last_conversation_at: Optional[datetime] = None  # 最后对话时间
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ==================== 对话管理相关 ====================

class ConversationCreate(BaseModel):
    """创建对话请求"""
    assistant_id: int = Field(..., description="助手ID")
    title: Optional[str] = Field("新对话", description="对话标题")


class ConversationResponse(BaseModel):
    """对话响应"""
    id: int
    assistant_id: int
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    """对话列表响应"""
    conversations: List[ConversationResponse]


class MessageCreate(BaseModel):
    """创建消息请求"""
    role: str = Field(..., description="角色: user 或 assistant")
    content: str = Field(..., description="消息内容")
    sources: Optional[List[dict]] = Field(None, description="来源文档(仅assistant)")


class ConversationMessageResponse(BaseModel):
    """对话消息响应（用于对话历史）"""
    id: int
    conversation_id: int
    role: str
    content: str
    sources: Optional[List[dict]]
    created_at: datetime
    
    @validator('sources', pre=True)
    def parse_sources(cls, v):
        """解析JSON字符串或返回原值"""
        if v is None:
            return None
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except:
                return None
        return v
    
    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """消息列表响应"""
    messages: List[ConversationMessageResponse]


class ModelInfo(BaseModel):
    """模型信息"""
    name: str
    path: str
    provider: str  # local, openai, azure
    dimension: Optional[int] = None  # embedding模型维度


class PromptTemplateList(BaseModel):
    """提示词模板列表"""
    templates: List[PromptTemplate]
