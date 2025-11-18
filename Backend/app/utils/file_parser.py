"""文件解析器 - 将不同格式的文件转换为文本"""
import os
from pathlib import Path
from typing import Optional
from abc import ABC, abstractmethod

from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseParser(ABC):
    """文件解析器基类"""
    
    @abstractmethod
    def parse(self, file_path: str) -> str:
        """
        解析文件为文本
        
        Args:
            file_path: 文件路径
            
        Returns:
            解析后的文本内容
        """
        pass


class TxtParser(BaseParser):
    """TXT文件解析器"""
    
    def parse(self, file_path: str) -> str:
        """解析TXT文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # 尝试其他编码
            for encoding in ['gbk', 'gb2312', 'latin-1']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        return f.read()
                except:
                    continue
            
            raise ValueError(f"无法解析文件编码: {file_path}")


class MarkdownParser(BaseParser):
    """Markdown文件解析器"""
    
    def parse(self, file_path: str) -> str:
        """解析Markdown文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"解析Markdown文件失败: {file_path}, {str(e)}")
            raise


class PDFParser(BaseParser):
    """PDF文件解析器 - 增强版，保留段落结构"""
    
    def parse(self, file_path: str) -> str:
        """解析PDF文件，保留段落边界"""
        try:
            from PyPDF2 import PdfReader
            
            reader = PdfReader(file_path)
            pages = []
            
            for page_num, page in enumerate(reader.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    # 清理页面文本：移除过多的空行，但保留段落分隔
                    lines = page_text.split('\n')
                    cleaned_lines = []
                    prev_empty = False
                    
                    for line in lines:
                        line = line.strip()
                        if line:
                            cleaned_lines.append(line)
                            prev_empty = False
                        elif not prev_empty:
                            # 保留一个空行作为段落分隔
                            cleaned_lines.append('')
                            prev_empty = True
                    
                    # 用双换行连接段落（为递归分割提供明确的边界）
                    page_content = '\n'.join(cleaned_lines)
                    
                    # 添加页码标记（可选，帮助追踪来源）
                    pages.append(f"[第{page_num}页]\n{page_content}")
            
            # 页面间用双换行分隔（段落级别的边界）
            return '\n\n'.join(pages)
            
        except Exception as e:
            logger.error(f"解析PDF文件失败: {file_path}, {str(e)}")
            raise


class DocxParser(BaseParser):
    """DOCX文件解析器 - 增强版，保留段落结构和标题层级"""
    
    def parse(self, file_path: str) -> str:
        """解析DOCX文件，保留文档结构"""
        try:
            from docx import Document
            
            doc = Document(file_path)
            content_parts = []
            
            # 解析段落（保留标题层级信息）
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    # 检查是否是标题
                    if paragraph.style.name.startswith('Heading'):
                        # 标题前后添加空行，增强段落分隔
                        content_parts.append(f"\n{paragraph.text}\n")
                    else:
                        content_parts.append(paragraph.text)
            
            # 解析表格（表格前后添加明确分隔）
            for table in doc.tables:
                table_content = []
                for row in table.rows:
                    row_text = []
                    for cell in row.cells:
                        if cell.text.strip():
                            row_text.append(cell.text.strip())
                    if row_text:
                        table_content.append(' | '.join(row_text))
                
                if table_content:
                    # 表格作为独立块，前后用双换行分隔
                    content_parts.append('\n[表格]\n' + '\n'.join(table_content))
            
            # 段落间用双换行分隔（为递归分割提供明确边界）
            return '\n\n'.join(part.strip() for part in content_parts if part.strip())
            
        except Exception as e:
            logger.error(f"解析DOCX文件失败: {file_path}, {str(e)}")
            raise


class HTMLParser(BaseParser):
    """HTML文件解析器 - 增强版，保留段落和标题结构"""
    
    def parse(self, file_path: str) -> str:
        """解析HTML文件，保留文档结构"""
        try:
            from bs4 import BeautifulSoup
            
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'lxml')
            
            # 移除script、style和不需要的标签
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            
            # 按块元素提取文本，保留结构
            content_parts = []
            
            # 提取标题（h1-h6）
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text = heading.get_text().strip()
                if text:
                    content_parts.append(f"\n{text}\n")
            
            # 提取段落（p, div, article, section）
            for block in soup.find_all(['p', 'div', 'article', 'section', 'blockquote']):
                text = block.get_text().strip()
                # 避免重复（如果已经被标题提取过）
                if text and text not in str(content_parts):
                    content_parts.append(text)
            
            # 提取列表（ul, ol）
            for list_tag in soup.find_all(['ul', 'ol']):
                items = []
                for li in list_tag.find_all('li', recursive=False):
                    text = li.get_text().strip()
                    if text:
                        items.append(f"- {text}")
                if items:
                    content_parts.append('\n'.join(items))
            
            # 段落间用双换行分隔
            return '\n\n'.join(part.strip() for part in content_parts if part.strip())
            
        except Exception as e:
            logger.error(f"解析HTML文件失败: {file_path}, {str(e)}")
            raise


class FileParser:
    """文件解析器工厂"""
    
    # 解析器映射
    PARSERS = {
        '.txt': TxtParser(),
        '.md': MarkdownParser(),
        '.markdown': MarkdownParser(),
        '.pdf': PDFParser(),
        '.docx': DocxParser(),
        '.doc': DocxParser(),
        '.html': HTMLParser(),
        '.htm': HTMLParser(),
    }
    
    @classmethod
    def parse(cls, file_path: str) -> str:
        """
        根据文件扩展名自动选择解析器
        
        Args:
            file_path: 文件路径
            
        Returns:
            解析后的文本内容
            
        Raises:
            ValueError: 不支持的文件格式
        """
        ext = os.path.splitext(file_path)[1].lower()
        
        parser = cls.PARSERS.get(ext)
        if not parser:
            raise ValueError(f"不支持的文件格式: {ext}")
        
        logger.info(f"开始解析文件: {file_path}")
        
        try:
            text = parser.parse(file_path)
            logger.info(f"文件解析成功: {file_path}, 文本长度: {len(text)}")
            return text
        except Exception as e:
            logger.error(f"文件解析失败: {file_path}, 错误: {str(e)}")
            raise
    
    @classmethod
    def is_supported(cls, filename: str) -> bool:
        """
        检查文件格式是否支持
        
        Args:
            filename: 文件名
            
        Returns:
            是否支持
        """
        ext = os.path.splitext(filename)[1].lower()
        return ext in cls.PARSERS


# 解析器映射（兼容旧接口）
PARSER_MAP = {
    'txt': TxtParser,
    'md': MarkdownParser,
    'pdf': PDFParser,
    'docx': DocxParser,
    'html': HTMLParser,
}


def get_file_parser(file_type: str) -> BaseParser:
    """
    根据文件类型获取解析器
    
    Args:
        file_type: 文件类型（不带点号，如 'txt', 'pdf'）
        
    Returns:
        解析器实例
        
    Raises:
        ValueError: 不支持的文件类型
    """
    parser_class = PARSER_MAP.get(file_type.lower())
    
    if not parser_class:
        raise ValueError(f"不支持的文件类型: {file_type}")
    
    return parser_class()
