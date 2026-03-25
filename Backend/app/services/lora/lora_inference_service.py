"""LoRA 推理服务"""
import torch
from typing import Dict, Any, Optional, List
from pathlib import Path
from collections import OrderedDict

from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

from app.core.database import DatabaseManager
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LoRAInferenceService:
    """LoRA 推理引擎"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        
        # 模型缓存 (LRU)
        self.base_model_cache: OrderedDict = OrderedDict()
        self.lora_model_cache: OrderedDict = OrderedDict()
        self.tokenizer_cache: OrderedDict = OrderedDict()
        
        # 缓存大小限制
        self.max_base_models = 2  # 最多缓存 2 个基座模型
        self.max_lora_models = 5  # 最多缓存 5 个 LoRA 模型
        
        # 目录配置
        self.llm_dir = Path("Models/LLM")
        self.lora_dir = Path("Models/LoRA")
    
    async def load_lora_model(
        self,
        lora_model_id: int,
        base_model_name: str
    ) -> tuple:
        """
        加载 LoRA 模型
        
        Args:
            lora_model_id: LoRA 模型 ID
            base_model_name: 基座模型名称
            
        Returns:
            (model, tokenizer)
        """
        try:
            cache_key = f"{base_model_name}_{lora_model_id}"
            
            # 检查缓存
            if cache_key in self.lora_model_cache:
                logger.info(f"从缓存加载 LoRA 模型: {cache_key}")
                # 移到最后（LRU）
                self.lora_model_cache.move_to_end(cache_key)
                return self.lora_model_cache[cache_key]
            
            # 获取 LoRA 模型信息
            sql = "SELECT * FROM lora_models WHERE id = %s"
            result = await self.db.execute_query(sql, (lora_model_id,))
            
            if not result:
                raise ValueError(f"LoRA 模型不存在: {lora_model_id}")
            
            lora_info = result[0]
            lora_path = Path(lora_info['file_path'])
            
            if not lora_path.exists():
                raise FileNotFoundError(f"LoRA 权重文件不存在: {lora_path}")
            
            # 加载或获取基座模型
            base_model, tokenizer = await self._get_or_load_base_model(base_model_name)
            
            # 加载 LoRA 权重
            logger.info(f"加载 LoRA 权重: {lora_path}")
            model = PeftModel.from_pretrained(base_model, str(lora_path))
            model.eval()
            
            # 添加到缓存
            self.lora_model_cache[cache_key] = (model, tokenizer)
            
            # LRU 淘汰
            if len(self.lora_model_cache) > self.max_lora_models:
                oldest_key = next(iter(self.lora_model_cache))
                logger.info(f"淘汰 LoRA 模型缓存: {oldest_key}")
                del self.lora_model_cache[oldest_key]
            
            logger.info(f"LoRA 模型加载完成: {cache_key}")
            return model, tokenizer
            
        except Exception as e:
            logger.error(f"加载 LoRA 模型失败: {str(e)}")
            # 回退到基座模型
            logger.warning(f"回退到基座模型: {base_model_name}")
            return await self._get_or_load_base_model(base_model_name)
    
    async def _get_or_load_base_model(self, model_name: str) -> tuple:
        """
        获取或加载基座模型
        
        Args:
            model_name: 模型名称
            
        Returns:
            (model, tokenizer)
        """
        try:
            # 检查缓存
            if model_name in self.base_model_cache:
                logger.info(f"从缓存加载基座模型: {model_name}")
                # 移到最后（LRU）
                self.base_model_cache.move_to_end(model_name)
                return self.base_model_cache[model_name]
            
            # 加载模型
            model_path = self.llm_dir / model_name
            
            if not model_path.exists():
                raise FileNotFoundError(f"基座模型不存在: {model_path}")
            
            logger.info(f"加载基座模型: {model_path}")
            
            # 加载 tokenizer
            if model_name in self.tokenizer_cache:
                tokenizer = self.tokenizer_cache[model_name]
            else:
                tokenizer = AutoTokenizer.from_pretrained(str(model_path))
                if tokenizer.pad_token is None:
                    tokenizer.pad_token = tokenizer.eos_token
                self.tokenizer_cache[model_name] = tokenizer
            
            # 加载模型
            model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True
            )
            model.eval()
            
            # 添加到缓存
            self.base_model_cache[model_name] = (model, tokenizer)
            
            # LRU 淘汰
            if len(self.base_model_cache) > self.max_base_models:
                oldest_key = next(iter(self.base_model_cache))
                logger.info(f"淘汰基座模型缓存: {oldest_key}")
                del self.base_model_cache[oldest_key]
            
            logger.info(f"基座模型加载完成: {model_name}")
            return model, tokenizer
            
        except Exception as e:
            logger.error(f"加载基座模型失败: {str(e)}")
            raise
    
    async def generate(
        self,
        model=None,
        tokenizer=None,
        prompt: Optional[str] = None,
        lora_model_id: Optional[int] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        base_model_name: Optional[str] = None,
        max_length: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs
    ) -> str:
        """
        使用模型生成响应
        
        Args:
            model: 模型（可选，直接推理模式）
            tokenizer: Tokenizer（可选，直接推理模式）
            prompt: 输入提示（可选，直接推理模式）
            lora_model_id: LoRA 模型 ID（可选，业务模式）
            messages: 对话消息列表（可选，业务模式）
            base_model_name: 基座模型名称（可选，业务模式）
            max_length: 最大生成长度
            temperature: 温度参数
            top_p: Top-p 采样参数
            
        Returns:
            生成的文本
        """
        try:
            # 兼容 chat_service 调用路径：传入 lora_model_id + messages
            if lora_model_id is not None and messages is not None:
                resolved_base_model_name = base_model_name or await self._resolve_base_model_name(lora_model_id)
                model, tokenizer = await self.load_lora_model(lora_model_id, resolved_base_model_name)
                prompt = self._build_prompt_from_messages(messages)

            if model is None or tokenizer is None or prompt is None:
                raise ValueError("generate 调用参数不完整，需要 model/tokenizer/prompt 或 lora_model_id/messages")

            return await self._generate_with_model(
                model=model,
                tokenizer=tokenizer,
                prompt=prompt,
                max_length=max_length,
                temperature=temperature,
                top_p=top_p,
                **kwargs
            )

        except Exception as e:
            logger.error(f"生成响应失败: {str(e)}")
            raise

    async def _generate_with_model(
        self,
        model,
        tokenizer,
        prompt: str,
        max_length: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs
    ) -> str:
        """使用已加载模型进行文本生成。"""
        try:
            # Tokenize 输入
            inputs = tokenizer(prompt, return_tensors="pt")
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
            
            # 生成
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_length=max_length,
                    temperature=temperature,
                    top_p=top_p,
                    do_sample=True,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                    **kwargs
                )
            
            # 解码
            generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # 移除输入部分
            if generated_text.startswith(prompt):
                generated_text = generated_text[len(prompt):].strip()
            
            return generated_text
            
        except Exception as e:
            logger.error(f"生成响应失败: {str(e)}")
            raise

    async def _resolve_base_model_name(self, lora_model_id: int) -> str:
        """根据 LoRA 模型 ID 获取对应基座模型名称。"""
        sql = "SELECT base_model_name FROM lora_models WHERE id = %s"
        result = await self.db.execute_query(sql, (lora_model_id,))
        if not result:
            raise ValueError(f"LoRA 模型不存在: {lora_model_id}")
        base_model_name = result[0].get("base_model_name")
        if not base_model_name:
            raise ValueError(f"LoRA 模型缺少 base_model_name: {lora_model_id}")
        return base_model_name

    def _build_prompt_from_messages(self, messages: List[Dict[str, str]]) -> str:
        """将消息列表转换为简单对话提示词。"""
        lines = []
        for message in messages:
            role = (message or {}).get("role", "user")
            content = (message or {}).get("content", "")
            role_text = "System" if role == "system" else "Assistant" if role == "assistant" else "User"
            lines.append(f"{role_text}: {content}")
        lines.append("Assistant:")
        return "\n\n".join(lines)
    
    async def unload_lora_model(self, lora_model_id: int, base_model_name: str):
        """
        卸载 LoRA 模型
        
        Args:
            lora_model_id: LoRA 模型 ID
            base_model_name: 基座模型名称
        """
        try:
            cache_key = f"{base_model_name}_{lora_model_id}"
            
            if cache_key in self.lora_model_cache:
                del self.lora_model_cache[cache_key]
                logger.info(f"LoRA 模型已卸载: {cache_key}")
            
        except Exception as e:
            logger.error(f"卸载 LoRA 模型失败: {str(e)}")
    
    def clear_cache(self):
        """清空所有缓存"""
        self.base_model_cache.clear()
        self.lora_model_cache.clear()
        self.tokenizer_cache.clear()
        logger.info("模型缓存已清空")


# 全局实例（懒加载）
_lora_inference_service_instance = None


def get_lora_inference_service() -> LoRAInferenceService:
    """获取 LoRA 推理服务单例（懒加载）"""
    global _lora_inference_service_instance
    if _lora_inference_service_instance is None:
        from app.core.database import db_manager

        _lora_inference_service_instance = LoRAInferenceService(db_manager)
    return _lora_inference_service_instance
