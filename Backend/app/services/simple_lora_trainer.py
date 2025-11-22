"""
简化的 LoRA 训练服务
使用 Hugging Face PEFT 进行自动化训练
"""
import os
import json
import torch
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType
)
from datasets import load_dataset
import pandas as pd

from app.core.database import DatabaseManager
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SimpleLoRATrainer:
    """简化的 LoRA 训练器"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.base_models_dir = Path(settings.file.upload_dir).parent / "Models" / "LLM"
        self.output_dir = Path(settings.file.upload_dir).parent / "Models" / "LoRA"
        self.datasets_dir = Path(settings.file.upload_dir).parent / "TrainingData"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        
        # 训练任务状态
        self.training_tasks = {}
        
    def get_default_params(self) -> Dict[str, Any]:
        """获取默认训练参数（针对 RTX 3060 6GB 优化）"""
        return {
            # LoRA 参数（target_modules 将在训练时自动检测）
            "lora_rank": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "target_modules": "auto",  # 改为 auto，自动检测
            
            # 训练参数
            "num_epochs": 3,
            "batch_size": 4,
            "gradient_accumulation_steps": 4,  # 有效 batch_size = 4*4 = 16
            "learning_rate": 2e-4,
            "warmup_steps": 100,
            "max_seq_length": 512,
            
            # 优化参数
            "use_4bit": True,
            "use_gradient_checkpointing": True,
            "logging_steps": 10,
            "save_steps": 100,
        }
    
    def _detect_target_modules(self, model) -> list:
        """
        自动检测模型的 attention 层名称（用于 LoRA）
        
        Args:
            model: 加载的模型
            
        Returns:
            target_modules 列表
        """
        # 常见的模型架构及其对应的 target_modules
        architecture_mapping = {
            "LlamaForCausalLM": ["q_proj", "v_proj", "k_proj", "o_proj"],
            "QWenLMHeadModel": ["c_attn"],  # Qwen 1.x
            "Qwen2ForCausalLM": ["q_proj", "v_proj", "k_proj", "o_proj"],  # Qwen 2.x
            "ChatGLMModel": ["query_key_value"],
            "BaichuanForCausalLM": ["W_pack"],
            "InternLMForCausalLM": ["q_proj", "v_proj", "k_proj", "o_proj"],
            "MistralForCausalLM": ["q_proj", "v_proj", "k_proj", "o_proj"],
            "GPT2LMHeadModel": ["c_attn"],
        }
        
        # 获取模型类型
        model_type = model.__class__.__name__
        logger.info(f"检测到模型类型: {model_type}")
        
        # 从预定义映射中获取
        if model_type in architecture_mapping:
            target_modules = architecture_mapping[model_type]
            logger.info(f"使用预定义的 target_modules: {target_modules}")
            return target_modules
        
        # 如果没有预定义，尝试自动检测
        logger.info("未找到预定义映射，开始自动检测...")
        
        # 收集所有包含 "attn" 或 "attention" 的层名称
        attention_layers = set()
        for name, module in model.named_modules():
            if any(keyword in name.lower() for keyword in ["attn", "attention", "query", "key", "value"]):
                # 提取最后一个组件名称
                layer_name = name.split('.')[-1]
                if layer_name and not layer_name.startswith('_'):
                    attention_layers.add(layer_name)
        
        if attention_layers:
            target_modules = sorted(list(attention_layers))
            logger.info(f"自动检测到的 attention 层: {target_modules}")
            return target_modules
        
        # 如果还是检测不到，使用 LLaMA 默认值
        logger.warning("无法自动检测，使用 LLaMA 默认值")
        return ["q_proj", "v_proj", "k_proj", "o_proj"]
    
    async def create_training_task(
        self,
        task_name: str,
        base_model_name: str,
        dataset_file: str,
        dataset_type: str = "alpaca",
        custom_params: Optional[Dict] = None
    ) -> int:
        """
        创建训练任务
        
        Args:
            task_name: 任务名称
            base_model_name: 基座模型名称
            dataset_file: 数据集文件路径
            dataset_type: 数据集格式 (alpaca, sharegpt, csv)
            custom_params: 自定义参数（可选）
        
        Returns:
            任务 ID
        """
        # 获取训练参数
        params = self.get_default_params()
        if custom_params:
            params.update(custom_params)
        
        # 生成输出目录名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"{task_name}_{timestamp}"
        output_path = self.output_dir / output_name
        
        # 插入数据库
        with self.db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO simple_lora_tasks 
                    (task_name, base_model, dataset_file, dataset_type, 
                     output_path, training_params, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                """, (
                    task_name,
                    base_model_name,
                    dataset_file,
                    dataset_type,
                    str(output_path),
                    json.dumps(params)
                ))
                conn.commit()
                task_id = cursor.lastrowid
        
        logger.info(f"创建训练任务: ID={task_id}, 名称={task_name}")
        return task_id
    
    async def start_training(self, task_id: int):
        """启动训练任务（后台运行）"""
        # 更新状态
        self._update_task_status(task_id, 'running', current_epoch=0, progress=0.0)
        
        # 在后台线程中运行训练
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self._train_worker, task_id)
        
        logger.info(f"训练任务 {task_id} 已在后台启动")
    
    def _train_worker(self, task_id: int):
        """训练工作线程"""
        try:
            # 获取任务信息
            task = self._get_task(task_id)
            if not task:
                raise Exception(f"任务不存在: {task_id}")
            
            params = json.loads(task['training_params'])
            
            logger.info(f"开始训练任务 {task_id}: {task['task_name']}")
            
            # 1. 加载基座模型
            self._update_task_status(task_id, 'running', progress=5.0, message="正在加载基座模型...")
            base_model_path = self.base_models_dir / task['base_model']
            
            model = AutoModelForCausalLM.from_pretrained(
                str(base_model_path),
                load_in_4bit=params['use_4bit'],
                device_map="auto",
                trust_remote_code=True
            )
            
            tokenizer = AutoTokenizer.from_pretrained(
                str(base_model_path),
                trust_remote_code=True
            )
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            
            logger.info("基座模型加载完成")
            self._update_task_status(task_id, 'running', progress=15.0, message="基座模型加载完成")
            
            # 2. 准备模型（4-bit 训练）
            if params['use_4bit']:
                model = prepare_model_for_kbit_training(model)
            
            # 3. 配置 LoRA
            self._update_task_status(task_id, 'running', progress=20.0, message="配置 LoRA...")
            
            # 自动检测 target_modules
            target_modules = params.get('target_modules', 'auto')
            if target_modules == 'auto' or not target_modules:
                target_modules = self._detect_target_modules(model)
                logger.info(f"自动检测的 target_modules: {target_modules}")
            else:
                logger.info(f"使用指定的 target_modules: {target_modules}")
            
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=params['lora_rank'],
                lora_alpha=params['lora_alpha'],
                lora_dropout=params['lora_dropout'],
                target_modules=target_modules,
                bias="none"
            )
            
            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()
            
            logger.info("LoRA 配置完成")
            self._update_task_status(task_id, 'running', progress=25.0, message="LoRA 配置完成")
            
            # 4. 加载数据集
            self._update_task_status(task_id, 'running', progress=30.0, message="正在加载数据集...")
            train_dataset = self._load_dataset(task['dataset_file'], task['dataset_type'], tokenizer, params['max_seq_length'])
            
            dataset_size = len(train_dataset)
            logger.info(f"数据集加载完成，样本数: {dataset_size}")
            self._update_task_status(task_id, 'running', progress=40.0, message=f"数据集加载完成 ({dataset_size} 样本)")
            
            # 动态调整 Epoch (针对小数据集优化)
            original_epochs = params['num_epochs']
            if dataset_size < 200:
                params['num_epochs'] = max(original_epochs, 15)  # 极小数据集：至少15轮
                logger.info(f"检测到极小数据集 ({dataset_size} < 200)，自动将 Epoch 调整为 {params['num_epochs']}")
            elif dataset_size < 1000:
                params['num_epochs'] = max(original_epochs, 5)   # 小数据集：至少5轮
                logger.info(f"检测到小数据集 ({dataset_size} < 1000)，自动将 Epoch 调整为 {params['num_epochs']}")
            
            # 5. 配置训练参数
            output_path = Path(task['output_path'])
            output_path.mkdir(parents=True, exist_ok=True)
            
            training_args = TrainingArguments(
                output_dir=str(output_path),
                num_train_epochs=params['num_epochs'],
                per_device_train_batch_size=params['batch_size'],
                gradient_accumulation_steps=params['gradient_accumulation_steps'],
                learning_rate=params['learning_rate'],
                warmup_steps=params['warmup_steps'],
                logging_steps=params['logging_steps'],
                save_steps=params['save_steps'],
                save_total_limit=2,
                fp16=True,
                gradient_checkpointing=params['use_gradient_checkpointing'],
                optim="adamw_torch",
                report_to="none",
            )
            
            # 6. 创建训练器
            data_collator = DataCollatorForLanguageModeling(
                tokenizer=tokenizer,
                mlm=False
            )
            
            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=train_dataset,
                data_collator=data_collator,
            )
            
            # 7. 开始训练
            self._update_task_status(task_id, 'running', progress=50.0, current_epoch=1, message="开始训练...")
            logger.info("开始训练...")
            
            trainer.train()
            
            # 8. 保存 LoRA 适配器（重要：只保存 LoRA 权重，不保存完整模型）
            self._update_task_status(task_id, 'running', progress=95.0, message="保存 LoRA 适配器...")
            
            # 保存 LoRA 适配器（使用 PEFT 的保存方法）
            model.save_pretrained(str(output_path))
            tokenizer.save_pretrained(str(output_path))
            
            # 验证保存的文件
            adapter_config = output_path / "adapter_config.json"
            adapter_model = output_path / "adapter_model.safetensors"
            if not adapter_config.exists():
                logger.warning(f"adapter_config.json 未找到，检查保存")
            if not adapter_model.exists():
                adapter_model_bin = output_path / "adapter_model.bin"
                if not adapter_model_bin.exists():
                    logger.error("LoRA 权重文件未保存！")
            
            logger.info(f"✅ LoRA 训练完成，适配器已保存到: {output_path}")
            logger.info(f"   - adapter_config.json: {adapter_config.exists()}")
            logger.info(f"   - adapter_model: {adapter_model.exists() or (output_path / 'adapter_model.bin').exists()}")
            
            # 9. 更新状态为完成
            completion_message = f"训练完成！LoRA适配器已保存到: {output_path.name}"
            self._update_task_status(
                task_id,
                'completed',
                progress=100.0,
                current_epoch=params['num_epochs'],
                message=completion_message
            )
            
            logger.info(f"====== 训练任务 {task_id} 完成 ======")
            logger.info(f"输出路径: {output_path}")
            logger.info(f"请前往【模型管理】页面扫描 LoRA 模型以使用")
            
        except Exception as e:
            logger.error(f"训练失败: {e}", exc_info=True)
            self._update_task_status(
                task_id,
                'failed',
                message=f"训练失败: {str(e)}"
            )
    
    def _load_dataset(self, dataset_file: str, dataset_type: str, tokenizer, max_length: int):
        """加载并预处理数据集（修复版：适配 Chat 模板 & 自动处理特殊 Token）"""
        dataset_path = Path(dataset_file)
        
        # 1. 加载原始数据
        dataset = load_dataset("json", data_files=str(dataset_path), split="train")
        
        # 2. 定义格式化函数
        def format_dataset(example):
            # 将不同格式统一转换为 Messages 格式
            messages = []
            
            if dataset_type == "alpaca":
                # Alpaca: instruction + input -> User, output -> Assistant
                user_content = example['instruction']
                if example.get('input'):
                    user_content += f"\n\n{example['input']}"
                
                messages = [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": example['output']}
                ]
                
            elif dataset_type == "sharegpt":
                # ShareGPT: 已经是对话格式，需要转换 role 名称
                for conv in example['conversations']:
                    role = "user" if conv['from'] == 'human' else "assistant"
                    messages.append({"role": role, "content": conv['value']})
            
            # 3. 构建 Prompt 和 Full Text 以计算 Mask
            # 这是关键：确保训练时的 Prompt 与推理时完全一致，且只对回答计算 Loss
            try:
                if hasattr(tokenizer, "apply_chat_template"):
                    # A. 获取完整的对话文本
                    full_text = tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=False
                    )
                    
                    # B. 获取仅包含 Prompt 的文本 (用于计算 Mask 长度)
                    # 假设最后一条是 Assistant 回复，我们需要 Mask 掉它之前的所有内容
                    prompt_messages = messages[:-1] 
                    prompt_text = tokenizer.apply_chat_template(
                        prompt_messages,
                        tokenize=False,
                        add_generation_prompt=True # 添加生成提示符 (如 <|assistant|>)
                    )
                else:
                    # 降级：使用通用格式 (User/Assistant)
                    full_text = ""
                    prompt_text = ""
                    for i, msg in enumerate(messages):
                        role = "User" if msg['role'] == 'user' else "Assistant"
                        content = f"{role}: {msg['content']}\n\n"
                        full_text += content
                        if i < len(messages) - 1:
                            prompt_text += content
                    prompt_text += "Assistant: "
            except Exception as e:
                # 再次降级
                full_text = ""
                prompt_text = ""
                for msg in messages:
                    role = "User" if msg['role'] == 'user' else "Assistant"
                    full_text += f"{role}: {msg['content']}\n\n"

            # 4. Tokenize
            # 自动添加特殊 token (BOS/EOS)
            model_inputs = tokenizer(
                full_text,
                max_length=max_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt"
            )
            
            input_ids = model_inputs["input_ids"][0]
            attention_mask = model_inputs["attention_mask"][0]
            labels = input_ids.clone()
            
            # 5. 计算 Mask (Data Masking) - 关键修复
            # 将 Prompt 部分的 Label 设为 -100，只让模型学习 Assistant 的回复
            if prompt_text:
                # Tokenize prompt 部分来获取长度
                prompt_inputs = tokenizer(
                    prompt_text,
                    max_length=max_length,
                    truncation=True,
                    return_tensors="pt",
                    add_special_tokens=True # 保持一致
                )
                prompt_len = prompt_inputs["input_ids"].shape[1]
                
                # 确保不越界
                if prompt_len < len(labels):
                    labels[:prompt_len] = -100
            
            # 将 padding 部分的 label 设为 -100
            if tokenizer.pad_token_id is not None:
                labels[input_ids == tokenizer.pad_token_id] = -100
                
            return {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "labels": labels
            }

        # 3. 应用格式化
        dataset = dataset.map(format_dataset, remove_columns=dataset.column_names)
        return dataset
    
    def _update_task_status(
        self,
        task_id: int,
        status: str,
        progress: float = None,
        current_epoch: int = None,
        message: str = None
    ):
        """更新任务状态"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    update_fields = ["status = %s"]
                    params = [status]
                    
                    if progress is not None:
                        update_fields.append("progress = %s")
                        params.append(progress)
                    
                    if current_epoch is not None:
                        update_fields.append("current_epoch = %s")
                        params.append(current_epoch)
                    
                    if message is not None:
                        update_fields.append("message = %s")
                        params.append(message)
                    
                    if status == 'completed':
                        update_fields.append("completed_at = NOW()")
                    
                    params.append(task_id)
                    
                    sql = f"UPDATE simple_lora_tasks SET {', '.join(update_fields)} WHERE id = %s"
                    cursor.execute(sql, params)
                    conn.commit()
        except Exception as e:
            logger.error(f"更新任务状态失败: {e}")
    
    def _get_task(self, task_id: int) -> Optional[Dict]:
        """获取任务信息"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM simple_lora_tasks WHERE id = %s", (task_id,))
                return cursor.fetchone()
    
    def get_task_status(self, task_id: int) -> Dict[str, Any]:
        """获取任务状态（用于前端查询）"""
        task = self._get_task(task_id)
        if not task:
            return {"error": "任务不存在"}
        
        return {
            "task_id": task['id'],
            "task_name": task['task_name'],
            "status": task['status'],
            "progress": float(task['progress']) if task['progress'] else 0.0,
            "current_epoch": task['current_epoch'] or 0,
            "message": task['message'],
            "created_at": task['created_at'].isoformat() if task['created_at'] else None,
            "completed_at": task['completed_at'].isoformat() if task['completed_at'] else None
        }
    
    def list_tasks(self) -> list:
        """列出所有任务"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM simple_lora_tasks 
                    ORDER BY created_at DESC 
                    LIMIT 50
                """)
                return cursor.fetchall()
