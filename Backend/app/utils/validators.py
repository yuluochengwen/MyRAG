"""验证工具"""
import os
import re
from typing import List, Tuple
from pathlib import Path
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


def validate_filename(filename: str) -> bool:
    """
    验证文件名是否合法
    
    Args:
        filename: 文件名
        
    Returns:
        是否合法
    """
    # 不允许的字符
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    
    if re.search(invalid_chars, filename):
        return False
    
    # 不允许的文件名
    invalid_names = [
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    ]
    
    name_without_ext = os.path.splitext(filename)[0].upper()
    if name_without_ext in invalid_names:
        return False
    
    return True


def validate_file_extension(filename: str, allowed_extensions: List[str] = None) -> str:
    """
    验证文件扩展名
    
    Args:
        filename: 文件名
        allowed_extensions: 允许的扩展名列表
        
    Returns:
        文件扩展名(不带点号,如 'txt', 'pdf')
        
    Raises:
        ValueError: 不支持的文件类型
    """
    if allowed_extensions is None:
        allowed_extensions = settings.file.allowed_extensions
    
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in allowed_extensions:
        raise ValueError(f"不支持的文件类型: {ext}")
    
    # 返回不带点号的扩展名
    return ext.lstrip('.')


def validate_file_size(file_size: int, max_size_mb: int = None) -> Tuple[bool, str]:
    """
    验证文件大小
    
    Args:
        file_size: 文件大小（字节）
        max_size_mb: 最大允许大小（MB）
        
    Returns:
        (是否合法, 错误信息)
    """
    if max_size_mb is None:
        max_size_mb = settings.file.max_size_mb
    
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if file_size > max_size_bytes:
        raise ValueError(f"文件大小超过限制 {max_size_mb}MB")
    
    return True


def validate_kb_name(name: str) -> bool:
    """
    验证知识库名称（简化版）
    
    Args:
        name: 知识库名称
        
    Returns:
        是否合法
    
    Raises:
        ValueError: 名称不合法
    """
    if not name or len(name.strip()) == 0:
        raise ValueError("知识库名称不能为空")
    
    if len(name) > 100:
        raise ValueError("知识库名称不能超过100个字符")
    
    # 只允许中文、英文、数字、下划线、连字符
    pattern = r'^[\u4e00-\u9fa5a-zA-Z0-9_-]+$'
    if not re.match(pattern, name):
        raise ValueError("知识库名称只能包含中文、英文、数字、下划线和连字符")
    
    return True


def sanitize_path(path: str) -> str:
    """
    清理路径，防止路径遍历攻击
    
    TODO: 应该在 file_service.py 的 save_file() 中使用此函数
    
    Args:
        path: 路径
        
    Returns:
        清理后的路径
    """
    # 移除路径遍历字符
    path = path.replace('..', '').replace('~', '')
    
    # 规范化路径
    path = os.path.normpath(path)
    
    return path


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小
    
    注意: 主要用于前端展示，后端API返回时使用
    
    Args:
        size_bytes: 字节数
        
    Returns:
        格式化后的字符串
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    
    return f"{size_bytes:.2f} PB"
