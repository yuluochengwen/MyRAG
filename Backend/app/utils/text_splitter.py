"""基于 LangChain 的智能文本分割工具"""
from typing import List, Optional, Dict, Any
from langchain.text_splitter import RecursiveCharacterTextSplitter
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TextSplitter:
    """
    基于 LangChain 的智能文本分割器（增强版）
    
    特性：
    - 递归尝试不同分隔符，保持语义完整性
    - 支持中英文混合文本
    - 文档类型感知（PDF/DOCX/HTML/Code）
    - 自动处理重叠部分
    - 支持chunk元数据（为Ollama等扩展预留）
    """
    
    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
        separators: Optional[List[str]] = None,
        document_type: Optional[str] = None
    ):
        """
        初始化文本分割器
        
        Args:
            chunk_size: 块大小（字符数）
            chunk_overlap: 重叠大小（字符数）
            separators: 自定义分隔符列表（可选）
            document_type: 文档类型（pdf/docx/html/code/text），用于优化分隔符
        """
        config = settings.text_processing
        
        self.chunk_size = chunk_size or config.chunk_size
        self.chunk_overlap = chunk_overlap or config.chunk_overlap
        self.document_type = document_type
        
        # 根据文档类型选择分隔符
        if separators:
            self.separators = separators
        else:
            self.separators = self._get_separators_for_type(document_type)
        
        logger.info(f"LangChain 文本分割器初始化: chunk_size={self.chunk_size}, "
                   f"overlap={self.chunk_overlap}, doc_type={document_type}, "
                   f"separators_count={len(self.separators)}")
    
    def _get_separators_for_type(self, doc_type: Optional[str]) -> List[str]:
        """
        根据文档类型返回优化的分隔符列表
        
        Args:
            doc_type: 文档类型（pdf/docx/html/code/text）
        
        Returns:
            分隔符列表（按优先级排序）
        """
        # 默认分隔符（适用于普通文本和已优化的PDF/DOCX）
        default_separators = [
            "\n\n",   # 双换行（段落） - 最高优先级
            "\n",     # 单换行（行）
            "。",      # 中文句号
            "！",      # 中文感叹号
            "？",      # 中文问号
            "；",      # 中文分号
            "，",      # 中文逗号
            ". ",     # 英文句号+空格
            "! ",     # 英文感叹号+空格
            "? ",     # 英文问号+空格
            "; ",     # 英文分号+空格
            ", ",     # 英文逗号+空格
            " ",      # 空格
            "",       # 字符级别（最后手段）
        ]
        
        if doc_type == 'code':
            # 代码文档：优先在函数/类定义处分割
            return [
                "\n\nclass ",     # 类定义
                "\n\ndef ",       # 函数定义
                "\n\nasync def ", # 异步函数
                "\n\n",           # 空行
                "\n",
                " ",
                ""
            ]
        elif doc_type == 'html':
            # HTML文档：优先在块级元素边界分割
            return [
                "\n\n",           # 段落边界
                "\n",
                "。",
                ". ",
                " ",
                ""
            ]
        else:
            # 默认（包括PDF/DOCX/TEXT）
            return default_separators
    
    def split_text(self, text: str, add_metadata: bool = False) -> List[str]:
        """
        使用 LangChain 的智能分割器分割文本
        
        Args:
            text: 待分割的文本
            add_metadata: 是否在chunk中添加元数据标记（为未来扩展预留）
            
        Returns:
            分割后的文本块列表
        """
        if not text or len(text) == 0:
            return []
        
        # 如果文本长度小于 chunk_size，直接返回
        if len(text) <= self.chunk_size:
            return [text]
        
        try:
            # 创建 LangChain 的递归字符文本分割器
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=self.separators,
                length_function=len,
                is_separator_regex=False,
            )
            
            # 使用 LangChain 的智能分割
            chunks = splitter.split_text(text)
            
            logger.info(f"文本分割完成: 原文本长度={len(text)}, 块数={len(chunks)}, "
                       f"平均块大小={sum(len(c) for c in chunks) / len(chunks):.0f}")
            
            return chunks
            
        except Exception as e:
            logger.error(f"LangChain 文本分割失败，使用降级方案: {str(e)}")
            # 降级方案：简单按字符数分割
            return self._fallback_split(text)
    
    def split_text_with_metadata(
        self,
        text: str,
        source_file: Optional[str] = None,
        file_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        分割文本并添加元数据（为Ollama等扩展预留）
        
        Args:
            text: 待分割的文本
            source_file: 来源文件名
            file_type: 文件类型
        
        Returns:
            包含元数据的chunk列表 [{"content": "...", "metadata": {...}}, ...]
        """
        chunks = self.split_text(text)
        
        result = []
        for i, chunk in enumerate(chunks):
            chunk_data = {
                "content": chunk,
                "metadata": {
                    "chunk_index": i,
                    "chunk_size": len(chunk),
                    "source_file": source_file,
                    "file_type": file_type,
                    "doc_type": self.document_type,
                    # 为未来扩展预留字段
                    "embedding_provider": None,  # 可扩展为 "transformers" 或 "ollama"
                    "page_number": None,         # PDF可以填充页码
                    "heading": None,              # DOCX可以填充标题
                }
            }
            result.append(chunk_data)
        
        return result
    
    def _fallback_split(self, text: str) -> List[str]:
        """
        降级分割方案（当 LangChain 失败时使用）
        
        Args:
            text: 文本
            
        Returns:
            分割后的文本块列表
        """
        chunks = []
        step = self.chunk_size - self.chunk_overlap
        
        for i in range(0, len(text), step):
            chunk = text[i:i + self.chunk_size]
            if chunk.strip():
                chunks.append(chunk)
        
        logger.info(f"降级分割完成: 块数={len(chunks)}")
        return chunks
