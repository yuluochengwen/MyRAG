"""智能助手对话服务"""
from typing import List, Dict, Any, Optional, AsyncGenerator
from app.services.knowledge_base_service import KnowledgeBaseService
from app.core.database import DatabaseManager
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ChatService:
    """智能助手对话服务 - RAG对话实现"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.kb_service = KnowledgeBaseService(db_manager)
    
    # ==================== 公共方法 ====================
    
    def _build_context(self, search_results: List[Dict]) -> str:
        """
        构建LLM上下文
        
        Args:
            search_results: 检索结果列表
            
        Returns:
            格式化的上下文字符串
        """
        context_parts = []
        for i, result in enumerate(search_results, 1):
            context_parts.append(
                f"[文档{i}] (相似度: {result['similarity']:.2%})\n"
                f"{result['content']}\n"
            )
        return "\n".join(context_parts)
    
    def _build_user_message(
        self,
        query: str,
        context: Optional[str],
        history_messages: Optional[List[Dict[str, str]]]
    ) -> str:
        """
        构建用户消息（统一的Prompt构建逻辑）
        
        Args:
            query: 用户问题
            context: 检索到的上下文
            history_messages: 历史消息列表
            
        Returns:
            构建好的用户消息
        """
        if context:
            # RAG模式：结合历史对话和检索上下文
            if history_messages and len(history_messages) > 0:
                # 提取历史对话摘要
                history_summary = "\n".join([
                    f"{msg['role']}: {msg['content'][:100]}..." if len(msg['content']) > 100 
                    else f"{msg['role']}: {msg['content']}"
                    for msg in history_messages[-4:]  # 最近2轮对话
                ])
                
                # 有历史对话：强制历史约定优先
                return f"""‼️【重要】我们之前的对话约定：
{history_summary}

---

现在有以下参考资料：
{context}

---

问题：{query}

‼️【回答规则 - 强制执行】：
1. 如果我之前明确告诉你某个规则或答案（例如"记住1+1=3"），你必须严格按照我说的回答，即使与常识不同
2. 对话历史中的约定拥有最高优先级，绝对高于参考资料
3. 只有当对话历史完全没有相关信息时，才使用参考资料
4. 直接给出答案，不要解释你的推理过程

回答："""
            else:
                # 无历史对话：标准RAG模式
                return f"""基于以下上下文回答问题。如果上下文中没有相关信息，请说"我不知道"。

上下文：
{context}

问题：{query}

回答："""
        else:
            # 纯对话模式
            return query
    
    def _build_messages(
        self,
        user_message: str,
        history_messages: Optional[List[Dict[str, str]]],
        system_prompt: Optional[str]
    ) -> List[Dict[str, str]]:
        """
        构建完整的消息列表（统一的消息构建逻辑）
        
        Args:
            user_message: 当前用户消息
            history_messages: 历史消息列表
            system_prompt: 系统提示词
            
        Returns:
            完整的消息列表
        """
        messages = []
        
        # 1. System prompt（有历史时增强）
        if history_messages and len(history_messages) > 0:
            enhanced_system_prompt = f"""{system_prompt if system_prompt else '你是一个智能助手。'}

