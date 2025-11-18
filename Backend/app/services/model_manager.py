"""模型管理服务 - 删除、验证等操作"""
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from app.core.database import DatabaseManager
from app.core.config import BASE_DIR
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ModelManager:
    """模型管理器"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.llm_dir = BASE_DIR / "Models" / "LLM"
        self.embedding_dir = BASE_DIR / "Models" / "Embedding"
        self.lora_dir = BASE_DIR / "Models" / "LoRA"
    
    async def check_embedding_model_usage(self, model_name: str) -> Dict[str, any]:
        """
        检查嵌入模型的使用情况
        
        Args:
            model_name: 模型名称
            
        Returns:
            使用情况字典
        """
        try:
            # 检查知识库使用
            kb_sql = "SELECT id, name FROM knowledge_bases WHERE embedding_model = %s"
            kb_results = await self.db.execute_query(kb_sql, (model_name,))
            
            # 检查助手使用
            assistant_sql = "SELECT id, name FROM assistants WHERE embedding_model = %s AND status = 'active'"
            assistant_results = await self.db.execute_query(assistant_sql, (model_name,))
            
            return {
                "is_used": len(kb_results) > 0 or len(assistant_results) > 0,
                "knowledge_bases": [{"id": kb["id"], "name": kb["name"]} for kb in kb_results],
                "assistants": [{"id": a["id"], "name": a["name"]} for a in assistant_results],
                "total_usage": len(kb_results) + len(assistant_results)
            }
        except Exception as e:
            logger.error(f"检查嵌入模型使用失败: {str(e)}")
            raise
    
    async def check_llm_model_usage(self, model_name: str) -> Dict[str, any]:
        """
        检查LLM模型的使用情况
        
        Args:
            model_name: 模型名称
            
        Returns:
            使用情况字典
        """
        try:
            # 检查助手使用
            assistant_sql = "SELECT id, name FROM assistants WHERE llm_model = %s AND status = 'active'"
            assistant_results = await self.db.execute_query(assistant_sql, (model_name,))
            
            return {
                "is_used": len(assistant_results) > 0,
                "assistants": [{"id": a["id"], "name": a["name"]} for a in assistant_results],
                "total_usage": len(assistant_results)
            }
        except Exception as e:
            logger.error(f"检查LLM模型使用失败: {str(e)}")
            raise
    
    async def delete_embedding_model(self, model_name: str, force: bool = False) -> Dict[str, any]:
        """
        删除嵌入模型
        
        Args:
            model_name: 模型名称
            force: 是否强制删除（即使被使用）
            
        Returns:
            删除结果
        """
        try:
            # 检查使用情况
            usage = await self.check_embedding_model_usage(model_name)
            
            if usage["is_used"] and not force:
                return {
                    "success": False,
                    "message": f"模型 '{model_name}' 正在被使用，无法删除",
                    "usage": usage
                }
            
            # 删除模型文件夹
            model_path = self.embedding_dir / model_name
            if not model_path.exists():
                return {
                    "success": False,
                    "message": f"模型 '{model_name}' 不存在"
                }
            
            shutil.rmtree(model_path)
            logger.info(f"嵌入模型已删除: {model_name}")
            
            return {
                "success": True,
                "message": f"模型 '{model_name}' 删除成功"
            }
        except Exception as e:
            logger.error(f"删除嵌入模型失败: {str(e)}")
            return {
                "success": False,
                "message": f"删除失败: {str(e)}"
            }
    
    async def delete_llm_model(self, model_name: str, force: bool = False) -> Dict[str, any]:
        """
        删除LLM模型
        
        Args:
            model_name: 模型名称
            force: 是否强制删除（即使被使用）
            
        Returns:
            删除结果
        """
        try:
            # 检查使用情况
            usage = await self.check_llm_model_usage(model_name)
            
            if usage["is_used"] and not force:
                return {
                    "success": False,
                    "message": f"模型 '{model_name}' 正在被使用，无法删除",
                    "usage": usage
                }
            
            # 删除模型文件夹
            model_path = self.llm_dir / model_name
            if not model_path.exists():
                return {
                    "success": False,
                    "message": f"模型 '{model_name}' 不存在"
                }
            
            shutil.rmtree(model_path)
            logger.info(f"LLM模型已删除: {model_name}")
            
            return {
                "success": True,
                "message": f"模型 '{model_name}' 删除成功"
            }
        except Exception as e:
            logger.error(f"删除LLM模型失败: {str(e)}")
            return {
                "success": False,
                "message": f"删除失败: {str(e)}"
            }
    
    async def delete_lora_model(self, model_name: str) -> Dict[str, any]:
        """
        删除LoRA模型
        
        Args:
            model_name: 模型名称
            
        Returns:
            删除结果
        """
        try:
            # LoRA模型暂时不检查使用情况（未来可扩展）
            model_path = self.lora_dir / model_name
            if not model_path.exists():
                return {
                    "success": False,
                    "message": f"LoRA模型 '{model_name}' 不存在"
                }
            
            shutil.rmtree(model_path)
            logger.info(f"LoRA模型已删除: {model_name}")
            
            return {
                "success": True,
                "message": f"LoRA模型 '{model_name}' 删除成功"
            }
        except Exception as e:
            logger.error(f"删除LoRA模型失败: {str(e)}")
            return {
                "success": False,
                "message": f"删除失败: {str(e)}"
            }
    
    async def get_statistics(self) -> Dict[str, any]:
        """
        获取模型统计信息
        
        Returns:
            统计数据
        """
        try:
            from app.services.model_scanner import model_scanner
            
            embedding_models = model_scanner.scan_embedding_models()
            llm_models = model_scanner.scan_llm_models()
            lora_models = model_scanner.scan_lora_models()
            
            # 计算总大小
            total_size = sum(m["size_bytes"] for m in embedding_models)
            total_size += sum(m["size_bytes"] for m in llm_models)
            total_size += sum(m["size_bytes"] for m in lora_models)
            
            return {
                "embedding_count": len(embedding_models),
                "llm_count": len(llm_models),
                "lora_count": len(lora_models),
                "total_count": len(embedding_models) + len(llm_models) + len(lora_models),
                "total_size_bytes": total_size,
                "total_size": model_scanner._format_size(total_size)
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {str(e)}")
            raise


# 全局实例（需要在使用时传入 db_manager）
def get_model_manager(db_manager: DatabaseManager) -> ModelManager:
    """获取模型管理器实例"""
    return ModelManager(db_manager)
