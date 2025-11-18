"""日志工具"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from app.core.config import settings


def setup_logger():
    """设置全局日志"""
    log_config = settings.logging
    
    # 确保日志目录存在
    log_file = Path(log_config.file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 创建logger
    logger = logging.getLogger("myrag")
    logger.setLevel(getattr(logging, log_config.level))
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 文件处理器
    file_handler = RotatingFileHandler(
        log_config.file,
        maxBytes=log_config.max_bytes,
        backupCount=log_config.backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # 格式化器
    formatter = logging.Formatter(log_config.format)
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    获取logger实例
    
    Args:
        name: logger名称，通常使用__name__
        
    Returns:
        Logger实例
    """
    if name:
        return logging.getLogger(f"myrag.{name}")
    return logging.getLogger("myrag")


# 初始化全局logger
logger = setup_logger()
