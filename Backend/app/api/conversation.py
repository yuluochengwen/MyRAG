"""对话管理API路由"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import json
from app.models.schemas import (
    ConversationCreate, ConversationResponse, ConversationListResponse,
    MessageCreate, ConversationMessageResponse, MessageListResponse
)
from app.core.database import db_manager
from app.services.chat_service import ChatService
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/conversations", tags=["对话管理"])


# ==================== 智能助手聊天请求模型 ====================

class AssistantChatRequest(BaseModel):
    """智能助手聊天请求"""
    query: str
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    max_history_turns: Optional[int] = 10  # 最多读取10轮历史对话（20条消息）
    use_hybrid_retrieval: Optional[bool] = False  # 是否使用混合检索（向量+图谱）


@router.post("", response_model=ConversationResponse)
async def create_conversation(request: ConversationCreate):
    """创建新对话"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 验证助手是否存在
            cursor.execute("SELECT id FROM assistants WHERE id = %s", (request.assistant_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"助手ID {request.assistant_id} 不存在")
            
            # 创建对话
            cursor.execute(
                """INSERT INTO conversations (assistant_id, title) 
                   VALUES (%s, %s)""",
                (request.assistant_id, request.title or '新对话')
            )
            conversation_id = cursor.lastrowid
            
            # 更新助手的对话次数
            cursor.execute(
                """UPDATE assistants 
                   SET conversation_count = conversation_count + 1,
                       last_conversation_at = CURRENT_TIMESTAMP
                   WHERE id = %s""",
                (request.assistant_id,)
            )
            
            # 返回创建的对话
            cursor.execute(
                """SELECT id, assistant_id, title, message_count, created_at, updated_at 
                   FROM conversations WHERE id = %s""",
                (conversation_id,)
            )
            conversation = cursor.fetchone()
            cursor.close()
            
            return ConversationResponse(**conversation)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建对话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=ConversationListResponse)