【核心规则】你必须记住我们之前的对话内容和约定，并在回答时优先遵循对话历史中的信息。如果我之前告诉你某个特定的规则或事实（即使它与常识不同），你必须按照我说的来回答。"""
            messages.append({"role": "system", "content": enhanced_system_prompt})
        elif system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # 2. 历史消息
        if history_messages:
            for msg in history_messages:
                messages.append({"role": msg['role'], "content": msg['content']})
            logger.info(f"历史消息详情: {[{'role': m['role'], 'content': m['content'][:50] + '...'} for m in history_messages]}")
        
        # 3. 当前用户消息
        messages.append({"role": "user", "content": user_message})
        
        return messages
    
    async def _release_embedding_memory(self):
        """释放embedding模型显存"""
        try:
            from app.services.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            embedding_service.unload_model()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("已释放embedding模型显存")
        except Exception as e:
            logger.warning(f"释放embedding显存失败: {e}")
    
    # ==================== 主要对话方法 ====================
    
    async def chat_with_assistant(
        self,
        kb_ids: Optional[List[int]],
        query: str,
        history_messages: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
        top_k: int = 5,
        llm_model: Optional[str] = None,
        llm_provider: str = "local",
        temperature: float = 0.7,
        use_hybrid_retrieval: bool = False
    ) -> Dict[str, Any]:
        """
        智能助手对话（支持多知识库 + 上下文记忆 + 混合检索）
        
        Args:
            kb_ids: 知识库ID列表（None表示纯对话模式）
            query: 用户问题
            history_messages: 历史消息列表 [{"role": "user", "content": "..."}, ...]
            system_prompt: 系统提示词
            top_k: 检索文档数量
            llm_model: LLM模型名称
            llm_provider: LLM提供方
            temperature: 生成温度
            use_hybrid_retrieval: 是否使用混合检索（向量+图谱）
            
        Returns:
            对话结果
        """
        try:
            embedding_model = None
            search_results = []
            retrieval_method = "none"
            
            # 1. 如果指定了知识库，进行检索
            if kb_ids and len(kb_ids) > 0:
                # 获取第一个知识库信息
                kb = await self.kb_service.get_knowledge_base(kb_ids[0])
                if kb:
                    embedding_model = kb.embedding_model
                
                # 判断使用哪种检索方式
                if use_hybrid_retrieval:
                    # 混合检索（向量+图谱）
                    logger.info(f"开始混合检索: kb_ids={kb_ids}, query='{query}'")
                    retrieval_method = "hybrid"
                    search_results = await self._hybrid_search(
                        kb_ids=kb_ids,
                        query=query,
                        top_k=top_k
                    )
                else:
                    # 纯向量检索
                    logger.info(f"开始向量检索: kb_ids={kb_ids}, query='{query}'")
                    retrieval_method = "vector"
                    search_results = await self.kb_service.search_knowledge_bases(
                        kb_ids=kb_ids,
                        query=query,
                        top_k=top_k,
                        score_threshold=0.2
                    )
            else:
                logger.info(f"纯对话模式: query='{query}'")
            
            # 2. 如果没有检索到结果但有知识库
            if kb_ids and not search_results:
                logger.warning(f"未检索到相关文档: kb_ids={kb_ids}, query='{query}'")
                return {
                    'answer': '抱歉，我在知识库中没有找到相关信息。请尝试换个问法或检查知识库内容。',
                    'sources': [],
                    'embedding_model': embedding_model,
                    'retrieval_count': 0,
                    'retrieval_method': retrieval_method
                }
            
            # 3. 构建上下文
            context = self._build_context(search_results) if search_results else None
            
            # 4. 释放embedding模型显存（为LLM腾出空间）
            if search_results:
                await self._release_embedding_memory()
            
            # 5. 调用LLM生成回答（传递历史消息）
            answer = await self._generate_answer(
                query=query,
                context=context,
                history_messages=history_messages,
                system_prompt=system_prompt,
                llm_model=llm_model,
                llm_provider=llm_provider,
                temperature=temperature
            )
            
            # 6. 返回结果
            return {
                'answer': answer,
                'sources': [
                    {
                        'content': r['content'][:200] + ('...' if len(r['content']) > 200 else ''),
                        'similarity': r.get('similarity', r.get('score', 0)),
                        'file_id': r.get('metadata', {}).get('file_id'),
                        'source': r.get('source', 'unknown')
                    }
                    for r in search_results[:3]  # 只返回前3个来源
                ],
                'embedding_model': embedding_model,
                'retrieval_count': len(search_results)
            }
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"智能助手对话失败: {str(e)}")
            raise
    
    async def chat(
        self,
        kb_id: int,
        query: str,
        top_k: int = 5,
        llm_model: Optional[str] = None,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        单知识库RAG对话（向后兼容）
        
        Args:
            kb_id: 知识库ID
            query: 用户问题
            top_k: 检索文档数量
            llm_model: LLM模型名称
            temperature: 生成温度
            
        Returns:
            对话结果
        """
        return await self.chat_with_assistant(
            kb_ids=[kb_id],
            query=query,
            top_k=top_k,
            llm_model=llm_model,
            temperature=temperature
        )
    
    async def _generate_answer(
        self,
        query: str,
        context: Optional[str],
        history_messages: Optional[List[Dict[str, str]]],
        system_prompt: Optional[str],
        llm_model: Optional[str],
        llm_provider: str,
        temperature: float
    ) -> str:
        """
        调用LLM生成回答（支持上下文记忆）
        
        Args:
            query: 用户问题
            context: 检索到的上下文(None表示纯对话)
            history_messages: 历史消息列表
            system_prompt: 系统提示词
            llm_model: LLM模型名称
            llm_provider: LLM提供方
            temperature: 生成温度
            
        Returns:
            生成的回答
        """
        # 构建用户消息
        user_message = self._build_user_message(query, context, history_messages)
        
        # 构建完整消息列表
        messages = self._build_messages(user_message, history_messages, system_prompt)
        
        # 根据provider调用不同的LLM
        try:
            if llm_provider in ['local', 'transformers']:
                # 调用Transformers本地推理（使用延迟加载）
                from app.services.transformers_service import get_transformers_service
                transformers_service = get_transformers_service()
                
                model_name = llm_model if llm_model else 'Qwen3-8B'
                logger.info(f"调用Transformers模型: {model_name}, 历史消息: {len(history_messages) if history_messages else 0}条, 完整messages数量: {len(messages)}")
                
                return await transformers_service.chat(
                    model=model_name,
                    messages=messages,
                    temperature=temperature
                )
            
            elif llm_provider == 'openai':
                # TODO: 调用OpenAI
                logger.error("OpenAI集成尚未实现")
                raise NotImplementedError("OpenAI集成尚未实现，请使用本地模型(transformers)")
            
            elif llm_provider == 'ollama':
                # 调用Ollama服务
                from app.services.ollama_llm_service import get_ollama_llm_service
                ollama_service = get_ollama_llm_service()
                
                model_name = llm_model if llm_model else 'qwen2.5:7b'
                logger.info(f"调用Ollama模型: {model_name}, 历史消息: {len(history_messages) if history_messages else 0}条, 完整messages数量: {len(messages)}")
                
                return await ollama_service.chat(
                    model=model_name,
                    messages=messages,
                    temperature=temperature
                )
            
            else:
                logger.error(f"未知的LLM提供方: {llm_provider}")
                raise ValueError(f"不支持的LLM提供方: {llm_provider}，仅支持: local, transformers, ollama")
        
        except Exception as e:
            logger.error(f"LLM调用失败: {str(e)}")
            # LLM调用失败时，抛出异常而不是返回模拟回答，让用户知道真实错误
            raise RuntimeError(f"模型生成失败: {str(e)}")
    
    async def chat_stream(
        self,
        kb_ids: Optional[List[int]],
        query: str,
        history_messages: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
        top_k: int = 5,
        llm_model: Optional[str] = None,
        llm_provider: str = "local",
        temperature: float = 0.7,
        use_hybrid_retrieval: bool = False
    ):
        """
        智能助手流式对话（支持上下文记忆）
        
        Args:
            kb_ids: 知识库ID列表（None表示纯对话模式）
            query: 用户问题
            history_messages: 历史消息列表
            system_prompt: 系统提示词
            top_k: 检索文档数量
            llm_model: LLM模型名称
            llm_provider: LLM提供方
            temperature: 生成温度
            use_hybrid_retrieval: 是否使用混合检索（向量+图谱）
            
        Yields:
            dict: 流式响应片段 {"type": "text|sources|done", "data": ...}
        """
        try:
            embedding_model = None
            search_results = []
            
            # 1. 如果指定了知识库，进行RAG检索
            if kb_ids and len(kb_ids) > 0:
                logger.info(f"开始多知识库RAG对话（流式）: kb_ids={kb_ids}, query='{query}', hybrid={use_hybrid_retrieval}")
                
                # 判断使用哪种检索方式
                if use_hybrid_retrieval:
                    # 混合检索（向量+图谱）
                    search_results = await self._hybrid_search(
                        kb_ids=kb_ids,
                        query=query,
                        top_k=top_k
                    )
                else:
                    # 纯向量检索
                    search_results = await self.kb_service.search_knowledge_bases(
                        kb_ids=kb_ids,
                        query=query,
                        top_k=top_k,
                        score_threshold=0.2
                    )
                
                kb = await self.kb_service.get_knowledge_base(kb_ids[0])
                if kb:
                    embedding_model = kb.embedding_model
            else:
                logger.info(f"纯对话模式（流式）: query='{query}'")
            
            # 2. 发送检索结果（如果有）
            if search_results:
                sources = [
                    {
                        'content': r['content'][:200] + ('...' if len(r['content']) > 200 else ''),
                        'similarity': r.get('similarity', r.get('score', r.get('final_score', 0))),
                        'file_id': r.get('metadata', {}).get('file_id'),
                        'source': r.get('source', 'unknown'),
                        'metadata': r.get('metadata', {})
                    }
                    for r in search_results[:5]  # 返回前5个来源（包含图谱）
                ]
                yield {
                    "type": "sources",
                    "data": {
                        "sources": sources,
                        "retrieval_count": len(search_results),
                        "embedding_model": embedding_model
                    }
                }
            
            # 3. 构建上下文
            context = self._build_context(search_results) if search_results else None
            
            # 4. 释放embedding模型显存
            if search_results:
                await self._release_embedding_memory()
            
            # 5. 流式调用LLM生成回答（传递历史消息）
            async for text_chunk in self._generate_answer_stream(
                query=query,
                context=context,
                history_messages=history_messages,
                system_prompt=system_prompt,
                llm_model=llm_model,
                llm_provider=llm_provider,
                temperature=temperature
            ):
                yield {
                    "type": "text",
                    "data": text_chunk
                }
            
            # 6. 发送完成信号
            yield {
                "type": "done",
                "data": {}
            }
            
        except Exception as e:
            logger.error(f"流式对话失败: {str(e)}")
            yield {
                "type": "error",
                "data": {"error": str(e)}
            }
    
    async def _generate_answer_stream(
        self,
        query: str,
        context: Optional[str],
        history_messages: Optional[List[Dict[str, str]]],
        system_prompt: Optional[str],
        llm_model: Optional[str],
        llm_provider: str,
        temperature: float
    ) -> AsyncGenerator[str, None]:
        """
        流式调用LLM生成回答（支持上下文记忆）
        
        Yields:
            str: 生成的文本片段
        """
        # 构建用户消息（复用公共方法）
        user_message = self._build_user_message(query, context, history_messages)
        
        # 构建完整消息列表（复用公共方法）
        messages = self._build_messages(user_message, history_messages, system_prompt)
        
        try:
            if llm_provider in ['local', 'transformers']:
                # 使用延迟加载获取transformers_service
                from app.services.transformers_service import get_transformers_service
                transformers_service = get_transformers_service()
                
                model_name = llm_model if llm_model else 'Qwen3-8B'
                logger.info(f"调用Transformers模型（流式）: {model_name}, 历史消息: {len(history_messages) if history_messages else 0}条, 完整messages数量: {len(messages)}")
                
                async for text_chunk in await transformers_service.chat(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    stream=True
                ):
                    yield text_chunk
            
            elif llm_provider == 'openai':
                raise NotImplementedError("OpenAI流式集成尚未实现")
            
            elif llm_provider == 'ollama':
                # 调用Ollama服务（流式）
                from app.services.ollama_llm_service import get_ollama_llm_service
                ollama_service = get_ollama_llm_service()
                
                model_name = llm_model if llm_model else 'qwen2.5:7b'
                logger.info(f"调用Ollama模型（流式）: {model_name}, 历史消息: {len(history_messages) if history_messages else 0}条, 完整messages数量: {len(messages)}")
                
                async for text_chunk in ollama_service.chat_stream(
                    model=model_name,
                    messages=messages,
                    temperature=temperature
                ):
                    yield text_chunk
            
            else:
                raise ValueError(f"不支持的LLM提供方: {llm_provider}")
            
        except Exception as e:
            logger.error(f"流式对话失败: {str(e)}")
            yield f"[错误] {str(e)}"
    
    # ==================== 混合检索方法 ====================
    
    async def _hybrid_search(
        self,
        kb_ids: List[int],
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        混合检索（向量+图谱）
        
        Args:
            kb_ids: 知识库ID列表
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            检索结果列表
        """
        try:
            from app.services.hybrid_retrieval_service import get_hybrid_retrieval_service
            from app.core.config import settings
            
            # 检查是否启用知识图谱
            if not settings.knowledge_graph.enabled:
                logger.warning("知识图谱未启用，降级为纯向量检索")
                return await self.kb_service.search_knowledge_bases(
                    kb_ids=kb_ids,
                    query=query,
                    top_k=top_k,
                    score_threshold=0.2
                )
            
            hybrid_service = get_hybrid_retrieval_service()
            
            # 如果有多个知识库，对每个库分别检索后合并
            all_results = []
            
            for kb_id in kb_ids:
                results = await hybrid_service.hybrid_search(
                    kb_id=kb_id,
                    query=query,
                    top_k=top_k,
                    enable_graph=True
                )
                all_results.extend(results)
            
            # 按最终分数排序并返回top_k
            all_results.sort(key=lambda x: x.get('final_score', x.get('score', 0)), reverse=True)
            
            # 格式化为标准检索结果格式
            formatted_results = []
            for result in all_results[:top_k]:
                formatted_results.append({
                    'content': result['content'],
                    'similarity': result.get('final_score', result.get('score', 0)),
                    'metadata': result.get('metadata', {}),
                    'source': result.get('source', 'unknown'),
                    'chunk_id': result.get('chunk_id')
                })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"混合检索失败，降级为向量检索: {str(e)}")
            # 降级为纯向量检索
            return await self.kb_service.search_knowledge_bases(
                kb_ids=kb_ids,
                query=query,
                top_k=top_k,
                score_threshold=0.2
            )

