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
    AutoModelForImageTextToText,
    AutoProcessor,
    AutoTokenizer,
    BitsAndBytesConfig,
    TextIteratorStreamer,
    __version__ as transformers_version
)
from transformers.models.auto.configuration_auto import CONFIG_MAPPING
from transformers.models.auto import modeling_auto
from threading import Thread
from app.core.config import settings
from app.utils.logger import logger


MODEL_FOR_CAUSAL_LM_MAPPING_NAMES = getattr(modeling_auto, "MODEL_FOR_CAUSAL_LM_MAPPING_NAMES", {})
MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING_NAMES = getattr(modeling_auto, "MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING_NAMES", {})
MODEL_FOR_VISION_2_SEQ_MAPPING_NAMES = getattr(modeling_auto, "MODEL_FOR_VISION_2_SEQ_MAPPING_NAMES", {})


class TransformersService:
    """Transformers本地推理服务"""
    
    def __init__(self):
        self.current_model = None
        self.current_tokenizer = None
        self.current_processor = None
        self.current_model_name = None
        self.current_model_loader = "causal_lm"
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
    
    def _estimate_model_size(self, model_path: Path) -> float:
        """
        估算 INT4 量化后的模型大小（GB）
        
        Args:
            model_path: 模型目录路径
            
        Returns:
            float: 估算的模型大小（GB）
        """
        try:
            config_file = model_path / "config.json"
            if config_file.exists():
                with open(config_file) as f:
                    config = json.load(f)
                
                # 从配置估算参数量
                vocab_size = config.get("vocab_size", 32000)
                hidden_size = config.get("hidden_size", 2048)
                num_layers = config.get("num_hidden_layers", 24)
                
                # 粗略估算参数量（billion）
                params_b = (vocab_size * hidden_size + 
                           num_layers * hidden_size * hidden_size * 4) / 1e9
                
                # INT4: 0.5 bytes per parameter
                size_gb = params_b * 0.5
                return size_gb
        except Exception as e:
            logger.warning(f"无法从配置估算模型大小: {e}")
        
        # 降级：计算 safetensors 文件大小
        try:
            total_size = sum(
                f.stat().st_size 
                for f in model_path.rglob('*.safetensors')
            ) / 1024**3
            # INT4 约为原始大小的 1/4
            return total_size * 0.25
        except:
            return 0.0
    
    def _post_process_response(self, response: str, model_name: str) -> str:
        """
        后处理模型输出，移除推理模型的思考过程
        支持多种思考过程格式
        
        Args:
            response: 原始模型输出
            model_name: 模型名称
            
        Returns:
            str: 处理后的输出
        """
        import re
        
        # 检测推理模型（DeepSeek-R1、R1-Distill 等）
        is_reasoning_model = any(keyword in model_name.lower() 
                                for keyword in ["deepseek-r1", "r1-distill", "-r1", "reasoning"])
        
        if is_reasoning_model:
            # 方法 1: 移除各种思考过程标签
            # <think>...</think>
            response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
            # [思考]...[/思考]
            response = re.sub(r'\[思考\].*?\[/思考\]', '', response, flags=re.DOTALL)
            # <reasoning>...</reasoning>
            response = re.sub(r'<reasoning>.*?</reasoning>', '', response, flags=re.DOTALL)
            
            # 方法 2: 如果有多段，保留最长的非思考段落
            if '\n\n' in response:
                parts = [p.strip() for p in response.split('\n\n') 
                        if p.strip() and not any(p.strip().startswith(tag) 
                                                for tag in ['<', '['])]
                if parts:
                    response = max(parts, key=len)
            
            # 清理多余空白
            response = re.sub(r'\n{3,}', '\n\n', response).strip()
        
        return response
    
    def _inject_system_instruction(self, messages: List[Dict[str, str]], instruction: str) -> List[Dict[str, str]]:
        """
        将指令注入到 system 消息
        
        Args:
            messages: 原始消息列表
            instruction: 要注入的指令
            
        Returns:
            List[Dict]: 注入后的消息列表
        """
        messages = messages.copy()
        has_system = any(msg["role"] == "system" for msg in messages)
        
        if has_system:
            # 追加到现有 system 消息
            for msg in messages:
                if msg["role"] == "system":
                    msg["content"] = f"{msg['content']}\n\n{instruction}"
                    break
        else:
            # 添加新的 system 消息
            messages.insert(0, {"role": "system", "content": instruction})
        
        return messages

    def _read_model_meta(self, model_path: Path) -> Dict[str, Any]:
        config_file = model_path / "config.json"
        if not config_file.exists():
            raise FileNotFoundError(f"模型目录缺少 config.json: {config_file}")
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _resolve_model_path(self, model_name: str) -> Optional[Path]:
        """将模型名解析为实际可加载目录（兼容 HuggingFace cache 目录结构）。"""
        if not model_name:
            return None

        normalized = model_name.replace("\\", "/").strip("/")

        # 1) 直接目录（兼容传入相对路径）
        direct_path = self.models_dir / normalized
        if direct_path.exists() and (direct_path / "config.json").exists():
            return direct_path

        # 2) HuggingFace cache 目录: models--org--repo
        cache_dir_name = f"models--{normalized.replace('/', '--')}"
        cache_dir = self.models_dir / cache_dir_name
        if cache_dir.exists() and cache_dir.is_dir():
            snapshots_dir = cache_dir / "snapshots"
            if snapshots_dir.exists() and snapshots_dir.is_dir():
                snapshot_dirs = [d for d in snapshots_dir.iterdir() if d.is_dir()]
                snapshot_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                for snapshot_dir in snapshot_dirs:
                    if (snapshot_dir / "config.json").exists():
                        return snapshot_dir
            if (cache_dir / "config.json").exists():
                return cache_dir

        # 3) 传入了 cache 目录名本身
        raw_cache_dir = self.models_dir / normalized
        if raw_cache_dir.exists() and raw_cache_dir.is_dir():
            snapshots_dir = raw_cache_dir / "snapshots"
            if snapshots_dir.exists() and snapshots_dir.is_dir():
                snapshot_dirs = [d for d in snapshots_dir.iterdir() if d.is_dir()]
                snapshot_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                for snapshot_dir in snapshot_dirs:
                    if (snapshot_dir / "config.json").exists():
                        return snapshot_dir
            if (raw_cache_dir / "config.json").exists():
                return raw_cache_dir

        return None

    def _resolve_model_loader(self, model_meta: Dict[str, Any]) -> str:
        model_type = str(model_meta.get("model_type") or "").strip()
        architectures = model_meta.get("architectures") or []
        auto_map = model_meta.get("auto_map") or {}

        if any("ForConditionalGeneration" in str(a) for a in architectures):
            return "image_text"
        if any("ForCausalLM" in str(a) for a in architectures):
            return "causal_lm"

        if isinstance(auto_map, dict):
            if auto_map.get("AutoModelForImageTextToText") or auto_map.get("AutoModelForVision2Seq"):
                return "image_text"
            if auto_map.get("AutoModelForCausalLM"):
                return "causal_lm"

        if model_type in MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING_NAMES.keys() or model_type in MODEL_FOR_VISION_2_SEQ_MAPPING_NAMES.keys():
            return "image_text"
        return "causal_lm"

    def _validate_model_compatibility(self, model_path: Path, model_meta: Dict[str, Any], loader_kind: str) -> Optional[str]:
        """
        检查模型与当前加载器的兼容性。

        Returns:
            Optional[str]: 不兼容原因（可直接用于报错），兼容则返回 None
        """
        model_type = str(model_meta.get("model_type") or "").strip()
        architectures = model_meta.get("architectures") or []
        auto_map = model_meta.get("auto_map") or {}
        target_transformers = str(model_meta.get("transformers_version") or "unknown")
        arch_name = str(architectures[0]) if architectures else "unknown"

        # 配置层支持检查：model_type 是否被当前 transformers 识别
        # 若存在 auto_map 且提供 AutoConfig，可通过 trust_remote_code 走动态配置加载
        has_auto_config = isinstance(auto_map, dict) and bool(auto_map.get("AutoConfig"))
        if model_type and model_type not in CONFIG_MAPPING.keys() and not has_auto_config:
            return (
                f"模型类型不受当前 Transformers 支持: model_type={model_type}, "
                f"当前Transformers={transformers_version}, 模型期望版本={target_transformers}. "
                "这不是路径错误。请升级Transformers或改用受支持的本地模型。"
            )

        if loader_kind == "causal_lm":
            has_auto_causal = isinstance(auto_map, dict) and bool(auto_map.get("AutoModelForCausalLM"))
            if model_type and model_type not in MODEL_FOR_CAUSAL_LM_MAPPING_NAMES.keys() and not has_auto_causal:
                return (
                    f"模型类型不在 AutoModelForCausalLM 支持列表中: model_type={model_type}, architecture={arch_name}. "
                    "请改用文本对话模型（如 Qwen2/Qwen3 CausalLM）或切换到支持该架构的加载方式。"
                )
        elif loader_kind == "image_text":
            has_auto_image_text = isinstance(auto_map, dict) and (
                bool(auto_map.get("AutoModelForImageTextToText"))
                or bool(auto_map.get("AutoModelForVision2Seq"))
            )
            if (
                model_type
                and model_type not in MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING_NAMES.keys()
                and model_type not in MODEL_FOR_VISION_2_SEQ_MAPPING_NAMES.keys()
                and not has_auto_image_text
            ):
                return (
                    f"模型类型不在 ImageText/Vision2Seq 支持列表中: model_type={model_type}, architecture={arch_name}. "
                    "该模型需要更新版 Transformers 或模型目录中提供 auto_map 远程代码入口。"
                )

        return None

    def _get_chat_template_tokenizer(self):
        if self.current_tokenizer is not None:
            return self.current_tokenizer
        if self.current_processor is not None and hasattr(self.current_processor, "tokenizer"):
            return self.current_processor.tokenizer
        return None

    def _prepare_model_inputs(self, messages: List[Dict[str, str]], max_length: int = 4096) -> Dict[str, torch.Tensor]:
        prompt = self._build_prompt(messages)
        tokenizer = self._get_chat_template_tokenizer()

        if self.current_model_loader == "image_text" and self.current_processor is not None:
            logger.info(f"开始编码输入(image_text)，prompt长度: {len(prompt)}")
            try:
                return self.current_processor(
                    text=prompt,
                    return_tensors="pt",
                    truncation=True,
                    max_length=max_length
                )
            except TypeError:
                return self.current_processor(text=prompt, return_tensors="pt")

        if tokenizer is None:
            raise RuntimeError("当前模型缺少 tokenizer/processor，无法编码输入")

        logger.info(f"开始编码输入(causal_lm)，prompt长度: {len(prompt)}")
        return tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=max_length
        )

    def _move_inputs_to_model_device(self, inputs: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        if hasattr(self.current_model, 'hf_device_map') and self.current_model.hf_device_map:
            first_device = list(self.current_model.hf_device_map.values())[0]
            moved = {k: v.to(first_device) for k, v in inputs.items()}
            logger.info(f"device_map模式: 移动输入到主设备 {first_device}")
            return moved
        if self.device == "cuda":
            moved = {k: v.to("cuda:0") for k, v in inputs.items()}
            logger.info("CUDA模式: 移动输入到cuda:0")
            return moved
        logger.info("CPU模式: 保持输入在CPU")
        return inputs

    def _decode_generated_text(self, output_ids: Any, inputs: Dict[str, torch.Tensor], model_name: str) -> str:
        tokenizer = self._get_chat_template_tokenizer()
        if tokenizer is None:
            raise RuntimeError("当前模型缺少 tokenizer，无法解码输出")

        input_length = inputs['input_ids'].shape[1] if 'input_ids' in inputs else 0
        response = tokenizer.decode(
            output_ids[0][input_length:],
            skip_special_tokens=True
        )
        return self._post_process_response(response, model_name)
    
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
            model_path = self._resolve_model_path(model_name)
            
            if model_path is None:
                raise FileNotFoundError(
                    f"模型不存在: {self.models_dir / model_name}"
                )

            model_meta = self._read_model_meta(model_path)
            loader_kind = self._resolve_model_loader(model_meta)

            compatibility_error = self._validate_model_compatibility(model_path, model_meta, loader_kind)
            if compatibility_error:
                raise ValueError(
                    f"模型兼容性检查失败: {compatibility_error} (loader={loader_kind}, model={model_name}, path={model_path})"
                )
            
            logger.info(f"开始加载模型: {model_name} (resolved_path={model_path})")
            logger.info(f"量化模式: {'INT4' if quantize else '无'}")
            
            # 如果已加载相同模型,跳过
            if self.current_model_name == model_name:
                logger.info(f"模型{model_name}已加载,跳过重复加载")
                return True
            
            # 清理之前的模型
            if self.current_model is not None:
                logger.info(f"卸载旧模型: {self.current_model_name}")
                del self.current_model
                if self.current_tokenizer is not None:
                    del self.current_tokenizer
                if self.current_processor is not None:
                    del self.current_processor
                torch.cuda.empty_cache()
                self.current_tokenizer = None
                self.current_processor = None
            
            # 加载tokenizer/processor
            if loader_kind == "image_text":
                logger.info("加载Processor...")
                self.current_processor = AutoProcessor.from_pretrained(
                    str(model_path),
                    trust_remote_code=True
                )
                if hasattr(self.current_processor, "tokenizer"):
                    self.current_tokenizer = self.current_processor.tokenizer
            else:
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
                "dtype": torch.float16,
                "low_cpu_mem_usage": True,
            }
            
            # 尝试启用 Flash Attention（如果可用）
            try:
                import flash_attn
                load_kwargs["attn_implementation"] = "flash_attention_2"
                logger.info("✓ Flash Attention 2 已启用")
            except ImportError:
                logger.info("Flash Attention 不可用，使用默认实现")
            
            if quantize and self.device == "cuda":
                load_kwargs["quantization_config"] = self.quantization_config
                
                # 估算模型大小，优化小模型加载
                model_size_gb = self._estimate_model_size(model_path)
                logger.info(f"估算模型大小: {model_size_gb:.2f} GB (INT4量化后)")
                
                if model_size_gb < 2.0:  # 小模型（< 2GB）
                    logger.info("小模型检测，直接加载到 GPU（避免 device_map 开销）")
                    load_kwargs["device_map"] = None  # 不使用 device_map
                else:
                    logger.info("大模型检测，使用 device_map=auto")
                    load_kwargs["device_map"] = "auto"
                    load_kwargs["max_memory"] = {0: "5.5GiB", "cpu": "0GiB"}
            elif self.device == "cuda":
                load_kwargs["device_map"] = "auto"
                load_kwargs["max_memory"] = {0: "5.5GiB", "cpu": "0GiB"}
            
            # 显存监控：加载前
            if self.device == "cuda":
                before_allocated = torch.cuda.memory_allocated(0) / 1024**3
                before_reserved = torch.cuda.memory_reserved(0) / 1024**3
                logger.info(f"加载前显存: {before_allocated:.2f}GB 已分配, {before_reserved:.2f}GB 已保留")
            
            if loader_kind == "image_text":
                self.current_model = AutoModelForImageTextToText.from_pretrained(**load_kwargs)
            else:
                self.current_model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
            
            # 设置为评估模式
            self.current_model.eval()
            
            self.current_model_name = model_name
            self.current_model_loader = loader_kind
            
            # 显示显存使用（加载后）
            if self.device == "cuda":
                after_allocated = torch.cuda.memory_allocated(0) / 1024**3
                after_reserved = torch.cuda.memory_reserved(0) / 1024**3
                delta_allocated = after_allocated - before_allocated
                delta_reserved = after_reserved - before_reserved
                logger.info(f"加载后显存: {after_allocated:.2f}GB 已分配 (+{delta_allocated:.2f}GB), "
                           f"{after_reserved:.2f}GB 已保留 (+{delta_reserved:.2f}GB)")
                
                # 显存利用率
                total_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
                utilization = (after_allocated / total_memory) * 100
                logger.info(f"显存利用率: {utilization:.1f}% ({after_allocated:.2f}GB / {total_memory:.1f}GB)")
            
            logger.info(f"模型{model_name}加载成功，loader={loader_kind}")
            return True
            
        except Exception as e:
            logger.error(f"加载模型失败: {e}", exc_info=True)
            self.current_model = None
            self.current_tokenizer = None
            self.current_processor = None
            self.current_model_name = None
            self.current_model_loader = "causal_lm"
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
            
            inputs = self._prepare_model_inputs(messages, max_length=4096)
            inputs = self._move_inputs_to_model_device(inputs)
            
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
                    # 生成超时: 取配置基线与按token估算的较大值，避免长回答被过早中断
                    configured_timeout = max(
                        1,
                        int(getattr(settings.llm, "transformers_generation_timeout_seconds", 480))
                    )
                    assumed_tps = max(
                        0.1,
                        float(getattr(settings.llm, "transformers_assumed_tokens_per_second", 5.0))
                    )
                    estimated_timeout = max(60, int(max_tokens / assumed_tps))
                    timeout = max(configured_timeout, estimated_timeout)
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
            response = self._decode_generated_text(output_ids, inputs, model)
            
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
            
            inputs = self._prepare_model_inputs(messages, max_length=4096)
            inputs = self._move_inputs_to_model_device(inputs)
            
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
                self._get_chat_template_tokenizer(),
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
            
            # 流式输出（累积文本用于后处理）
            loop = asyncio.get_event_loop()
            accumulated_text = ""
            for text_chunk in streamer:
                await asyncio.sleep(0)  # 让出控制权
                accumulated_text += text_chunk
                # 实时后处理（移除可能的思考标签）
                processed_chunk = self._post_process_response(accumulated_text, model)
                if processed_chunk != accumulated_text:
                    # 有变化，说明遇到了思考标签，重新生成输出
                    accumulated_text = processed_chunk
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
        构建模型输入 Prompt（智能适配不同模型和任务）
        
        Args:
            messages: 消息列表
            
        Returns:
            str: 构建好的 prompt
        """
        tokenizer = self._get_chat_template_tokenizer()

        # 检测模型类型
        is_reasoning_model = (self.current_model_name and 
                             any(k in self.current_model_name.lower() 
                                 for k in ["deepseek-r1", "r1-distill", "-r1"]))
        
        # 为推理模型添加特殊指令
        if is_reasoning_model:
            # 检测任务类型（是否是 RAG 对话）
            is_rag_task = any("根据" in msg.get("content", "") or 
                            "文档" in msg.get("content", "") or
                            "检索" in msg.get("content", "")
                            for msg in messages if msg["role"] == "system")
            
            if is_rag_task:
                # RAG 任务：强调使用文档内容
                instruction = (
                    "请直接给出最终答案，不要输出思考过程。"
                    "严格基于检索到的文档内容回答，确保答案准确且有依据。"
                )
            else:
                # 普通对话：强调简洁
                instruction = (
                    "请直接回答问题，不要输出思考过程。"
                    "保持回答简洁、准确、自然。"
                )
            
            messages = self._inject_system_instruction(messages, instruction)
        
        # 尝试使用 tokenizer 的 chat_template
        if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
            try:
                return tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True
                )
            except Exception as e:
                logger.warning(f"apply_chat_template 失败: {e}, 使用默认模板")
        
        # 默认模板
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
            if self.current_tokenizer is not None:
                del self.current_tokenizer
            if self.current_processor is not None:
                del self.current_processor
            self.current_model = None
            self.current_tokenizer = None
            self.current_processor = None
            self.current_model_name = None
            self.current_model_loader = "causal_lm"
            
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
