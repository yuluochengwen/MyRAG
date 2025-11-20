"""LoRA 模型扫描与管理服务"""
import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.core.database import DatabaseManager
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LoRAScannerService:
    """LoRA 模型扫描与管理服务"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        # LoRA 模型目录（多个）
        base_dir = Path(settings.file.upload_dir).parent
        self.lora_dir = base_dir / "Models" / "LoRA"
        self.lora_dir.mkdir(parents=True, exist_ok=True)
        
        # LLaMA-Training 输出目录
        self.training_saves_dir = base_dir / "LLaMA-Training" / "saves"
        
        logger.info(f"LoRA 模型目录: {self.lora_dir}")
        logger.info(f"LLaMA-Training 输出目录: {self.training_saves_dir}")
    
    def scan_training_output(self) -> List[Dict[str, Any]]:
        """
        扫描训练输出目录，发现新模型
        扫描 Models/LoRA 和 LLaMA-Training/saves 两个目录
        
        Returns:
            新发现的模型列表
        """
        new_models = []
        
        # 收集所有需要扫描的目录
        scan_dirs = []
        if self.lora_dir.exists():
            scan_dirs.append(("Models/LoRA", self.lora_dir))
        if self.training_saves_dir.exists():
            scan_dirs.append(("LLaMA-Training/saves", self.training_saves_dir))
        
        if not scan_dirs:
            logger.warning("没有可扫描的 LoRA 目录")
            return new_models
        
        # 扫描所有目录
        for dir_name, dir_path in scan_dirs:
            logger.info(f"开始扫描 {dir_name}: {dir_path}")
            new_models.extend(self._scan_directory(dir_path))
        
        return new_models
    
    def _scan_directory(self, base_dir: Path) -> List[Dict[str, Any]]:
        """
        扫描单个目录（支持递归扫描 saves 目录的复杂结构）
        
        Args:
            base_dir: 要扫描的基础目录
            
        Returns:
            新发现的模型列表
        """
        new_models = []
        
        # 递归查找所有包含 adapter_config.json 的目录
        for adapter_config in base_dir.rglob("adapter_config.json"):
            model_dir = adapter_config.parent
            # 检查是否包含 LoRA 权重文件
            adapter_model_safetensors = model_dir / "adapter_model.safetensors"
            adapter_model_bin = model_dir / "adapter_model.bin"
            
            # 必须有配置文件和权重文件
            has_config = adapter_config.exists()
            has_weights = adapter_model_safetensors.exists() or adapter_model_bin.exists()
            
            if not (has_config and has_weights):
                logger.debug(f"跳过非 LoRA 目录: {model_dir.name}")
                continue
            
            model_name = model_dir.name
            
            # 检查数据库中是否已存在
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM lora_models WHERE model_name = %s",
                        (model_name,)
                    )
                    if cursor.fetchone():
                        logger.debug(f"模型已存在: {model_name}")
                        continue  # 已存在
            
            logger.info(f"发现新 LoRA 模型: {model_name}")
            
            # 读取配置信息
            try:
                with open(adapter_config, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    base_model = config.get('base_model_name_or_path', 'unknown')
                    lora_rank = config.get('r', None)
                    lora_alpha = config.get('lora_alpha', None)
            except Exception as e:
                logger.error(f"读取配置文件失败: {e}")
                base_model = 'unknown'
                lora_rank = None
                lora_alpha = None
            
            # 计算文件大小
            try:
                file_size = sum(f.stat().st_size for f in model_dir.rglob('*') if f.is_file())
                file_size_mb = file_size / (1024 * 1024)
            except Exception as e:
                logger.error(f"计算文件大小失败: {e}")
                file_size_mb = 0
            
            # 插入数据库
            try:
                with self.db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO lora_models 
                            (model_name, base_model, model_path, file_size_mb, 
                             lora_rank, lora_alpha, status)
                            VALUES (%s, %s, %s, %s, %s, %s, 'discovered')
                        """, (model_name, base_model, str(model_dir), file_size_mb,
                              lora_rank, lora_alpha))
                        conn.commit()
                        model_id = cursor.lastrowid
                
                new_model = {
                    "id": model_id,
                    "model_name": model_name,
                    "base_model": base_model,
                    "file_size_mb": round(file_size_mb, 2),
                    "lora_rank": lora_rank,
                    "lora_alpha": lora_alpha
                }
                new_models.append(new_model)
                
                logger.info(f"✅ 已添加模型: {model_name} (ID: {model_id})")
                
            except Exception as e:
                logger.error(f"插入数据库失败: {e}", exc_info=True)
        
        logger.info(f"扫描完成，发现 {len(new_models)} 个新模型")
        return new_models
    
    def list_models(self) -> List[Dict[str, Any]]:
        """列出所有 LoRA 模型"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM lora_models 
                    ORDER BY created_at DESC
                """)
                models = cursor.fetchall()
        
        return models if models else []
    
    def get_model(self, model_id: int) -> Optional[Dict[str, Any]]:
        """获取单个模型信息"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM lora_models WHERE id = %s",
                    (model_id,)
                )
                return cursor.fetchone()
    
    def activate_lora(self, model_id: int) -> Dict[str, Any]:
        """
        激活 LoRA 模型 (标记为可用状态,实际加载在推理时完成)
        
        Args:
            model_id: 模型ID
            
        Returns:
            激活结果
        """
        # 获取模型信息
        model = self.get_model(model_id)
        
        if not model:
            return {
                "success": False,
                "message": f"模型不存在: ID={model_id}"
            }
        
        logger.info(f"激活 LoRA 模型: {model['model_name']}")
        
        try:
            # 验证 LoRA 文件完整性
            model_path = Path(model['model_path'])
            
            # 检查必需的 PEFT 文件
            adapter_config = model_path / "adapter_config.json"
            adapter_model = model_path / "adapter_model.safetensors"
            
            if not adapter_config.exists():
                raise FileNotFoundError(f"缺少 adapter_config.json: {model_path}")
            
            if not adapter_model.exists():
                # 尝试查找 .bin 格式
                adapter_model_bin = model_path / "adapter_model.bin"
                if not adapter_model_bin.exists():
                    raise FileNotFoundError(f"缺少 adapter 模型文件: {model_path}")
            
            logger.info(f"✅ LoRA 文件验证通过: {model_path}")
            
            # 验证基座模型路径
            base_model = model['base_model']
            if '\\' in base_model or '/' in base_model:
                base_model_path = Path(base_model)
                if not base_model_path.exists():
                    raise FileNotFoundError(f"基座模型不存在: {base_model_path}")
                logger.info(f"✅ 基座模型验证通过: {base_model_path}")
            
            # 更新数据库状态为已激活
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE lora_models 
                        SET status = 'active', 
                            is_deployed = TRUE,
                            deployed_at = NOW()
                        WHERE id = %s
                    """, (model_id,))
                    conn.commit()
            
            logger.info(f"✅ LoRA 模型已激活: {model['model_name']}")
            
            return {
                "success": True,
                "message": "激活成功",
                "model_id": model_id,
                "model_name": model['model_name'],
                "base_model": base_model,
                "lora_path": str(model_path)
            }
            
        except FileNotFoundError as e:
            self._update_status(model_id, 'failed')
            logger.error(f"文件验证失败: {e}")
            return {
                "success": False,
                "message": f"文件验证失败: {str(e)}"
            }
        except Exception as e:
            self._update_status(model_id, 'failed')
            logger.error(f"激活失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"激活失败: {str(e)}"
            }
    
    def delete_model(self, model_id: int, force: bool = False) -> Dict[str, Any]:
        """
        删除 LoRA 模型
        
        Args:
            model_id: 模型ID
            force: 是否强制删除（即使正在使用）
            
        Returns:
            删除结果
        """
        # 获取模型信息
        model = self.get_model(model_id)
        
        if not model:
            return {
                "success": False,
                "message": f"模型不存在: ID={model_id}"
            }
        
        logger.info(f"开始删除 LoRA 模型: {model['model_name']}")
        
        # 检查是否被助手使用
        if not force:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT COUNT(*) as count FROM assistants 
                        WHERE lora_model_id = %s
                    """, (model_id,))
                    result = cursor.fetchone()
                    
                    if result and result['count'] > 0:
                        return {
                            "success": False,
                            "message": f"模型正在被 {result['count']} 个助手使用，无法删除",
                            "in_use": True,
                            "usage_count": result['count']
                        }
        
        try:
            # 如果已部署到 Ollama，先删除
            if model['is_deployed'] and model['ollama_model_name']:
                try:
                    logger.info(f"正在从 Ollama 删除: {model['ollama_model_name']}")
                    subprocess.run(
                        ['ollama', 'rm', model['ollama_model_name']],
                        capture_output=True,
                        timeout=30
                    )
                    logger.info(f"已从 Ollama 删除: {model['ollama_model_name']}")
                except Exception as e:
                    logger.warning(f"从 Ollama 删除失败（继续删除文件）: {e}")
            
            # 删除文件
            model_path = Path(model['model_path'])
            if model_path.exists():
                logger.info(f"正在删除文件: {model_path}")
                shutil.rmtree(model_path)
                logger.info(f"文件已删除: {model_path}")
            
            # 删除数据库记录
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 如果强制删除，先解除助手关联
                    if force:
                        cursor.execute("""
                            UPDATE assistants 
                            SET lora_model_id = NULL 
                            WHERE lora_model_id = %s
                        """, (model_id,))
                    
                    cursor.execute(
                        "DELETE FROM lora_models WHERE id = %s",
                        (model_id,)
                    )
                    conn.commit()
            
            logger.info(f"✅ LoRA 模型已删除: {model['model_name']}")
            
            return {
                "success": True,
                "message": "删除成功",
                "model_name": model['model_name']
            }
            
        except Exception as e:
            logger.error(f"删除失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"删除失败: {str(e)}"
            }
    
    def _update_status(self, model_id: int, status: str):
        """更新模型状态"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE lora_models SET status = %s WHERE id = %s",
                        (status, model_id)
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"更新状态失败: {e}")
