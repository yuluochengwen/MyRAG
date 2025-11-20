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
            # LoRA 参数
            "lora_rank": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "target_modules": ["q_proj", "v_proj", "k_proj", "o_proj"],
            
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
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=params['lora_rank'],
                lora_alpha=params['lora_alpha'],
                lora_dropout=params['lora_dropout'],
                target_modules=params['target_modules'],
                bias="none"
            )
            
            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()
            
            logger.info("LoRA 配置完成")
            self._update_task_status(task_id, 'running', progress=25.0, message="LoRA 配置完成")
            
            # 4. 加载数据集
            self._update_task_status(task_id, 'running', progress=30.0, message="正在加载数据集...")
            train_dataset = self._load_dataset(task['dataset_file'], task['dataset_type'], tokenizer, params['max_seq_length'])
            
            logger.info(f"数据集加载完成，样本数: {len(train_dataset)}")
            self._update_task_status(task_id, 'running', progress=40.0, message=f"数据集加载完成 ({len(train_dataset)} 样本)")
            
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
            
            # 8. 保存模型
            self._update_task_status(task_id, 'running', progress=95.0, message="保存模型...")
            trainer.save_model(str(output_path))
            tokenizer.save_pretrained(str(output_path))
            
            logger.info(f"训练完成，模型已保存到: {output_path}")
            
            # 9. 更新状态为完成
            self._update_task_status(
                task_id,
                'completed',
                progress=100.0,
                current_epoch=params['num_epochs'],
                message="训练完成"
            )
            
        except Exception as e:
            logger.error(f"训练失败: {e}", exc_info=True)
            self._update_task_status(
                task_id,
                'failed',
                message=f"训练失败: {str(e)}"
            )
    
    def _load_dataset(self, dataset_file: str, dataset_type: str, tokenizer, max_length: int):
        """加载并预处理数据集"""
        dataset_path = Path(dataset_file)
        
        if dataset_type == "alpaca":
            # Alpaca 格式: {"instruction": "", "input": "", "output": ""}
            dataset = load_dataset("json", data_files=str(dataset_path), split="train")
            
            def format_alpaca(example):
                if example.get("input"):
                    prompt = f"### Instruction:\n{example['instruction']}\n\n### Input:\n{example['input']}\n\n### Response:\n"
                else:
                    prompt = f"### Instruction:\n{example['instruction']}\n\n### Response:\n"
                
                text = prompt + example['output']
                
                tokenized = tokenizer(
                    text,
                    truncation=True,
                    max_length=max_length,
                    padding="max_length"
                )
                tokenized["labels"] = tokenized["input_ids"].copy()
                return tokenized
            
            dataset = dataset.map(format_alpaca, remove_columns=dataset.column_names)
            
        elif dataset_type == "sharegpt":
            # ShareGPT 格式: {"conversations": [{"from": "human", "value": ""}, {"from": "gpt", "value": ""}]}
            dataset = load_dataset("json", data_files=str(dataset_path), split="train")
            
            def format_sharegpt(example):
                text = ""
                for conv in example['conversations']:
                    role = "User" if conv['from'] == 'human' else "Assistant"
                    text += f"{role}: {conv['value']}\n\n"
                
                tokenized = tokenizer(
                    text,
                    truncation=True,
                    max_length=max_length,
                    padding="max_length"
                )
                tokenized["labels"] = tokenized["input_ids"].copy()
                return tokenized
            
            dataset = dataset.map(format_sharegpt, remove_columns=dataset.column_names)
            
        else:
            raise ValueError(f"不支持的数据集类型: {dataset_type}")
        
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
