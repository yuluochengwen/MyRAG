"""基于 LangChain 的智能文本分割工具"""
import re
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
        profile_map = getattr(config, 'split_profiles', {}) or {}
        profile = profile_map.get(document_type or 'text', {}) if isinstance(profile_map, dict) else {}

        self.chunk_size = chunk_size or int(profile.get('chunk_size', config.chunk_size))
        self.chunk_overlap = chunk_overlap or int(profile.get('chunk_overlap', config.chunk_overlap))
        if self.chunk_overlap >= self.chunk_size:
            self.chunk_overlap = max(0, self.chunk_size // 5)
        self.document_type = document_type
        self.hard_sentence_split_enabled = bool(getattr(config, 'hard_sentence_split_enabled', True))
        self.hard_sentence_max_length = max(80, int(getattr(config, 'hard_sentence_max_length', 280) or 280))
        
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
            "\n# ",
            "\n## ",
            "\n### ",
            "\n#### ",
            "\n- ",
            "\n* ",
            "\n1. ",
            "\n|",      # Markdown表格
            "\n---",    # 分割线
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
                "\n\nfunc ",      # Go函数
                "\n\nSELECT ",    # SQL语句
                "\n\nINSERT ",
                "\n\nUPDATE ",
                "\n\nDELETE ",
                "\n\n",           # 空行
                "\n",
                " ",
                ""
            ]
        elif doc_type == 'markdown':
            return [
                "\n# ",
                "\n## ",
                "\n### ",
                "\n#### ",
                "\n- ",
                "\n* ",
                "\n1. ",
                "\n|",
                "\n\n",
                "\n",
                "。",
                ". ",
                " ",
                ""
            ]
        elif doc_type == 'json':
            return [
                "\n\n",
                "\n",
                "},",
                "],",
                ",\"",
                ",",
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

    def _normalize_text(self, text: str) -> str:
        """预清洗文本，减少噪声分块。"""
        if not text:
            return ""

        normalized = text.replace('\r\n', '\n').replace('\r', '\n')
        normalized = normalized.replace('\u00a0', ' ')
        normalized = re.sub(r"[\t\f\v]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        normalized = re.sub(r"[ ]{2,}", " ", normalized)
        return normalized.strip()

    def _hard_split_long_sentences(self, text: str) -> str:
        """对异常超长句进行硬切，降低单块语义混杂。
        
        使用 regex finditer 定位标点位置批量切分，避免逐字符遍历的 O(n²) 拼接开销。
        策略：优先在标点处切分；若连续 max_length 内无标点则强制定长切。
        """
        if not text or not self.hard_sentence_split_enabled:
            return text

        max_len = self.hard_sentence_max_length
        lines = text.split('\n')
        processed_lines: List[str] = []
        punct_re = re.compile(r'[。！？!?；;,.，]')

        for line in lines:
            current = line.strip()
            if len(current) <= max_len:
                processed_lines.append(current)
                continue

            # 收集所有标点位置（作为候选切分点）
            punct_positions = [m.end() for m in punct_re.finditer(current)]

            if punct_positions:
                segments: List[str] = []
                seg_start = 0
                last_punct = 0

                for pos in punct_positions:
                    if pos - seg_start >= max_len:
                        # 在上一个标点处切分；如果上一个标点就是起点则在当前标点切
                        cut = last_punct if last_punct > seg_start else pos
                        segment = current[seg_start:cut].strip()
                        if segment:
                            segments.append(segment)
                        seg_start = cut
                    last_punct = pos

                # 处理剩余部分
                remainder = current[seg_start:].strip()
                if remainder:
                    if len(remainder) <= max_len * 1.3:
                        segments.append(remainder)
                    else:
                        # 剩余部分仍然超长，定长切
                        for i in range(0, len(remainder), max_len):
                            piece = remainder[i:i + max_len].strip()
                            if piece:
                                segments.append(piece)

                processed_lines.extend(segments)
            else:
                # 无标点，定长硬切
                for i in range(0, len(current), max_len):
                    piece = current[i:i + max_len].strip()
                    if piece:
                        processed_lines.append(piece)

        return "\n".join(processed_lines)
    
    def split_text(self, text: str, add_metadata: bool = False) -> List[str]:
        """
        使用 LangChain 的智能分割器分割文本
        
        Args:
            text: 待分割的文本
            add_metadata: 是否在chunk中添加元数据标记（为未来扩展预留）
            
        Returns:
            分割后的文本块列表
        """
        text = self._normalize_text(text)
        text = self._hard_split_long_sentences(text)

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
            chunks = [chunk.strip() for chunk in chunks if chunk and chunk.strip()]
            
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
        text = self._normalize_text(text)
        text = self._hard_split_long_sentences(text)
        step = max(1, self.chunk_size - self.chunk_overlap)
        
        for i in range(0, len(text), step):
            chunk = text[i:i + self.chunk_size]
            if chunk.strip():
                chunks.append(chunk)
        
        logger.info(f"降级分割完成: 块数={len(chunks)}")
        return chunks
