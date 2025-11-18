"""知识库元数据管理服务"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MetadataService:
    """管理知识库的 info.json 元数据文件"""
    
    def __init__(self, kb_base_dir: str):
        self.kb_base_dir = Path(kb_base_dir)
    
    def create_metadata(self, kb_id: int, kb_info: Dict[str, Any]) -> bool:
        """
        创建知识库元数据文件
        
        Args:
            kb_id: 知识库ID
            kb_info: 知识库信息
            
        Returns:
            是否成功
        """
        try:
            kb_dir = self.kb_base_dir / f"kb_{kb_id}"
            kb_dir.mkdir(parents=True, exist_ok=True)
            
            metadata = {
                "kb_id": kb_id,
                "name": kb_info.get("name"),
                "description": kb_info.get("description"),
                "embedding_model": kb_info.get("embedding_model"),
                "created_at": kb_info.get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat(),
                "total_files": 0,
                "total_chunks": 0,
                "version": "1.0"
            }
            
            info_file = kb_dir / "info.json"
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            logger.info(f"知识库元数据创建成功: kb_id={kb_id}")
            return True
            
        except Exception as e:
            logger.error(f"创建知识库元数据失败: {str(e)}")
            return False
    
    def update_metadata(self, kb_id: int, updates: Dict[str, Any]) -> bool:
        """
        更新知识库元数据
        
        Args:
            kb_id: 知识库ID
            updates: 更新的字段
            
        Returns:
            是否成功
        """
        try:
            info_file = self.kb_base_dir / f"kb_{kb_id}" / "info.json"
            
            if not info_file.exists():
                logger.warning(f"元数据文件不存在: kb_id={kb_id}")
                return False
            
            with open(info_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            metadata.update(updates)
            metadata["updated_at"] = datetime.now().isoformat()
            
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            logger.info(f"知识库元数据更新成功: kb_id={kb_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新知识库元数据失败: {str(e)}")
            return False
    
    def get_metadata(self, kb_id: int) -> Optional[Dict[str, Any]]:
        """
        读取知识库元数据
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            元数据字典
        """
        try:
            info_file = self.kb_base_dir / f"kb_{kb_id}" / "info.json"
            
            if not info_file.exists():
                return None
            
            with open(info_file, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"读取知识库元数据失败: {str(e)}")
            return None
    
    def delete_metadata(self, kb_id: int) -> bool:
        """
        删除知识库元数据文件
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            是否成功
        """
        try:
            info_file = self.kb_base_dir / f"kb_{kb_id}" / "info.json"
            
            if info_file.exists():
                info_file.unlink()
                logger.info(f"知识库元数据删除成功: kb_id={kb_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"删除知识库元数据失败: {str(e)}")
            return False
