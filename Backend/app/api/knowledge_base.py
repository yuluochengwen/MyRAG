"""知识库API路由"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, BackgroundTasks, Query
from app.models.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    FileUploadResponse,
    MessageResponse,
    SearchRequest,
    SearchResponse
)
from app.services import KnowledgeBaseService, FileService, EmbeddingService, VectorStoreService, MetadataService
from app.core.dependencies import (
    get_kb_service,
    get_file_service,
    get_embedding_service,
    get_vector_store_service
)
from app.core.config import settings
from app.core.database import db_manager
from app.websocket.manager import ws_manager
from app.utils.logger import get_logger
from app.utils.validators import validate_kb_name, validate_file_extension
from app.utils.text_splitter import TextSplitter

logger = get_logger(__name__)
router = APIRouter(prefix="/api/knowledge-bases", tags=["知识库"])


@router.post("", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    kb_data: KnowledgeBaseCreate,
    kb_service: KnowledgeBaseService = Depends(get_kb_service)
):
    """创建知识库"""
    try:
        # 验证名称
        validate_kb_name(kb_data.name)
        
        # 检查是否已存在
        existing = await kb_service.get_kb_by_name(kb_data.name)
        if existing:
            raise HTTPException(status_code=400, detail="知识库名称已存在")
        
        # 创建知识库
        kb = await kb_service.create_knowledge_base(
            name=kb_data.name,
            description=kb_data.description,
            embedding_model=kb_data.embedding_model,
            embedding_provider=kb_data.embedding_provider
        )
        
        if not kb:
            raise HTTPException(status_code=500, detail="创建知识库失败")
        
        # 创建元数据文件
        metadata_service = MetadataService(settings.file.upload_dir)
        metadata_service.create_metadata(kb.id, {
            "name": kb.name,
            "description": kb.description,
            "embedding_model": kb.embedding_model,
            "embedding_provider": kb.embedding_provider,
            "created_at": kb.created_at.isoformat() if kb.created_at else None
        })
        
        return KnowledgeBaseResponse.from_model(kb)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[KnowledgeBaseResponse])
async def list_knowledge_bases(
    skip: int = 0,
    limit: int = 100,
    kb_service: KnowledgeBaseService = Depends(get_kb_service)
):
    """获取知识库列表"""
    try:
        kbs = await kb_service.list_knowledge_bases(skip=skip, limit=limit)
        return [KnowledgeBaseResponse.from_model(kb) for kb in kbs]
        
    except Exception as e:
        logger.error(f"获取知识库列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: int,
    kb_service: KnowledgeBaseService = Depends(get_kb_service)
):
    """获取知识库详情"""
    try:
        kb = await kb_service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        return KnowledgeBaseResponse.from_model(kb)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{kb_id}", response_model=MessageResponse)
async def delete_knowledge_base(
    kb_id: int,
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    vector_store: VectorStoreService = Depends(get_vector_store_service)
):
    """删除知识库"""
    try:
        # 检查是否存在
        kb = await kb_service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 删除向量集合
        collection_name = f"kb_{kb_id}"
        try:
            vector_store.delete_collection(collection_name)
        except Exception as e:
            logger.warning(f"删除向量集合失败: {str(e)}")
        
        # 删除元数据文件
        metadata_service = MetadataService(settings.file.upload_dir)
        metadata_service.delete_metadata(kb_id)
        
        # 删除知识库
        success = await kb_service.delete_knowledge_base(kb_id)
        if not success:
            raise HTTPException(status_code=500, detail="删除知识库失败")
        
        return MessageResponse(message=f"知识库 {kb.name} 删除成功")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_file_background(
    file_id: int,
    kb_id: int,
    client_id: str,
    file_service: FileService,
    embedding_service: EmbeddingService,
    vector_store: VectorStoreService,
    kb_service: KnowledgeBaseService,
    embedding_model: str,
    embedding_provider: str = "transformers"
):
    """后台处理文件"""
    try:
        # 1. 解析文件
        await ws_manager.send_progress(
            client_id, kb_id, "parsing", 10, "正在解析文件..."
        )
        
        content = await file_service.parse_file(file_id)
        
        # 2. 文本分块
        await ws_manager.send_progress(
            client_id, kb_id, "chunking", 30, "正在分块文本..."
        )
        
        # 根据配置选择分割策略
        semantic_config = settings.text_processing.semantic_split
        
        if semantic_config.enabled and semantic_config.use_for_short_text and len(content) < semantic_config.short_text_threshold:
            # 短文本使用LLM语义分割
            from app.utils.semantic_splitter import get_semantic_splitter
            splitter = get_semantic_splitter()
            chunks = splitter.split_text(content, use_llm=True)
            logger.info(f"使用LLM语义分割: file_id={file_id}, content_len={len(content)}, chunks={len(chunks)}")
        elif semantic_config.enabled:
            # 长文本使用快速规则分割
            from app.utils.semantic_splitter import get_semantic_splitter
            splitter = get_semantic_splitter()
            chunks = splitter.split_text(content, use_llm=False)
            logger.info(f"使用规则分割（文本过长）: file_id={file_id}, content_len={len(content)}, chunks={len(chunks)}")
        else:
            # 禁用语义分割，使用传统TextSplitter
            splitter = TextSplitter()
            chunks = splitter.split_text(content)
            logger.info(f"使用传统分割: file_id={file_id}, chunks={len(chunks)}")
        
        # 3. 生成向量
        await ws_manager.send_progress(
            client_id, kb_id, "embedding", 50, f"正在生成向量 (共{len(chunks)}块, provider={embedding_provider})..."
        )
        
        embeddings = embedding_service.encode(
            chunks,
            embedding_model,
            provider=embedding_provider,
            batch_size=32,
            show_progress=False
        )
        
        # 4. 存储向量
        await ws_manager.send_progress(
            client_id, kb_id, "storing", 80, "正在存储向量..."
        )
        
        collection_name = f"kb_{kb_id}"
        ids = [f"file_{file_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                'kb_id': kb_id,
                'file_id': file_id,
                'chunk_index': i
            }
            for i in range(len(chunks))
        ]
        
        vector_store.add_vectors(
            collection_name=collection_name,
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )
        
        # 4.5 保存文本块到MySQL数据库
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            for i, chunk in enumerate(chunks):
                cursor.execute(
                    """INSERT INTO text_chunks (kb_id, file_id, chunk_index, content, vector_id)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (kb_id, file_id, i, chunk, ids[i])
                )
            cursor.close()
        
        # 5. 更新文件分块数量
        await file_service.update_chunk_count(file_id, len(chunks))
        
        # 6. 更新文件状态为completed (同时设置processed_at)
        await file_service.update_file_status(file_id, 'completed')
        
        # 7. 更新知识库统计
        await kb_service.update_stats(kb_id)
        
        # 8. 更新元数据文件
        kb = await kb_service.get_knowledge_base(kb_id)
        if kb:
            metadata_service = MetadataService(settings.file.upload_dir)
            metadata_service.update_metadata(kb_id, {
                "total_files": kb.file_count,
                "total_chunks": kb.chunk_count
            })
        
        # 9. 发送完成消息
        await ws_manager.send_complete(
            client_id,
            kb_id,
            "文件处理完成",
            file_id=file_id,
            chunk_count=len(chunks)
        )
        
    except Exception as e:
        logger.error(f"文件处理失败: {str(e)}")
        await file_service.update_file_status(file_id, 'error', str(e))
        await ws_manager.send_error(client_id, kb_id, "文件处理失败", str(e))