async def list_conversations(assistant_id: int, limit: int = 50):
    """获取助手的对话列表"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                """SELECT id, assistant_id, title, message_count, created_at, updated_at 
                   FROM conversations 
                   WHERE assistant_id = %s 
                   ORDER BY updated_at DESC 
                   LIMIT %s""",
                (assistant_id, limit)
            )
            conversations = cursor.fetchall()
            cursor.close()
            
            return ConversationListResponse(conversations=conversations)
        
    except Exception as e:
        logger.error(f"获取对话列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: int):
    """获取单个对话详情"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                """SELECT id, assistant_id, title, message_count, created_at, updated_at 
                   FROM conversations WHERE id = %s""",
                (conversation_id,)
            )
            conversation = cursor.fetchone()
            cursor.close()
            
            if not conversation:
                raise HTTPException(status_code=404, detail=f"对话ID {conversation_id} 不存在")
            
            return ConversationResponse(**conversation)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取对话详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(conversation_id: int, request: ConversationCreate):
    """重命名对话"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 检查对话是否存在
            cursor.execute("SELECT id FROM conversations WHERE id = %s", (conversation_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"对话ID {conversation_id} 不存在")
            
            # 更新标题
            cursor.execute(
                """UPDATE conversations 
                   SET title = %s, updated_at = CURRENT_TIMESTAMP 
                   WHERE id = %s""",
                (request.title, conversation_id)
            )
            
            # 返回更新后的对话
            cursor.execute(
                """SELECT id, assistant_id, title, message_count, created_at, updated_at 
                   FROM conversations WHERE id = %s""",
                (conversation_id,)
            )
            conversation = cursor.fetchone()
            cursor.close()
            
            return ConversationResponse(**conversation)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重命名对话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: int):
    """删除对话"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"对话ID {conversation_id} 不存在")
            
            cursor.close()
            return {"message": "对话已删除"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除对话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def get_messages(conversation_id: int, limit: int = 100):
    """获取对话的消息列表"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 验证对话是否存在
            cursor.execute("SELECT id FROM conversations WHERE id = %s", (conversation_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"对话ID {conversation_id} 不存在")
            
            # 获取消息
            cursor.execute(
                """SELECT id, conversation_id, role, content, sources, created_at 
                   FROM messages 
                   WHERE conversation_id = %s 
                   ORDER BY created_at ASC 
                   LIMIT %s""",
                (conversation_id, limit)
            )
            messages = cursor.fetchall()
            cursor.close()
            
            return MessageListResponse(messages=messages)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取消息列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{conversation_id}/messages")
async def delete_conversation_messages(conversation_id: int):
    """清除对话的所有消息"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 检查对话是否存在
            cursor.execute("SELECT id FROM conversations WHERE id = %s", (conversation_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"对话ID {conversation_id} 不存在")
            
            # 删除所有消息
            cursor.execute("DELETE FROM messages WHERE conversation_id = %s", (conversation_id,))
            
            # 重置消息计数
            cursor.execute(
                """UPDATE conversations 
                   SET message_count = 0, 
                       updated_at = CURRENT_TIMESTAMP 
                   WHERE id = %s""",
                (conversation_id,)
            )
            
            cursor.close()
            
            return {"message": "对话消息已清除"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清除对话消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{conversation_id}/messages", response_model=ConversationMessageResponse)
async def create_message(conversation_id: int, request: MessageCreate):
    """创建新消息(保存用户消息或AI回复)"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 验证对话是否存在
            cursor.execute("SELECT id FROM conversations WHERE id = %s", (conversation_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"对话ID {conversation_id} 不存在")
            
            # 插入消息
            sources_json = None
            if request.sources:
                import json
                sources_json = json.dumps(request.sources, ensure_ascii=False)
            
            cursor.execute(
                """INSERT INTO messages (conversation_id, role, content, sources) 
                   VALUES (%s, %s, %s, %s)""",
                (conversation_id, request.role, request.content, sources_json)
            )
            message_id = cursor.lastrowid
            
            # 更新对话的消息数量和更新时间
            cursor.execute(
                """UPDATE conversations 
                   SET message_count = message_count + 1, 
                       updated_at = CURRENT_TIMESTAMP 
                   WHERE id = %s""",
                (conversation_id,)
            )
            
            # 返回创建的消息
            cursor.execute(
                """SELECT id, conversation_id, role, content, sources, created_at 
                   FROM messages WHERE id = %s""",
                (message_id,)
            )
            message = cursor.fetchone()
            cursor.close()
            
            return ConversationMessageResponse(**message)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 智能助手聊天API ====================

@router.post("/{conversation_id}/chat")
async def chat_with_assistant(conversation_id: int, request: AssistantChatRequest):
    """
    智能助手对话（支持多知识库、system_prompt、纯对话等功能）
    
    流程：
    1. 获取对话关联的助手配置
    2. 保存用户消息
    3. 调用chat_service.chat_with_assistant()进行RAG对话
    4. 保存AI回复
    5. 返回结果
    """
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 获取对话信息
            cursor.execute(
                "SELECT assistant_id FROM conversations WHERE id = %s",
                (conversation_id,)
            )
            conv = cursor.fetchone()
            if not conv:
                raise HTTPException(status_code=404, detail=f"对话ID {conversation_id} 不存在")
            
            assistant_id = conv['assistant_id']
            
            # 2. 获取助手配置
            cursor.execute(
                """SELECT id, name, kb_ids, embedding_model, llm_model, 
                          llm_provider, system_prompt 
                   FROM assistants WHERE id = %s""",
                (assistant_id,)
            )
            assistant = cursor.fetchone()
            if not assistant:
                raise HTTPException(status_code=404, detail=f"助手ID {assistant_id} 不存在")
            
            # 3. 解析知识库ID列表
            kb_ids = None
            if assistant['kb_ids']:
                kb_ids = [int(id) for id in assistant['kb_ids'].split(',')]
            
            # 4. 读取历史消息（用于上下文记忆）
            max_messages = request.max_history_turns * 2  # 每轮对话=2条消息
            logger.info(f"准备读取历史消息: conversation_id={conversation_id}, max_messages={max_messages}")
            cursor.execute(
                """SELECT role, content 
                   FROM messages 
                   WHERE conversation_id = %s 
                   ORDER BY created_at DESC 
                   LIMIT %s""",
                (conversation_id, max_messages)
            )
            history_rows = cursor.fetchall()
            logger.info(f"读取到历史消息数量: {len(history_rows)}")
            if history_rows:
                logger.info(f"历史消息预览: {[{'role': row['role'], 'content': row['content'][:30] + '...'} for row in history_rows[:3]]}")
            history_messages = list(reversed(history_rows))  # 反转为时间正序
            
            # 5. 保存用户消息
            cursor.execute(
                """INSERT INTO messages (conversation_id, role, content) 
                   VALUES (%s, %s, %s)""",
                (conversation_id, 'user', request.query)
            )
            
            cursor.close()
        
        # 6. 调用聊天服务（传递历史消息）
        chat_service = ChatService(db_manager)
        result = await chat_service.chat_with_assistant(
            kb_ids=kb_ids,
            query=request.query,
            history_messages=history_messages,
            system_prompt=assistant['system_prompt'],
            top_k=5,
            llm_model=assistant['llm_model'],
            llm_provider=assistant['llm_provider'],
            temperature=request.temperature,
            use_hybrid_retrieval=request.use_hybrid_retrieval
        )
        
        # 7. 保存AI回复
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 保存sources为JSON
            sources_json = None
            if result['sources']:
                import json
                sources_json = json.dumps(result['sources'], ensure_ascii=False)
            
            cursor.execute(
                """INSERT INTO messages (conversation_id, role, content, sources) 
                   VALUES (%s, %s, %s, %s)""",
                (conversation_id, 'assistant', result['answer'], sources_json)
            )
            
            # 更新对话统计
            cursor.execute(
                """UPDATE conversations 
                   SET message_count = message_count + 2, 
                       updated_at = CURRENT_TIMESTAMP 
                   WHERE id = %s""",
                (conversation_id,)
            )
            
            cursor.close()
        
        # 8. 返回结果
        return {
            "answer": result['answer'],
            "sources": result['sources'],
            "embedding_model": result.get('embedding_model'),
            "retrieval_count": result.get('retrieval_count', 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"智能助手对话失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 智能助手流式聊天API ====================

@router.post("/{conversation_id}/chat/stream")
async def chat_with_assistant_stream(conversation_id: int, request: AssistantChatRequest):
    """
    智能助手流式对话（SSE - Server-Sent Events）
    
    返回格式：
    - data: {"type": "sources", "data": {...}}  # 检索结果
    - data: {"type": "text", "data": "文本片段"}  # 生成的文本
    - data: {"type": "done", "data": {}}        # 完成信号
    - data: {"type": "error", "data": {...}}    # 错误信息
    """
    
    async def generate_stream():
        """流式生成器"""
        collected_text = ""  # 收集完整回答
        sources_data = None
        retrieval_count = 0
        embedding_model = None
        
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取对话和助手信息
                cursor.execute(
                    """SELECT c.id, c.assistant_id, a.kb_ids, a.llm_model, 
                              a.llm_provider, a.system_prompt
                       FROM conversations c
                       JOIN assistants a ON c.assistant_id = a.id
                       WHERE c.id = %s""",
                    (conversation_id,)
                )
                result = cursor.fetchone()
                
                if not result:
                    yield f"data: {json.dumps({'type': 'error', 'data': {'error': '对话不存在'}}, ensure_ascii=False)}\n\n"
                    return
                
                conv = result
                kb_ids = [int(id) for id in conv['kb_ids'].split(',')] if conv['kb_ids'] else None
                
                # 读取历史消息（用于上下文记忆）
                max_messages = request.max_history_turns * 2
                logger.info(f"[流式]准备读取历史消息: conversation_id={conversation_id}, max_messages={max_messages}")
                cursor.execute(
                    """SELECT role, content 
                       FROM messages 
                       WHERE conversation_id = %s 
                       ORDER BY created_at DESC 
                       LIMIT %s""",
                    (conversation_id, max_messages)
                )
                history_rows = cursor.fetchall()
                logger.info(f"[流式]读取到历史消息数量: {len(history_rows)}")
                if history_rows:
                    logger.info(f"[流式]历史消息预览: {[{'role': row['role'], 'content': row['content'][:30] + '...'} for row in history_rows[:3]]}")
                history_messages = list(reversed(history_rows))  # 反转为时间正序
                
                # 保存用户消息
                cursor.execute(
                    """INSERT INTO messages (conversation_id, role, content) 
                       VALUES (%s, %s, %s)""",
                    (conversation_id, 'user', request.query)
                )
                cursor.close()
            
            # 调用流式聊天服务（传递历史消息）
            chat_service = ChatService(db_manager)
            async for chunk in chat_service.chat_stream(
                kb_ids=kb_ids,
                query=request.query,
                history_messages=history_messages,
                system_prompt=conv['system_prompt'],
                top_k=5,
                llm_model=conv['llm_model'],
                llm_provider=conv['llm_provider'],
                temperature=request.temperature,
                use_hybrid_retrieval=request.use_hybrid_retrieval
            ):
                chunk_type = chunk.get('type')
                chunk_data = chunk.get('data')
                
                # 处理不同类型的消息
                if chunk_type == 'sources':
                    sources_data = chunk_data.get('sources', [])
                    retrieval_count = chunk_data.get('retrieval_count', 0)
                    embedding_model = chunk_data.get('embedding_model')
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                
                elif chunk_type == 'text':
                    collected_text += chunk_data
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                
                elif chunk_type == 'done':
                    # 保存AI回复到数据库
                    with db_manager.get_connection() as conn:
                        cursor = conn.cursor()
                        
                        sources_json = None
                        if sources_data:
                            sources_json = json.dumps(sources_data, ensure_ascii=False)
                        
                        cursor.execute(
                            """INSERT INTO messages (conversation_id, role, content, sources) 
                               VALUES (%s, %s, %s, %s)""",
                            (conversation_id, 'assistant', collected_text, sources_json)
                        )
                        
                        # 更新对话统计
                        cursor.execute(
                            """UPDATE conversations 
                               SET message_count = message_count + 2, 
                                   updated_at = CURRENT_TIMESTAMP 
                               WHERE id = %s""",
                            (conversation_id,)
                        )
                        cursor.close()
                    
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                
                elif chunk_type == 'error':
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    return
        
        except Exception as e:
            logger.error(f"流式对话失败: {str(e)}", exc_info=True)
            error_chunk = {
                "type": "error",
                "data": {"error": str(e)}
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用Nginx缓冲
        }
    )
