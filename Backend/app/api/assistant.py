"""智能助手API路由 - 使用原生SQL"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from app.core.dependencies import get_database
from app.core.database import DatabaseManager
from app.models.schemas import (
    AssistantCreate, 
    AssistantResponse, 
    ModelInfo, 
    PromptTemplate, 
    PromptTemplateList
)
from app.services.model_scanner import model_scanner
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/assistants", tags=["智能助手"])


# ==================== 提示词模板 ====================

PROMPT_TEMPLATES = [
    PromptTemplate(
        name="通用对话助手",
        description="适合日常交流的友好助手",
        content="你是一个友好、专业的AI助手。请用简洁、准确的语言回答用户问题。"
    ),
    PromptTemplate(
        name="知识库问答助手",
        description="基于知识库进行专业问答",
        content="你是一个专业的知识库问答助手。请基于提供的参考资料,给出准确、详细的回答。如果资料中没有相关信息,请如实告知用户。"
    ),
    PromptTemplate(
        name="产品顾问",
        description="专业的产品咨询助手",
        content="你是一个专业的产品顾问。请根据产品知识库中的信息,为客户提供专业、详细的产品咨询服务。重点突出产品优势和适用场景。"
    ),
    PromptTemplate(
        name="研发助手",
        description="帮助开发者解决技术问题",
        content="你是一个专业的研发助手。请根据技术文档和代码库,帮助开发者解决技术问题。回答需要准确、清晰,并提供代码示例。"
    ),
    PromptTemplate(
        name="销售助手",
        description="辅助销售人员进行客户沟通",
        content="你是一个专业的销售助手。请根据产品和客户信息,帮助销售人员制定沟通策略,提供专业的解决方案。语言要友好、有说服力。"
    ),
]


@router.get("/prompt-templates", response_model=PromptTemplateList)
async def get_prompt_templates():
    """获取提示词模板列表"""
    return PromptTemplateList(templates=PROMPT_TEMPLATES)


# ==================== 助手CRUD ====================

@router.post("", response_model=AssistantResponse, status_code=201)
async def create_assistant(
    assistant_data: AssistantCreate,
    db: DatabaseManager = Depends(get_database)
):
    """创建智能助手"""
    try:
        # 1. 处理知识库绑定逻辑
        kb_ids_str = None
        kb_names = []
        
        if assistant_data.kb_ids:
            # 查询知识库信息
            placeholders = ','.join(['%s'] * len(assistant_data.kb_ids))
            sql = f"SELECT id, name, embedding_model FROM knowledge_bases WHERE id IN ({placeholders})"
            results = await db.execute_query(sql, tuple(assistant_data.kb_ids))
            
            if len(results) != len(assistant_data.kb_ids):
                raise HTTPException(status_code=404, detail="部分知识库不存在")
            
            # 检查embedding_model一致性
            embedding_models = set(kb['embedding_model'] for kb in results)
            if len(embedding_models) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"选择的知识库使用了不同的嵌入模型: {', '.join(embedding_models)}"
                )
            
            assistant_data.embedding_model = results[0]['embedding_model']
            kb_ids_str = ','.join(map(str, assistant_data.kb_ids))
            kb_names = [kb['name'] for kb in results]
        
        elif not assistant_data.embedding_model:
            raise HTTPException(status_code=400, detail="未选择知识库时必须指定嵌入模型")
        
        # 2. 验证LLM模型
        if assistant_data.llm_provider in ["local", "transformers"]:
            llm_models = model_scanner.scan_llm_models()
            llm_names = [m["name"] for m in llm_models]
            if assistant_data.llm_model not in llm_names:
                raise HTTPException(
                    status_code=404,
                    detail=f"LLM模型 '{assistant_data.llm_model}' 不存在"
                )
        elif assistant_data.llm_provider == "ollama":
            # 验证Ollama模型
            from app.services.ollama_llm_service import get_ollama_llm_service
            ollama_service = get_ollama_llm_service()
            
            if not ollama_service.is_available():
                raise HTTPException(
                    status_code=503,
                    detail="Ollama服务不可用，请确保Ollama已启动"
                )
            
            ollama_models = ollama_service.list_available_models()
            ollama_model_names = [m["name"] for m in ollama_models]
            
            if assistant_data.llm_model not in ollama_model_names:
                raise HTTPException(
                    status_code=404,
                    detail=f"Ollama模型 '{assistant_data.llm_model}' 不存在或未安装"
                )

        
        # 3. 插入数据库
        sql = """
            INSERT INTO assistants 
            (name, description, kb_ids, embedding_model, llm_model, llm_provider, system_prompt, color_theme, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
        """
        assistant_id = await db.execute_insert(sql, (
            assistant_data.name,
            assistant_data.description,
            kb_ids_str,
            assistant_data.embedding_model,
            assistant_data.llm_model,
            assistant_data.llm_provider,
            assistant_data.system_prompt,
            assistant_data.color_theme
        ))
        
        # 4. 查询创建的记录
        sql = "SELECT * FROM assistants WHERE id = %s"
        result = await db.execute_query(sql, (assistant_id,))
        assistant = result[0]
        
        return AssistantResponse(
            id=assistant['id'],
            name=assistant['name'],
            description=assistant['description'],
            kb_ids=assistant_data.kb_ids,
            kb_names=kb_names if kb_names else None,
            embedding_model=assistant['embedding_model'],
            llm_model=assistant['llm_model'],
            llm_provider=assistant['llm_provider'],
            system_prompt=assistant['system_prompt'],
            color_theme=assistant['color_theme'],
            status=assistant['status'],
            created_at=assistant['created_at'],
            updated_at=assistant['updated_at']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建助手失败: {str(e)}")


@router.get("/{assistant_id}", response_model=AssistantResponse)
async def get_assistant(assistant_id: int, db: DatabaseManager = Depends(get_database)):
    """获取单个助手详情"""
    try:
        sql = """
            SELECT id, name, description, kb_ids, embedding_model, llm_model, llm_provider, 
                   system_prompt, color_theme, status, conversation_count, total_messages, 
                   last_conversation_at, created_at, updated_at 
            FROM assistants 
            WHERE id = %s
        """
        assistants = await db.execute_query(sql, (assistant_id,))
        
        if not assistants:
            raise HTTPException(status_code=404, detail=f"助手ID {assistant_id} 不存在")
        
        assistant = assistants[0]
        
        # 解析kb_ids
        kb_ids = None
        kb_names = None
        if assistant['kb_ids']:
            kb_ids = [int(id) for id in assistant['kb_ids'].split(',')]
            
            # 查询知识库名称
            placeholders = ','.join(['%s'] * len(kb_ids))
            kb_sql = f"SELECT name FROM knowledge_bases WHERE id IN ({placeholders})"
            kbs = await db.execute_query(kb_sql, tuple(kb_ids))
            kb_names = [kb['name'] for kb in kbs]
        
        return AssistantResponse(
            id=assistant['id'],
            name=assistant['name'],
            description=assistant['description'],
            kb_ids=kb_ids,
            kb_names=kb_names,
            embedding_model=assistant['embedding_model'],
            llm_model=assistant['llm_model'],
            llm_provider=assistant['llm_provider'],
            system_prompt=assistant['system_prompt'],
            color_theme=assistant['color_theme'],
            status=assistant['status'],
            conversation_count=assistant['conversation_count'] or 0,
            total_messages=assistant['total_messages'] or 0,
            last_conversation_at=assistant['last_conversation_at'],
            created_at=assistant['created_at'],
            updated_at=assistant['updated_at']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取助手详情失败: {str(e)}")


@router.get("", response_model=List[AssistantResponse])
async def list_assistants(db: DatabaseManager = Depends(get_database)):
    """获取所有助手列表"""
    try:
        sql = """
            SELECT id, name, description, kb_ids, embedding_model, llm_model, llm_provider, 
                   system_prompt, color_theme, status, conversation_count, total_messages, 
                   last_conversation_at, created_at, updated_at 
            FROM assistants 
            WHERE status = 'active' 
            ORDER BY created_at DESC
        """
        assistants = await db.execute_query(sql)
        
        result = []
        for assistant in assistants:
            # 解析kb_ids
            kb_ids = None
            kb_names = None
            if assistant['kb_ids']:
                kb_ids = [int(id) for id in assistant['kb_ids'].split(',')]
                
                # 查询知识库名称
                placeholders = ','.join(['%s'] * len(kb_ids))
                kb_sql = f"SELECT name FROM knowledge_bases WHERE id IN ({placeholders})"
                kbs = await db.execute_query(kb_sql, tuple(kb_ids))
                kb_names = [kb['name'] for kb in kbs]
            
            result.append(AssistantResponse(
                id=assistant['id'],
                name=assistant['name'],
                description=assistant['description'],
                kb_ids=kb_ids,
                kb_names=kb_names,
                embedding_model=assistant['embedding_model'],
                llm_model=assistant['llm_model'],
                llm_provider=assistant['llm_provider'],
                system_prompt=assistant['system_prompt'],
                color_theme=assistant['color_theme'],
                status=assistant['status'],
                conversation_count=assistant['conversation_count'] or 0,
                total_messages=assistant['total_messages'] or 0,
                last_conversation_at=assistant['last_conversation_at'],
                created_at=assistant['created_at'],
                updated_at=assistant['updated_at']
            ))
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取助手列表失败: {str(e)}")


@router.put("/{assistant_id}", response_model=AssistantResponse)
async def update_assistant(
    assistant_id: int,
    assistant_data: AssistantCreate,
    db: DatabaseManager = Depends(get_database)
):
    """更新智能助手配置"""
    try:
        # 1. 检查助手是否存在
        sql = "SELECT id FROM assistants WHERE id = %s"
        result = await db.execute_query(sql, (assistant_id,))
        if not result:
            raise HTTPException(status_code=404, detail="助手不存在")
        
        # 2. 处理知识库绑定逻辑
        kb_ids_str = None
        
        if assistant_data.kb_ids:
            # 查询知识库信息
            placeholders = ','.join(['%s'] * len(assistant_data.kb_ids))
            sql = f"SELECT id, name, embedding_model FROM knowledge_bases WHERE id IN ({placeholders})"
            results = await db.execute_query(sql, tuple(assistant_data.kb_ids))
            
            if len(results) != len(assistant_data.kb_ids):
                raise HTTPException(status_code=404, detail="部分知识库不存在")
            
            # 检查embedding_model一致性
            embedding_models = set(kb['embedding_model'] for kb in results)
            if len(embedding_models) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"选择的知识库使用了不同的嵌入模型: {', '.join(embedding_models)}"
                )
            
            assistant_data.embedding_model = results[0]['embedding_model']
            kb_ids_str = ','.join(map(str, assistant_data.kb_ids))
        
        # 3. 验证LLM模型
        if assistant_data.llm_provider in ["local", "transformers"]:
            llm_models = model_scanner.scan_llm_models()
            llm_names = [m["name"] for m in llm_models]
            if assistant_data.llm_model not in llm_names:
                raise HTTPException(
                    status_code=404,
                    detail=f"LLM模型 '{assistant_data.llm_model}' 不存在"
                )
        elif assistant_data.llm_provider == "ollama":
            # 验证Ollama模型
            from app.services.ollama_llm_service import get_ollama_llm_service
            ollama_service = get_ollama_llm_service()
            
            if not ollama_service.is_available():
                raise HTTPException(
                    status_code=503,
                    detail="Ollama服务不可用，请确保Ollama已启动"
                )
            
            ollama_models = ollama_service.list_available_models()
            ollama_model_names = [m["name"] for m in ollama_models]
            
            if assistant_data.llm_model not in ollama_model_names:
                raise HTTPException(
                    status_code=404,
                    detail=f"Ollama模型 '{assistant_data.llm_model}' 不存在或未安装"
                )
        
        # 4. 更新数据库
        sql = """
            UPDATE assistants 
            SET name = %s, 
                description = %s, 
                kb_ids = %s, 
                embedding_model = %s, 
                llm_model = %s, 
                llm_provider = %s, 
                system_prompt = %s, 
                color_theme = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """
        
        await db.execute_update(
            sql,
            (
                assistant_data.name,
                assistant_data.description,
                kb_ids_str,
                assistant_data.embedding_model,
                assistant_data.llm_model,
                assistant_data.llm_provider,
                assistant_data.system_prompt,
                assistant_data.color_theme,
                assistant_id
            )
        )
        
        # 5. 返回更新后的助手信息
        return await get_assistant(assistant_id, db)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新助手失败: {str(e)}")


@router.delete("/{assistant_id}")
async def delete_assistant(assistant_id: int, db: DatabaseManager = Depends(get_database)):
    """彻底删除助手(包括数据库记录和关联对话)"""
    try:
        # 检查助手是否存在
        sql = "SELECT name FROM assistants WHERE id = %s"
        result = await db.execute_query(sql, (assistant_id,))
        
        if not result:
            raise HTTPException(status_code=404, detail="助手不存在")
        
        assistant_name = result[0]['name']
        logger.info(f"开始彻底删除助手: id={assistant_id}, name={assistant_name}")
        
        # 1. 删除关联的对话消息
        sql = "DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE assistant_id = %s)"
        await db.execute_update(sql, (assistant_id,))
        logger.info(f"✓ 关联消息已删除")
        
        # 2. 删除关联的对话
        sql = "DELETE FROM conversations WHERE assistant_id = %s"
        await db.execute_update(sql, (assistant_id,))
        logger.info(f"✓ 关联对话已删除")
        
        # 3. 删除助手记录
        sql = "DELETE FROM assistants WHERE id = %s"
        await db.execute_update(sql, (assistant_id,))
        logger.info(f"✓ 助手记录已删除")
        
        logger.info(f"助手彻底删除完成: {assistant_name}")
        return {"message": f"助手 '{assistant_name}' 已彻底删除(包括所有对话记录)"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除助手失败: {str(e)}")


# ==================== 模型管理 ====================

@router.get("/models/llm", response_model=dict)
async def get_llm_models():
    """获取所有LLM模型(本地+远程)"""
    return model_scanner.get_all_llm_models()


@router.get("/models/embedding", response_model=List[ModelInfo])
async def get_embedding_models():
    """获取所有Embedding模型"""
    models = model_scanner.get_all_embedding_models()
    return [ModelInfo(**m) for m in models]