@router.post("/{kb_id}/upload", response_model=FileUploadResponse)
async def upload_file(
    kb_id: int,
    client_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = FastAPIFile(...),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    file_service: FileService = Depends(get_file_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_store: VectorStoreService = Depends(get_vector_store_service)
):
    """上传文件到知识库"""
    try:
        # 检查知识库是否存在
        kb = await kb_service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 验证文件扩展名
        file_type = validate_file_extension(file.filename)
        
        # 保存文件
        file_obj = await file_service.save_file(
            file.file,
            file.filename,
            kb_id,
            file_type
        )
        
        if not file_obj:
            raise HTTPException(status_code=500, detail="文件保存失败")
        
        # 添加后台任务处理文件
        background_tasks.add_task(
            process_file_background,
            file_obj.id,
            kb_id,
            client_id,
            file_service,
            embedding_service,
            vector_store,
            kb_service,
            kb.embedding_model,
            kb.embedding_provider
        )
        
        return FileUploadResponse(
            id=file_obj.id,
            filename=file_obj.filename,
            file_type=file_obj.file_type,
            file_size=file_obj.file_size,
            status=file_obj.status
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/files", response_model=List[FileUploadResponse])
async def list_files(
    kb_id: int,
    file_service: FileService = Depends(get_file_service)
):
    """获取知识库的文件列表"""
    try:
        files = await file_service.list_files(kb_id)
        
        return [
            FileUploadResponse(
                id=f.id,
                filename=f.filename,
                file_type=f.file_type,
                file_size=f.file_size,
                status=f.status
            )
            for f in files
        ]
        
    except Exception as e:
        logger.error(f"获取文件列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/files/{file_id}/content")
async def get_file_content(
    kb_id: int,
    file_id: int,
    file_service: FileService = Depends(get_file_service)
):
    """获取文件的原始内容"""
    try:
        # 验证文件属于该知识库
        file = await file_service.get_file(file_id)
        if not file or file.kb_id != kb_id:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 读取文件内容
        import os
        file_path = file.storage_path
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="文件不存在于存储系统")
        
        # 根据文件类型读取内容
        from app.utils.file_parser import FileParser
        content = FileParser.parse(file_path)
        
        return {
            "file_id": file_id,
            "filename": file.filename,
            "file_type": file.file_type,
            "file_size": file.file_size,
            "content": content,
            "chunk_count": file.chunk_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件内容失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{kb_id}/files/{file_id}", response_model=MessageResponse)
async def delete_file(
    kb_id: int,
    file_id: int,
    file_service: FileService = Depends(get_file_service),
    vector_store: VectorStoreService = Depends(get_vector_store_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service)
):
    """删除知识库中的文件"""
    try:
        # 验证文件属于该知识库
        file = await file_service.get_file(file_id)
        if not file or file.kb_id != kb_id:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 从向量数据库中删除该文件的所有chunks
        collection_name = f"kb_{kb_id}"
        try:
            # 查询该文件的所有chunk的vector_id
            chunk_ids = await db_manager.execute_query(
                "SELECT vector_id FROM text_chunks WHERE file_id = %s",
                (file_id,)
            )
            
            if chunk_ids:
                vector_ids = [row['vector_id'] for row in chunk_ids]
                vector_store.delete_by_ids(collection_name, vector_ids)
                logger.info(f"已从向量数据库删除文件向量: file_id={file_id}, count={len(vector_ids)}")
        except Exception as e:
            logger.warning(f"删除向量时出错: {str(e)}")
        
        # 删除数据库中的text_chunks记录（会被外键级联删除，但为了确保可以手动删除）
        try:
            await db_manager.execute_update(
                "DELETE FROM text_chunks WHERE file_id = %s",
                (file_id,)
            )
        except Exception as e:
            logger.warning(f"删除text_chunks记录时出错: {str(e)}")
        
        # 删除文件记录和磁盘文件
        success = await file_service.delete_file(file_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="文件删除失败")
        
        # 更新知识库统计信息
        try:
            await kb_service.update_stats(kb_id)
            logger.info(f"已更新知识库统计信息: kb_id={kb_id}")
        except Exception as e:
            logger.warning(f"更新知识库统计信息失败: {str(e)}")
        
        logger.info(f"文件删除成功: kb_id={kb_id}, file_id={file_id}, filename={file.filename}")
        return MessageResponse(message=f"文件 '{file.filename}' 删除成功")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/chunks")
async def list_chunks(kb_id: int):
    """获取知识库的文本块列表"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 验证知识库是否存在
            cursor.execute("SELECT id FROM knowledge_bases WHERE id = %s", (kb_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="知识库不存在")
            
            # 获取文本块列表（带文件名信息）
            cursor.execute(
                """SELECT tc.id, tc.file_id, tc.chunk_index, tc.content, tc.created_at,
                          f.filename, f.file_type
                   FROM text_chunks tc
                   JOIN files f ON tc.file_id = f.id
                   WHERE tc.kb_id = %s
                   ORDER BY f.filename, tc.chunk_index""",
                (kb_id,)
            )
            chunks = cursor.fetchall()
            cursor.close()
            
            return {
                "kb_id": kb_id,
                "total": len(chunks),
                "chunks": chunks
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文本块列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_id}/search", response_model=SearchResponse)
async def search_knowledge_base(
    kb_id: int,
    request: SearchRequest,
    kb_service: KnowledgeBaseService = Depends(get_kb_service)
):
    """
    检索知识库
    
    自动使用知识库对应的嵌入模型进行查询向量化，
    确保查询向量与存储向量的维度一致。
    """
    try:
        # 执行检索
        results = await kb_service.search_knowledge_base(
            kb_id=kb_id,
            query=request.query,
            top_k=request.top_k or 5,
            score_threshold=request.score_threshold or 0.0
        )
        
        # 获取知识库信息
        kb = await kb_service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        return SearchResponse(
            kb_id=kb_id,
            kb_name=kb.name,
            embedding_model=kb.embedding_model,
            query=request.query,
            results=results,
            total=len(results)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"检索失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/embedding/models")
async def list_embedding_models(
    provider: Optional[str] = Query(None, description="过滤特定provider的模型: transformers, ollama"),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    """
    获取可用的嵌入模型列表
    
    支持provider参数过滤：
    - provider=transformers: 只返回Transformers模型
    - provider=ollama: 只返回Ollama模型
    - 不传provider: 返回所有provider的模型
    """
    try:
        models = embedding_service.list_available_models(provider=provider)
        
        return {
            "provider_filter": provider,
            "total": len(models),
            "models": models
        }
        
    except Exception as e:
        logger.error(f"获取嵌入模型列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
