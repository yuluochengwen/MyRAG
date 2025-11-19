"""基于LLM语义边界检测的文本分割器"""
from typing import List, Dict, Any, Optional
import re
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SemanticTextSplitter:
    """
    基于Ollama LLM的语义边界检测文本分割器
    
    特性:
    - 使用LLM识别自然语义边界（段落、主题转换）
    - 适合中短文本（<10000字符）
    - 保持语义完整性
    - 支持批量处理
    """
    
    def __init__(
        self,
        max_chunk_size: int = None,
        min_chunk_size: int = None,
        ollama_model: str = None
    ):
        """
        初始化语义分割器
        
        Args:
            max_chunk_size: 最大块大小（字符数），None则从配置读取
            min_chunk_size: 最小块大小（避免过碎），None则从配置读取
            ollama_model: 使用的Ollama模型，None则从配置读取
        """
        # 从配置读取参数
        semantic_config = settings.text_processing.semantic_split
        
        self.max_chunk_size = max_chunk_size or semantic_config.max_chunk_size
        self.min_chunk_size = min_chunk_size or semantic_config.min_chunk_size
        self.ollama_model = ollama_model or semantic_config.ollama_model
        
        logger.info(f"语义分割器初始化: max_size={self.max_chunk_size}, "
                   f"min_size={self.min_chunk_size}, model={self.ollama_model}")
    
    def split_text(self, text: str, use_llm: bool = True) -> List[str]:
        """
        智能分割文本
        
        Args:
            text: 待分割文本
            use_llm: 是否使用LLM检测语义边界（False时使用快速规则）
            
        Returns:
            分割后的文本块列表
        """
        if not text or len(text) == 0:
            return []
        
        # 短文本直接返回
        if len(text) <= self.max_chunk_size:
            return [text]
        
        # 根据选项选择分割策略
        if use_llm:
            return self._llm_split(text)
        else:
            return self._rule_based_split(text)
    
    def _llm_split(self, text: str) -> List[str]:
        """
        使用LLM进行语义边界检测分割
        
        策略:
        1. 先用规则粗分（按段落）
        2. LLM判断是否可以合并相邻段落
        3. 确保chunk大小在合理范围
        """
        try:
            # 第一步：按段落粗分
            paragraphs = self._split_by_paragraphs(text)
            
            if len(paragraphs) == 0:
                return self._rule_based_split(text)
            
            # 第二步：使用LLM智能合并
            chunks = self._merge_with_llm(paragraphs)
            
            # 第三步：后处理（处理过长/过短chunk）
            chunks = self._post_process_chunks(chunks)
            
            logger.info(f"LLM语义分割完成: 原文={len(text)}字符, "
                       f"段落={len(paragraphs)}, 最终块={len(chunks)}")
            
            return chunks
            
        except Exception as e:
            logger.error(f"LLM分割失败，降级为规则分割: {str(e)}")
            return self._rule_based_split(text)
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """按段落分割（第一步粗分）"""
        # 按双换行或明显段落标志分割
        paragraphs = re.split(r'\n\n+|\n(?=[一二三四五六七八九十]、)|\n(?=\d+\.)|\n(?=[A-Z]\.)', text)
        
        # 清理并过滤
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        return paragraphs
    
    def _merge_with_llm(self, paragraphs: List[str]) -> List[str]:
        """
        使用LLM判断段落是否应该合并
        
        思路:
        - 遍历相邻段落对
        - 询问LLM: "这两个段落讨论的是同一主题吗？"
        - 如果是，且合并后不超过max_size，则合并
        """
        from app.services.ollama_llm_service import get_ollama_llm_service
        
        try:
            ollama_service = get_ollama_llm_service()
            
            if not ollama_service.is_available():
                logger.warning("Ollama服务不可用，使用规则合并")
                return self._rule_based_merge(paragraphs)
            
            chunks = []
            current_chunk = paragraphs[0] if paragraphs else ""
            
            for i in range(1, len(paragraphs)):
                next_para = paragraphs[i]
                
                # 如果合并后会超过max_size，直接分开
                if len(current_chunk) + len(next_para) > self.max_chunk_size:
                    chunks.append(current_chunk)
                    current_chunk = next_para
                    continue
                
                # 如果当前chunk已经足够大，也分开
                if len(current_chunk) >= self.min_chunk_size * 2:
                    # 使用LLM判断是否语义相关
                    should_merge = self._ask_llm_should_merge(
                        ollama_service,
                        current_chunk[-200:],  # 只取尾部200字符
                        next_para[:200]         # 只取开头200字符
                    )
                    
                    if not should_merge:
                        chunks.append(current_chunk)
                        current_chunk = next_para
                        continue
                
                # 默认合并
                current_chunk = current_chunk + "\n\n" + next_para
            
            # 添加最后一个chunk
            if current_chunk:
                chunks.append(current_chunk)
            
            return chunks
            
        except Exception as e:
            logger.error(f"LLM合并失败: {str(e)}")
            return self._rule_based_merge(paragraphs)
    
    def _ask_llm_should_merge(
        self,
        ollama_service,
        text1_tail: str,
        text2_head: str
    ) -> bool:
        """
        询问LLM两个文本片段是否应该合并
        
        返回True表示语义相关，应该合并
        """
        try:
            import asyncio
            
            prompt = f"""分析以下两个文本片段是否讨论同一主题或具有强相关性。

片段1结尾:
{text1_tail}

片段2开头:
{text2_head}

请只回答"是"或"否"，不要解释。
如果两个片段讨论同一主题或紧密相关，回答"是"；
如果主题转换或相关性弱，回答"否"。

回答:"""

            messages = [{"role": "user", "content": prompt}]
            
            # 同步调用异步函数
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在事件循环中，创建新任务
                future = asyncio.ensure_future(
                    ollama_service.chat(
                        model=self.ollama_model,
                        messages=messages,
                        temperature=0.1  # 低温度确保一致性
                    )
                )
                response = loop.run_until_complete(future)
            else:
                response = loop.run_until_complete(
                    ollama_service.chat(
                        model=self.ollama_model,
                        messages=messages,
                        temperature=0.1
                    )
                )
            
            # 解析回答
            answer = response.strip().lower()
            should_merge = '是' in answer or 'yes' in answer
            
            logger.debug(f"LLM判断结果: {answer} -> merge={should_merge}")
            return should_merge
            
        except Exception as e:
            logger.warning(f"LLM判断失败，默认不合并: {str(e)}")
            return False
    
    def _rule_based_merge(self, paragraphs: List[str]) -> List[str]:
        """
        基于规则的段落合并（LLM不可用时的降级方案）
        
        规则:
        - 段落长度<min_size，尝试与下一段合并
        - 合并后不超过max_size
        """
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            if not current_chunk:
                current_chunk = para
            elif len(current_chunk) + len(para) + 2 <= self.max_chunk_size:
                current_chunk = current_chunk + "\n\n" + para
            else:
                chunks.append(current_chunk)
                current_chunk = para
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _rule_based_split(self, text: str) -> List[str]:
        """
        基于规则的快速分割（完全不使用LLM）
        
        策略:
        1. 优先在段落边界分割
        2. 其次在句子边界分割
        3. 最后按固定长度分割
        """
        paragraphs = self._split_by_paragraphs(text)
        return self._rule_based_merge(paragraphs)
    
    def _post_process_chunks(self, chunks: List[str]) -> List[str]:
        """
        后处理：处理过长或过短的chunk
        
        - 过长chunk（>max_size）：强制分割
        - 过短chunk（<min_size）：尝试与相邻合并
        """
        processed = []
        
        for chunk in chunks:
            if len(chunk) > self.max_chunk_size:
                # 过长，强制分割
                sub_chunks = self._force_split(chunk)
                processed.extend(sub_chunks)
            else:
                processed.append(chunk)
        
        # 处理过短chunk
        final_chunks = []
        i = 0
        while i < len(processed):
            chunk = processed[i]
            
            # 如果过短且不是最后一个，尝试与下一个合并
            if len(chunk) < self.min_chunk_size and i < len(processed) - 1:
                next_chunk = processed[i + 1]
                if len(chunk) + len(next_chunk) <= self.max_chunk_size:
                    final_chunks.append(chunk + "\n\n" + next_chunk)
                    i += 2
                    continue
            
            final_chunks.append(chunk)
            i += 1
        
        return final_chunks
    
    def _force_split(self, text: str) -> List[str]:
        """强制分割过长文本"""
        chunks = []
        sentences = re.split(r'([。！？\.!?]+)', text)
        
        current = ""
        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            punct = sentences[i + 1] if i + 1 < len(sentences) else ""
            full_sentence = sentence + punct
            
            if len(current) + len(full_sentence) > self.max_chunk_size:
                if current:
                    chunks.append(current.strip())
                current = full_sentence
            else:
                current += full_sentence
        
        if current:
            chunks.append(current.strip())
        
        return chunks if chunks else [text]
    
    def split_text_with_metadata(
        self,
        text: str,
        source_file: Optional[str] = None,
        file_type: Optional[str] = None,
        use_llm: bool = True
    ) -> List[Dict[str, Any]]:
        """
        分割文本并添加元数据
        
        Args:
            text: 待分割文本
            source_file: 来源文件
            file_type: 文件类型
            use_llm: 是否使用LLM
            
        Returns:
            包含元数据的chunk列表
        """
        chunks = self.split_text(text, use_llm=use_llm)
        
        result = []
        for i, chunk in enumerate(chunks):
            result.append({
                "content": chunk,
                "metadata": {
                    "chunk_index": i,
                    "chunk_size": len(chunk),
                    "source_file": source_file,
                    "file_type": file_type,
                    "split_method": "llm_semantic" if use_llm else "rule_based"
                }
            })
        
        return result


def get_semantic_splitter() -> SemanticTextSplitter:
    """获取语义分割器单例（参数从配置文件读取）"""
    global _semantic_splitter_instance
    if _semantic_splitter_instance is None:
        # 所有参数从配置文件读取
        _semantic_splitter_instance = SemanticTextSplitter()
    return _semantic_splitter_instance


_semantic_splitter_instance = None
