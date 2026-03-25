"""LoRA 模型管理服务"""
import os
import shutil
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from app.core.database import DatabaseManager
from app.models.lora_model import LoRAModel
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LoRAService:
    """LoRA 模型管理服务"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.lora_dir = Path("Models/LoRA")
        
        # 确保目录存在
        self.lora_dir.mkdir(parents=True, exist_ok=True)
    
    async def scan_lora_models(self) -> List[Dict[str, Any]]:
        """
        扫描 LoRA 模型目录
        
        Returns:
            LoRA 模型列表
        """
        try:
            models = []
            
            # 扫描目录
            if self.lora_dir.exists():
                for model_dir in self.lora_dir.iterdir():
                    if model_dir.is_dir():
                        # 检查必需文件
                        adapter_config = model_dir / "adapter_config.json"
                        adapter_model = model_dir / "adapter_model.bin"
                        
                        if adapter_config.exists() and adapter_model.exists():
                            # 计算文件大小
                            file_size = self._calculate_model_size(model_dir)
                            
                            models.append({
                                "name": model_dir.name,
                                "path": str(model_dir),
                                "file_size": file_size
                            })
            
            logger.info(f"扫描到 {len(models)} 个 LoRA 模型")
            return models
            
        except Exception as e:
            logger.error(f"扫描 LoRA 模型失败: {str(e)}")
            raise
    
    async def get_lora_model(self, lora_id: int) -> Optional[LoRAModel]:
        """
        获取 LoRA 模型详情
        
        Args:
            lora_id: LoRA 模型 ID
            
        Returns:
            LoRA 模型对象
        """
        try:
            sql = "SELECT * FROM lora_models WHERE id = %s AND status = 'active'"
            result = await self.db.execute_query(sql, (lora_id,))
            
            if result:
                return LoRAModel.from_dict(result[0])
            
            return None
            
        except Exception as e:
            logger.error(f"获取 LoRA 模型失败: {str(e)}")
            raise
    
    async def list_lora_models(
        self,
        base_model_name: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[LoRAModel]:
        """
        获取 LoRA 模型列表
        
        Args:
            base_model_name: 基座模型名称（可选，用于筛选）
            skip: 跳过数量
            limit: 返回数量
            
        Returns:
            LoRA 模型列表
        """
        try:
            if base_model_name:
                sql = """
                    SELECT * FROM lora_models 
                    WHERE status = 'active' AND base_model_name = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                result = await self.db.execute_query(sql, (base_model_name, limit, skip))
            else:
                sql = """
                    SELECT * FROM lora_models 
                    WHERE status = 'active'
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                result = await self.db.execute_query(sql, (limit, skip))
            
            models = [LoRAModel.from_dict(row) for row in result]
            logger.info(f"获取到 {len(models)} 个 LoRA 模型")
            return models
            
        except Exception as e:
            logger.error(f"获取 LoRA 模型列表失败: {str(e)}")
            raise
    
    async def get_lora_models_by_base(self, base_model_name: str) -> List[LoRAModel]:
        """
        获取指定基座模型的 LoRA 列表
        
        Args:
            base_model_name: 基座模型名称
            
        Returns:
            LoRA 模型列表
        """
        return await self.list_lora_models(base_model_name=base_model_name)
    
    async def delete_lora_model(self, lora_id: int) -> Dict[str, Any]:
        """
        删除 LoRA 模型
        
        Args:
            lora_id: LoRA 模型 ID
            
        Returns:
            删除结果
        """
        try:
            # 1. 获取模型信息
            model = await self.get_lora_model(lora_id)
            if not model:
                return {
                    "success": False,
                    "message": f"LoRA 模型不存在: id={lora_id}"
                }
            
            # 2. 删除文件系统中的权重文件
            model_path = Path(model.file_path)
            if model_path.exists():
                try:
                    shutil.rmtree(model_path)
                    logger.info(f"删除 LoRA 权重文件: {model_path}")
                except Exception as e:
                    logger.error(f"删除 LoRA 权重文件失败: {str(e)}")
                    # 继续删除数据库记录
            
            # 3. 更新数据库记录状态为 deleted
            sql = "UPDATE lora_models SET status = 'deleted' WHERE id = %s"
            await self.db.execute_update(sql, (lora_id,))
            
            # 4. 清理关联的助手（将 lora_model_id 设置为 NULL）
            sql_clear_assistants = "UPDATE assistants SET lora_model_id = NULL WHERE lora_model_id = %s"
            await self.db.execute_update(sql_clear_assistants, (lora_id,))
            
            logger.info(f"LoRA 模型删除成功: id={lora_id}, name={model.name}")
            return {
                "success": True,
                "message": f"LoRA 模型删除成功: {model.name}"
            }
            
        except Exception as e:
            logger.error(f"删除 LoRA 模型失败: {str(e)}")
            raise
    
    async def create_lora_model(
        self,
        name: str,
        base_model_name: str,
        file_path: str,
        file_size: int,
        training_job_id: Optional[int] = None
    ) -> Optional[LoRAModel]:
        """
        创建 LoRA 模型记录
        
        Args:
            name: LoRA 模型名称
            base_model_name: 基座模型名称
            file_path: 文件路径
            file_size: 文件大小
            training_job_id: 训练任务 ID
            
        Returns:
            创建的 LoRA 模型对象
        """
        try:
            sql = """
                INSERT INTO lora_models 
                (name, base_model_name, file_path, file_size, training_job_id, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            lora_id = await self.db.execute_insert(
                sql,
                (name, base_model_name, file_path, file_size, training_job_id, 'active')
            )
            
            if lora_id:
                logger.info(f"LoRA 模型创建成功: id={lora_id}, name={name}")
                return await self.get_lora_model(lora_id)
            
            return None
            
        except Exception as e:
            logger.error(f"创建 LoRA 模型失败: {str(e)}")
            raise
    
    async def check_lora_name_exists(self, name: str) -> bool:
        """
        检查 LoRA 名称是否已存在
        
        Args:
            name: LoRA 模型名称
            
        Returns:
            是否存在
        """
        try:
            sql = "SELECT COUNT(*) as count FROM lora_models WHERE name = %s AND status = 'active'"
            result = await self.db.execute_query(sql, (name,))
            
            if result and result[0]['count'] > 0:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查 LoRA 名称失败: {str(e)}")
            raise
    
    def _calculate_model_size(self, model_path: Path) -> int:
        """
        计算模型文件大小
        
        Args:
            model_path: 模型目录路径
            
        Returns:
            文件大小（字节）
        """
        total_size = 0
        
        try:
            for file_path in model_path.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except Exception as e:
            logger.error(f"计算模型大小失败: {str(e)}")
        
        return total_size
