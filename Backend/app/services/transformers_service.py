"""
Transformers本地推理服务
支持动态模型加载、流式输出、量化加速
适配RTX 3060 6GB显存
"""
import os
import json
import asyncio
from typing import Optional, Dict, List, Any, AsyncGenerator
from pathlib import Path
import torch
import accelerate  # 显式导入accelerate
from transformers import (
    AutoModelForCausalLM, 
    AutoTokenizer,
    BitsAndBytesConfig,
    TextIteratorStreamer
)
from threading import Thread
from app.core.config import settings
from app.utils.logger import logger


class TransformersService:
    """Transformers本地推理服务"""
    
    def __init__(self):
        self.current_model = None
        self.current_tokenizer = None
        self.current_model_name = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.models_dir = Path(settings.llm.local_models_dir) / "LLM"
        
        # 6GB显存优化配置
        self.quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,  # INT4量化
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,  # 双重量化节省显存
            bnb_4bit_quant_type="nf4"  # NormalFloat4量化
            # 注意：bitsandbytes >= 0.43.2 已正确支持device_map="auto"与量化的配合
        )
        
        logger.info(f"TransformersService初始化完成 - 设备: {self.device}")
        if self.device == "cuda":
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            logger.info(f"GPU: {gpu_name}, 显存: {gpu_memory:.1f}GB")
    
    async def load_model(self, model_name: str, quantize: bool = True) -> bool:
        """
        加载模型到内存
        
        Args:
            model_name: 模型名称(文件夹名)
            quantize: 是否启用INT4量化(6GB显存必须启用)
        
        Returns:
            bool: 加载成功返回True
        """
        try:
            model_path = self.models_dir / model_name
            
            if not model_path.exists():
                raise FileNotFoundError(f"模型不存在: {model_path}")
            
            logger.info(f"开始加载模型: {model_name}")
            logger.info(f"量化模式: {'INT4' if quantize else '无'}")
            
            # 如果已加载相同模型,跳过
            if self.current_model_name == model_name:
                logger.info(f"模型{model_name}已加载,跳过重复加载")
                return True
            
            # 清理之前的模型
            if self.current_model is not None:
                logger.info(f"卸载旧模型: {self.current_model_name}")
                del self.current_model
                del self.current_tokenizer
                torch.cuda.empty_cache()
            
            # 加载tokenizer
            logger.info("加载Tokenizer...")
            try:
                self.current_tokenizer = AutoTokenizer.from_pretrained(
                    str(model_path),
                    trust_remote_code=True,
                    use_fast=True  # 优先使用fast tokenizer
                )
            except Exception as e:
                logger.warning(f"Fast tokenizer加载失败: {e}，尝试slow tokenizer")
                self.current_tokenizer = AutoTokenizer.from_pretrained(
                    str(model_path),
                    trust_remote_code=True,
                    use_fast=False
                )
            
            # 加载模型
            logger.info("加载模型权重...")
            load_kwargs = {
                "pretrained_model_name_or_path": str(model_path),
                "trust_remote_code": True,
                "torch_dtype": torch.float16,
                "low_cpu_mem_usage": True,
            }
            
            if quantize and self.device == "cuda":
                load_kwargs["quantization_config"] = self.quantization_config
                # 使用device_map="auto"，但限制只使用CUDA，不offload到CPU
                load_kwargs["device_map"] = "auto"
                load_kwargs["max_memory"] = {0: "5.5GiB", "cpu": "0GiB"}  # 限制CPU内存为0，强制全部在GPU
            elif self.device == "cuda":
                # 不量化时也使用device_map="auto"，但限制只使用CUDA
                load_kwargs["device_map"] = "auto"
                load_kwargs["max_memory"] = {0: "5.5GiB", "cpu": "0GiB"}
            
            self.current_model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
            
            # 设置为评估模式
            self.current_model.eval()
            
            self.current_model_name = model_name
            
            # 显示显存使用
            if self.device == "cuda":
                allocated = torch.cuda.memory_allocated(0) / 1024**3
                reserved = torch.cuda.memory_reserved(0) / 1024**3
                logger.info(f"显存使用: {allocated:.2f}GB 已分配, {reserved:.2f}GB 已保留")
            
            logger.info(f"模型{model_name}加载成功")
            return True
            
        except Exception as e:
            logger.error(f"加载模型失败: {e}", exc_info=True)
            self.current_model = None
            self.current_tokenizer = None
            self.current_model_name = None
            return False
    
    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False
    ):
        """
        聊天接口（支持流式和非流式）
        
        Args:
            model: 模型名称
            messages: 消息列表 [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大生成token数
            stream: 是否流式输出
        
        Returns:
            str: 模型回复（非流式）
            AsyncGenerator: 流式生成器（流式）
        """
        # 流式生成
        if stream:
            return self._chat_stream(model, messages, temperature, max_tokens)
        
        # 非流式生成
        try:
            # 确保模型已加载
            if self.current_model_name != model:
                success = await self.load_model(model)
                if not success:
                    raise RuntimeError(f"无法加载模型: {model}")
            
            # 构建prompt
            prompt = self._build_prompt(messages)
            
            # 编码输入
            logger.info(f"开始编码输入，prompt长度: {len(prompt)}")
            inputs = self.current_tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=4096
            )
            
            # 当使用device_map="auto"时，模型会分布在多个设备上
            # tokenizer默认输出CPU张量，需要移动到模型的主设备
            if hasattr(self.current_model, 'hf_device_map') and self.current_model.hf_device_map:
                # 获取模型的第一个设备（通常是主设备）
                first_device = list(self.current_model.hf_device_map.values())[0]
                inputs = {k: v.to(first_device) for k, v in inputs.items()}
                logger.info(f"device_map模式: 移动输入到主设备 {first_device}, input_ids shape: {inputs['input_ids'].shape}")
            elif self.device == "cuda":
                # 没有device_map但在CUDA上，直接移动到cuda:0
                inputs = {k: v.to("cuda:0") for k, v in inputs.items()}
                logger.info(f"CUDA模式: 移动输入到cuda:0, input_ids shape: {inputs['input_ids'].shape}")
            else:
                # CPU模式，不需要移动
                logger.info(f"CPU模式: 保持输入在CPU, input_ids shape: {inputs['input_ids'].shape}")
            
            logger.info(f"输入准备完成")

            
            # 生成配置
            generation_config = {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "do_sample": temperature > 0,
                "top_p": 0.9,
                "top_k": 50,
                "repetition_penalty": 1.1,
                "pad_token_id": self.current_tokenizer.eos_token_id,
            }
            
            logger.info(f"开始生成回复，max_new_tokens: {max_tokens}")
            # 同步生成(异步包装，添加超时保护)
            loop = asyncio.get_event_loop()
            
            try:
                with torch.no_grad():
                    # 设置60秒超时(根据max_tokens调整)
                    timeout = max(60, max_tokens // 10)
                    output_ids = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self.current_model.generate(
                                **inputs,
                                **generation_config
                            )
                        ),
                        timeout=timeout
                    )
            except asyncio.TimeoutError:
                logger.error(f"生成超时({timeout}秒)，返回部分结果")
                return "抱歉，生成回复超时。请尝试缩短问题或降低max_tokens。"
            
            logger.info("生成完成，开始解码")
            
            # 解码输出（注意：inputs现在是dict）
            input_length = inputs['input_ids'].shape[1]
            response = self.current_tokenizer.decode(
                output_ids[0][input_length:],
                skip_special_tokens=True
            )
            
            # 显存回收
            if self.device == "cuda":
                torch.cuda.empty_cache()
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"聊天生成失败: {e}", exc_info=True)
            raise
    
    async def _chat_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天生成
        
        Args:
            model: 模型名称
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大生成token数
            
        Yields:
            str: 生成的文本片段
        """
        try:
            # 确保模型已加载
            if self.current_model_name != model:
                success = await self.load_model(model)
                if not success:
                    raise RuntimeError(f"无法加载模型: {model}")
            
            # 构建prompt
            prompt = self._build_prompt(messages)
            
            # 编码输入
            logger.info(f"开始流式生成，prompt长度: {len(prompt)}")
            inputs = self.current_tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=4096
            )
            
            # 移动输入到正确的设备
            if hasattr(self.current_model, 'hf_device_map') and self.current_model.hf_device_map:
                first_device = list(self.current_model.hf_device_map.values())[0]
                inputs = {k: v.to(first_device) for k, v in inputs.items()}
            elif self.device == "cuda":
                inputs = {k: v.to("cuda:0") for k, v in inputs.items()}
            
            # 生成配置
            generation_config = {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "do_sample": temperature > 0,
                "top_p": 0.9,
                "top_k": 50,
                "repetition_penalty": 1.1,
                "pad_token_id": self.current_tokenizer.eos_token_id,
            }
            
            # 创建流式输出器
            streamer = TextIteratorStreamer(
                self.current_tokenizer,
                skip_prompt=True,
                skip_special_tokens=True
            )
            
            # 在后台线程中运行生成
            import asyncio
            from threading import Thread
            
            generation_kwargs = dict(
                **inputs,
                **generation_config,
                streamer=streamer
            )
            
            # 启动生成线程
            thread = Thread(target=self.current_model.generate, kwargs=generation_kwargs)
            thread.start()
            
            # 流式输出
            loop = asyncio.get_event_loop()
            for text_chunk in streamer:
                await asyncio.sleep(0)  # 让出控制权
                yield text_chunk
            
            # 等待线程结束
            thread.join()
            
            # 显存回收
            if self.device == "cuda":
                torch.cuda.empty_cache()
            
            logger.info("流式生成完成")
            
        except Exception as e:
            logger.error(f"流式生成失败: {e}", exc_info=True)
            raise
    
    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        """
        构建模型输入prompt
        支持多种对话模板
        """
        # 检测是否有apply_chat_template方法
        if hasattr(self.current_tokenizer, "apply_chat_template"):
            try:
                return self.current_tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True
                )
            except Exception as e:
                logger.warning(f"apply_chat_template失败: {e}, 使用默认模板")
        
        # 默认模板(适用于大多数模型)
        prompt = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                prompt += f"System: {content}\n\n"
            elif role == "user":
                prompt += f"User: {content}\n\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n\n"
        
        prompt += "Assistant: "
        return prompt
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """
        列出所有可用模型
        
        Returns:
            List[Dict]: 模型列表
        """
        try:
            models = []
            
            if not self.models_dir.exists():
                return models
            
            for model_dir in self.models_dir.iterdir():
                if not model_dir.is_dir():
                    continue
                
                # 检查是否是HuggingFace模型
                config_file = model_dir / "config.json"
                if not config_file.exists():
                    continue
                
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    
                    # 计算模型大小
                    model_size = sum(
                        f.stat().st_size 
                        for f in model_dir.rglob('*.safetensors')
                    ) / 1024**3  # GB
                    
                    models.append({
                        "id": model_dir.name,
                        "name": model_dir.name,
                        "architecture": config.get("architectures", ["Unknown"])[0],
                        "size_gb": round(model_size, 2),
                        "loaded": model_dir.name == self.current_model_name
                    })
                except Exception as e:
                    logger.warning(f"读取模型{model_dir.name}配置失败: {e}")
                    continue
            
            return models
            
        except Exception as e:
            logger.error(f"列出模型失败: {e}", exc_info=True)
            return []
    
    async def get_current_model(self) -> Optional[str]:
        """
        获取当前加载的模型名称
        
        Returns:
            Optional[str]: 模型名称,未加载返回None
        """
        return self.current_model_name
    
    async def check_health(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            Dict: 服务状态信息
        """
        try:
            health_info = {
                "status": "healthy",
                "device": self.device,
                "current_model": self.current_model_name,
                "models_available": len(await self.list_models())
            }
            
            if self.device == "cuda":
                health_info["gpu_name"] = torch.cuda.get_device_name(0)
                health_info["gpu_memory_allocated_gb"] = round(
                    torch.cuda.memory_allocated(0) / 1024**3, 2
                )
                health_info["gpu_memory_reserved_gb"] = round(
                    torch.cuda.memory_reserved(0) / 1024**3, 2
                )
            
            return health_info
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}", exc_info=True)
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def unload_model(self) -> bool:
        """
        卸载当前模型,释放显存
        
        Returns:
            bool: 卸载成功返回True
        """
        try:
            if self.current_model is None:
                logger.info("没有已加载的模型")
                return True
            
            logger.info(f"卸载模型: {self.current_model_name}")
            
            del self.current_model
            del self.current_tokenizer
            self.current_model = None
            self.current_tokenizer = None
            self.current_model_name = None
            
            if self.device == "cuda":
                torch.cuda.empty_cache()
                logger.info("显存已清理")
            
            return True
            
        except Exception as e:
            logger.error(f"卸载模型失败: {e}", exc_info=True)
            return False


# 延迟加载单例（避免启动时加载torch/CUDA）
_transformers_service_instance = None

def get_transformers_service() -> TransformersService:
    """获取TransformersService单例（延迟加载）
    
    首次调用时才初始化，避免Windows多进程启动时的CUDA冲突
    """
    global _transformers_service_instance
    if _transformers_service_instance is None:
        _transformers_service_instance = TransformersService()
    return _transformers_service_instance
