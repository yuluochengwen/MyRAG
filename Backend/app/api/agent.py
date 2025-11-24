"""
Agent API - Agent 智能体接口
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.services.agent_service import AgentService
from app.core.database import get_db
from app.services.ollama_llm_service import OllamaLLMService
from app.services.knowledge_base_service import KnowledgeBaseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["Agent"])


class AgentQueryRequest(BaseModel):
    """Agent 查询请求"""
    query: str = Field(..., description="用户问题")
    session_id: Optional[str] = Field(None, description="会话ID，用于保持上下文")
    max_iterations: Optional[int] = Field(5, description="最大迭代次数", ge=1, le=10)


class AgentQueryResponse(BaseModel):
    """Agent 查询响应"""
    answer: str = Field(..., description="最终答案")
    steps: List[Dict[str, Any]] = Field(..., description="执行步骤")
    success: bool = Field(..., description="是否成功")
    iterations: int = Field(..., description="实际迭代次数")


class ToolInfo(BaseModel):
    """工具信息"""
    name: str
    description: str


# 全局 Agent 实例（实际项目中应该使用依赖注入）
_agent_instance = None


def get_agent_service() -> AgentService:
    """获取 Agent 服务实例"""
    global _agent_instance
    
    if _agent_instance is None:
        try:
            # 初始化 Ollama LLM 服务
            ollama_service = OllamaLLMService()
            
            # 包装为 Agent 兼容的服务
            class LLMServiceWrapper:
                """LLM 服务包装器"""
                def __init__(self, ollama_service):
                    self.ollama = ollama_service
                    # 默认使用的模型
                    self.default_model = "qwen2.5:7b"  # 可以从配置读取
                
                async def generate(self, prompt: str, max_tokens: int = 500, temperature: float = 0.1, **kwargs):
                    """生成文本"""
                    messages = [{"role": "user", "content": prompt}]
                    response_text = await self.ollama.chat(
                        model=self.default_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    return {"text": response_text}
            
            llm_service = LLMServiceWrapper(ollama_service)
            
            # 初始化知识库服务 - 使用 DatabaseManager
            db_manager = get_db()
            kb_service = KnowledgeBaseService(db_manager)
            
            # 创建 Agent
            _agent_instance = AgentService(
                llm_service=llm_service,
                knowledge_base_service=kb_service,
                max_iterations=5
            )
            logger.info("Agent service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize agent service: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Agent 服务初始化失败: {str(e)}")
    
    return _agent_instance


@router.post("/query", response_model=AgentQueryResponse)
async def agent_query(
    request: AgentQueryRequest,
    agent: AgentService = Depends(get_agent_service)
):
    """
    Agent 问答接口
    
    Agent 会自主决定使用哪些工具来回答用户问题
    """
    try:
        logger.info(f"Agent query: {request.query}")
        
        # 更新 max_iterations
        agent.max_iterations = request.max_iterations
        
        # 运行 Agent
        result = await agent.run(
            user_query=request.query,
            session_id=request.session_id
        )
        
        return AgentQueryResponse(**result)
        
    except Exception as e:
        logger.error(f"Agent query failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools", response_model=List[ToolInfo])
async def get_tools(agent: AgentService = Depends(get_agent_service)):
    """
    获取可用工具列表
    """
    try:
        tools = agent.get_tools_info()
        return [ToolInfo(**tool) for tool in tools]
    except Exception as e:
        logger.error(f"Failed to get tools: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register-tool")
async def register_custom_tool(
    name: str,
    description: str,
    # 实际项目中需要更安全的方式来注册自定义工具
    agent: AgentService = Depends(get_agent_service)
):
    """
    注册自定义工具（演示用）
    
    实际生产环境需要更严格的权限控制和安全检查
    """
    try:
        # 这里只是演示，实际需要更复杂的实现
        raise HTTPException(
            status_code=501,
            detail="自定义工具注册功能暂未完全实现，请在代码中直接注册工具"
        )
    except Exception as e:
        logger.error(f"Failed to register tool: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "agent"}
