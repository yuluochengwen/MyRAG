"""LoRA 训练服务"""
import asyncio
import json
import os
import shutil
import torch
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
import uuid
import time

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    BitsAndBytesConfig
)
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from datasets import Dataset

from app.core.database import DatabaseManager
from app.models.lora_training_job import LoRATrainingJob
from app.services.lora.dataset_validator_service import DatasetValidatorService
from app.services.lora.lora_service import LoRAService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LoRATrainingService:
    """LoRA 训练引擎"""
    
    def __init__(self, db_manager: DatabaseManager, ws_manager=None):
        self.db = db_manager
        self.ws_manager = ws_manager
        self.training_queue = asyncio.Queue(maxsize=1)
        self.current_job_id = None
        self.training_lock = asyncio.Lock()
        self.lora_service = LoRAService(db_manager)
        self.validator = DatasetValidatorService()
        
        # 目录配置
        self.lora_dir = Path("Models/LoRA")
        self.temp_data_dir = Path("data/training_data/temp")
        self.log_dir = Path("data/logs")
        
        # 确保目录存在
        self.lora_dir.mkdir(parents=True, exist_ok=True)
        self.temp_data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    async def submit_training_job(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        提交训练任务
        
        Args:
            config: 训练配置
                - base_model_name: 基座模型名称
                - lora_name: LoRA 权重名称
                - training_mode: 训练模式 (lora/qlora)
                - dataset_file: 数据集文件路径
                - parameters: 训练参数
                
        Returns:
            {
                "job_id": int,
                "status": str,
                "message": str,
                "client_id": str
            }
        """
        try:
            # 1. 训练前验证
            validation_result = await self._validate_training_config(config)
            if not validation_result["valid"]:
                return {
                    "job_id": None,
                    "status": "error",
                    "message": validation_result["message"],
                    "client_id": None
                }
            
            # 2. 创建训练任务记录
            job_id = await self._create_training_job(config)
            if not job_id:
                return {
                    "job_id": None,
                    "status": "error",
                    "message": "创建训练任务失败",
                    "client_id": None
                }
            
            # 3. 生成客户端 ID（用于 WebSocket）
            client_id = str(uuid.uuid4())
            
            # 4. 检查是否有正在进行的训练任务
            async with self.training_lock:
                if self.current_job_id is not None:
                    # 有任务正在训练，新任务进入 pending 状态
                    await self._update_job_status(job_id, "pending")
                    logger.info(f"训练任务进入队列: job_id={job_id}")
                    return {
                        "job_id": job_id,
                        "status": "pending",
                        "message": "训练任务已加入队列，等待执行",
                        "client_id": client_id
                    }
                else:
                    # 没有任务在训练，立即开始
                    self.current_job_id = job_id
                    
                    # 启动异步训练任务
                    asyncio.create_task(self._execute_training_wrapper(job_id, client_id))
                    
                    logger.info(f"训练任务已提交: job_id={job_id}")
                    return {
                        "job_id": job_id,
                        "status": "training",
                        "message": "训练任务已开始",
                        "client_id": client_id
                    }
            
        except Exception as e:
            logger.error(f"提交训练任务失败: {str(e)}")
            raise
    
    async def _validate_training_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        训练前验证
        
        Returns:
            {"valid": bool, "message": str}
        """
        try:
            # 1. 验证基座模型存在
            base_model_name = config.get("base_model_name")
            if not base_model_name:
                return {"valid": False, "message": "缺少基座模型名称"}
            
            # TODO: 验证基座模型是否存在于本地
            # 这里简化处理，实际应该检查 Models/LLM/ 目录
            
            # 2. 验证训练数据格式
            dataset_file = config.get("dataset_file")
            if not dataset_file or not Path(dataset_file).exists():
                return {"valid": False, "message": "训练数据文件不存在"}
            
            validation_result = self.validator.validate_dataset(dataset_file)
            if not validation_result["valid"]:
                error_msg = "; ".join(validation_result["errors"][:3])
                return {"valid": False, "message": f"训练数据格式错误: {error_msg}"}
            
            # 3. 验证数据集不为空
            if validation_result["sample_count"] == 0:
                return {"valid": False, "message": "训练数据集为空"}
            
            # 4. 验证数据集大小限制
            if validation_result["sample_count"] > 10000:
                return {"valid": False, "message": f"训练数据集样本数量超过限制: {validation_result['sample_count']} > 10000"}
            
            # 5. 验证 LoRA 名称未被使用
            lora_name = config.get("lora_name")
            if not lora_name:
                return {"valid": False, "message": "缺少 LoRA 权重名称"}
            
            name_exists = await self.lora_service.check_lora_name_exists(lora_name)
            if name_exists:
                return {"valid": False, "message": f"LoRA 名称已存在: {lora_name}"}
            
            # 6. 验证没有正在进行的训练任务（单任务队列）
            # 这个在 submit_training_job 中处理，这里只是检查
            
            return {"valid": True, "message": "验证通过"}
            
        except Exception as e:
            logger.error(f"训练配置验证失败: {str(e)}")
            return {"valid": False, "message": f"验证失败: {str(e)}"}
    
    async def _create_training_job(self, config: Dict[str, Any]) -> Optional[int]:
        """
        创建训练任务记录
        
        Returns:
            job_id
        """
        try:
            # 提取配置
            base_model_name = config["base_model_name"]
            lora_name = config["lora_name"]
            training_mode = config.get("training_mode", "qlora")
            dataset_file = config["dataset_file"]
            parameters = config.get("parameters", {})
            
            # 验证数据集格式
            validation_result = self.validator.validate_dataset(dataset_file)
            dataset_format = validation_result["format"]
            
            # 获取训练轮数
            total_epochs = parameters.get("num_train_epochs", 3)
            
            # 生成日志文件路径
            log_file_path = str(self.log_dir / f"lora_training_{{job_id}}.log")
            
            # 插入数据库
            sql = """
                INSERT INTO lora_training_jobs 
                (base_model_name, dataset_path, dataset_format, training_mode, 
                 parameters, status, total_epochs, log_file_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            job_id = await self.db.execute_insert(
                sql,
                (base_model_name, dataset_file, dataset_format, training_mode,
                 json.dumps(parameters), "pending", total_epochs, log_file_path)
            )
            
            if job_id:
                # 更新日志文件路径（包含实际的 job_id）
                actual_log_path = str(self.log_dir / f"lora_training_{job_id}.log")
                sql_update = "UPDATE lora_training_jobs SET log_file_path = %s WHERE id = %s"
                await self.db.execute_update(sql_update, (actual_log_path, job_id))
                
                logger.info(f"训练任务记录创建成功: job_id={job_id}")
                return job_id
            
            return None
            
        except Exception as e:
            logger.error(f"创建训练任务记录失败: {str(e)}")
            raise
    
    async def _update_job_status(
        self,
        job_id: int,
        status: str,
        progress: float = None,
        current_epoch: int = None,
        error_message: str = None
    ):
        """更新任务状态"""
        try:
            updates = ["status = %s"]
            params = [status]
            
            if progress is not None:
                updates.append("progress = %s")
                params.append(progress)
            
            if current_epoch is not None:
                updates.append("current_epoch = %s")
                params.append(current_epoch)
            
            if error_message is not None:
                updates.append("error_message = %s")
                params.append(error_message)
            
            if status == "training":
                updates.append("started_at = NOW()")
            elif status in ["completed", "failed", "cancelled"]:
                updates.append("completed_at = NOW()")
            
            params.append(job_id)
            
            sql = f"UPDATE lora_training_jobs SET {', '.join(updates)} WHERE id = %s"
            await self.db.execute_update(sql, tuple(params))
            
        except Exception as e:
            logger.error(f"更新任务状态失败: {str(e)}")
    
    async def _execute_training_wrapper(self, job_id: int, client_id: str):
        """训练任务包装器（处理异常）"""
        try:
            await self._execute_training(job_id, client_id)
        except Exception as e:
            logger.error(f"训练任务执行失败: job_id={job_id}, error={str(e)}")
            await self._update_job_status(job_id, "failed", error_message=str(e))
            
            # 发送错误消息
            if self.ws_manager:
                await self.ws_manager.send_training_error(client_id, job_id, str(e))
        finally:
            # 释放训练锁
            async with self.training_lock:
                self.current_job_id = None
            
            # 检查队列中是否有待处理的任务
            await self._process_next_job()
    
    async def _execute_training(self, job_id: int, client_id: str):
        """
        执行训练任务（核心逻辑）
        """
        logger.info(f"开始执行训练任务: job_id={job_id}")
        
        # 更新状态为 training
        await self._update_job_status(job_id, "training", progress=0.0, current_epoch=0)
        
        # 发送开始消息
        if self.ws_manager:
            await self.ws_manager.send_training_log(client_id, job_id, "训练开始...")
        
        try:
            # 1. 获取任务配置
            job = await self.get_training_job(job_id)
            if not job:
                raise Exception("训练任务不存在")
            
            config = json.loads(job.parameters) if isinstance(job.parameters, str) else job.parameters
            
            # 2. 准备训练数据
            if self.ws_manager:
                await self.ws_manager.send_training_log(client_id, job_id, "准备训练数据...")
            
            train_dataset = await self._prepare_training_data(
                job.dataset_path,
                job.dataset_format,
                job.base_model_name,
                config
            )
            
            # 3. 加载模型和创建 LoRA 配置
            if self.ws_manager:
                await self.ws_manager.send_training_log(client_id, job_id, "加载基座模型...")
            
            model, tokenizer = await self._load_base_model(
                job.base_model_name,
                job.training_mode,
                config
            )
            
            # 4. 创建 LoRA 配置并应用
            if self.ws_manager:
                await self.ws_manager.send_training_log(client_id, job_id, "配置 LoRA...")
            
            model = await self._apply_lora_config(model, job.training_mode, config)
            
            # 5. 执行训练
            if self.ws_manager:
                await self.ws_manager.send_training_log(client_id, job_id, "开始训练...")
            
            await self._train_model(
                model,
                tokenizer,
                train_dataset,
                job_id,
                client_id,
                config
            )
            
            # 6. 保存 LoRA 权重
            if self.ws_manager:
                await self.ws_manager.send_training_log(client_id, job_id, "保存 LoRA 权重...")
            
            lora_model_id = await self._save_lora_weights(
                model,
                job_id,
                config.get("lora_name"),
                job.base_model_name,
                config
            )
            
            # 7. 清理临时文件
            await self._cleanup_temp_files(job.dataset_path)
            
            # 8. 更新任务状态
            await self._update_job_status(job_id, "completed", progress=100.0)
            
            # 9. 发送完成消息
            if self.ws_manager:
                await self.ws_manager.send_training_complete(client_id, job_id)
            
            logger.info(f"训练任务完成: job_id={job_id}, lora_model_id={lora_model_id}")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"训练任务执行失败: job_id={job_id}, error={error_msg}")
            
            # 检查是否是 OOM 错误
            if "out of memory" in error_msg.lower() or "oom" in error_msg.lower():
                error_msg = "显存不足！建议使用 QLoRA 模式或减小 batch_size"
            
            await self._update_job_status(job_id, "failed", error_message=error_msg)
            
            # 发送错误消息
            if self.ws_manager:
                await self.ws_manager.send_training_error(client_id, job_id, error_msg)
            
            raise
    
    async def _prepare_training_data(
        self,
        dataset_path: str,
        dataset_format: str,
        base_model_name: str,
        config: Dict[str, Any]
    ) -> Dataset:
        """
        准备训练数据
        
        将 Alpaca 或 Conversation 格式转换为统一的训练格式
        """
        try:
            # 读取数据集
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 根据格式转换数据
            if dataset_format == "alpaca":
                texts = self._convert_alpaca_format(data)
            elif dataset_format == "conversation":
                texts = self._convert_conversation_format(data)
            else:
                raise ValueError(f"不支持的数据格式: {dataset_format}")
            
            # 创建 Dataset
            dataset = Dataset.from_dict({"text": texts})
            
            logger.info(f"训练数据准备完成: {len(texts)} 条样本")
            return dataset
            
        except Exception as e:
            logger.error(f"准备训练数据失败: {str(e)}")
            raise
    
    def _convert_alpaca_format(self, data: List[Dict]) -> List[str]:
        """转换 Alpaca 格式数据"""
        texts = []
        for item in data:
            instruction = item.get("instruction", "")
            input_text = item.get("input", "")
            output = item.get("output", "")
            
            if input_text:
                text = f"### Instruction:\n{instruction}\n\n### Input:\n{input_text}\n\n### Response:\n{output}"
            else:
                text = f"### Instruction:\n{instruction}\n\n### Response:\n{output}"
            
            texts.append(text)
        
        return texts
    
    def _convert_conversation_format(self, data: List[Dict]) -> List[str]:
        """转换 Conversation 格式数据"""
        texts = []
        for item in data:
            conversations = item.get("conversations", [])
            
            conversation_text = ""
            for msg in conversations:
                role = msg.get("from", "")
                content = msg.get("value", "")
                
                if role == "human":
                    conversation_text += f"### Human:\n{content}\n\n"
                elif role == "gpt":
                    conversation_text += f"### Assistant:\n{content}\n\n"
            
            if conversation_text:
                texts.append(conversation_text.strip())
        
        return texts
    
    async def _load_base_model(
        self,
        model_name: str,
        training_mode: str,
        config: Dict[str, Any]
    ):
        """
        加载基座模型
        """
        try:
            model_path = Path("Models/LLM") / model_name
            
            if not model_path.exists():
                raise FileNotFoundError(f"基座模型不存在: {model_path}")
            
            # 加载 tokenizer
            tokenizer = AutoTokenizer.from_pretrained(str(model_path))
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            
            # 根据训练模式加载模型
            if training_mode == "qlora":
                # QLoRA: 使用 4-bit 量化
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True
                )
                
                model = AutoModelForCausalLM.from_pretrained(
                    str(model_path),
                    quantization_config=bnb_config,
                    device_map="auto",
                    trust_remote_code=True
                )
                
                # 准备模型用于 k-bit 训练
                model = prepare_model_for_kbit_training(model)
                
            else:
                # LoRA: 标准加载
                model = AutoModelForCausalLM.from_pretrained(
                    str(model_path),
                    torch_dtype=torch.float16,
                    device_map="auto",
                    trust_remote_code=True
                )
            
            logger.info(f"基座模型加载完成: {model_name}, 模式: {training_mode}")
            return model, tokenizer
            
        except Exception as e:
            logger.error(f"加载基座模型失败: {str(e)}")
            raise
    
    async def _apply_lora_config(
        self,
        model,
        training_mode: str,
        config: Dict[str, Any]
    ):
        """
        创建并应用 LoRA 配置
        """
        try:
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=config.get("lora_rank", 8),
                lora_alpha=config.get("lora_alpha", 16),
                lora_dropout=config.get("lora_dropout", 0.05),
                target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],  # 常见的目标模块
                bias="none"
            )
            
            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()
            
            logger.info("LoRA 配置应用完成")
            return model
            
        except Exception as e:
            logger.error(f"应用 LoRA 配置失败: {str(e)}")
            raise
    
    async def _train_model(
        self,
        model,
        tokenizer,
        dataset: Dataset,
        job_id: int,
        client_id: str,
        config: Dict[str, Any]
    ):
        """
        执行模型训练
        """
        try:
            # Tokenize 数据集
            def tokenize_function(examples):
                return tokenizer(
                    examples["text"],
                    truncation=True,
                    max_length=config.get("max_seq_length", 512),
                    padding="max_length"
                )
            
            tokenized_dataset = dataset.map(
                tokenize_function,
                batched=True,
                remove_columns=dataset.column_names
            )
            
            # 训练参数
            output_dir = self.temp_data_dir / f"training_{job_id}"
            output_dir.mkdir(exist_ok=True)
            
            training_args = TrainingArguments(
                output_dir=str(output_dir),
                num_train_epochs=config.get("num_train_epochs", 3),
                per_device_train_batch_size=config.get("per_device_train_batch_size", 4),
                learning_rate=config.get("learning_rate", 2e-4),
                logging_steps=10,
                save_strategy="epoch",
                fp16=True,
                gradient_accumulation_steps=config.get("gradient_accumulation_steps", 1),
                warmup_steps=config.get("warmup_steps", 100),
                report_to="none"  # 不使用外部报告工具
            )
            
            # 数据整理器
            data_collator = DataCollatorForLanguageModeling(
                tokenizer=tokenizer,
                mlm=False
            )
            
            # 创建 Trainer
            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=tokenized_dataset,
                data_collator=data_collator
            )
            
            # 开始训练
            train_result = trainer.train()
            
            logger.info(f"训练完成: {train_result}")
            
        except Exception as e:
            logger.error(f"模型训练失败: {str(e)}")
            raise
    
    async def _save_lora_weights(
        self,
        model,
        job_id: int,
        lora_name: str,
        base_model_name: str,
        config: Dict[str, Any]
    ) -> int:
        """
        保存 LoRA 权重
        """
        try:
            # 创建保存目录
            lora_path = self.lora_dir / lora_name
            lora_path.mkdir(parents=True, exist_ok=True)
            
            # 保存 LoRA 权重
            model.save_pretrained(str(lora_path))
            
            # 保存训练参数
            training_args_path = lora_path / "training_args.json"
            with open(training_args_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # 计算文件大小
            file_size = sum(f.stat().st_size for f in lora_path.rglob('*') if f.is_file())
            
            # 创建数据库记录
            sql = """
                INSERT INTO lora_models 
                (name, base_model_name, file_path, file_size, training_job_id, 
                 lora_rank, lora_alpha, description, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            lora_model_id = await self.db.execute_insert(
                sql,
                (
                    lora_name,
                    base_model_name,
                    str(lora_path),
                    file_size,
                    job_id,
                    config.get("lora_rank", 8),
                    config.get("lora_alpha", 16),
                    config.get("description", ""),
                    "active"
                )
            )
            
            # 更新训练任务的 lora_model_id
            sql_update = "UPDATE lora_training_jobs SET lora_model_id = %s WHERE id = %s"
            await self.db.execute_update(sql_update, (lora_model_id, job_id))
            
            logger.info(f"LoRA 权重保存完成: {lora_path}, model_id={lora_model_id}")
            return lora_model_id
            
        except Exception as e:
            logger.error(f"保存 LoRA 权重失败: {str(e)}")
            raise
    
    async def _cleanup_temp_files(self, dataset_path: str):
        """清理临时文件"""
        try:
            # 如果数据集在临时目录中，删除它
            if self.temp_data_dir.as_posix() in dataset_path:
                Path(dataset_path).unlink(missing_ok=True)
                logger.info(f"临时文件已清理: {dataset_path}")
        except Exception as e:
            logger.warning(f"清理临时文件失败: {str(e)}")
    
    
    async def _process_next_job(self):
        """处理队列中的下一个任务"""
        try:
            # 查询 pending 状态的任务
            sql = """
                SELECT id FROM lora_training_jobs 
                WHERE status = 'pending' 
                ORDER BY created_at ASC 
                LIMIT 1
            """
            result = await self.db.execute_query(sql)
            
            if result:
                next_job_id = result[0]['id']
                client_id = str(uuid.uuid4())  # 生成新的客户端 ID
                
                async with self.training_lock:
                    self.current_job_id = next_job_id
                
                # 启动训练
                asyncio.create_task(self._execute_training_wrapper(next_job_id, client_id))
                logger.info(f"开始处理队列中的任务: job_id={next_job_id}")
                
        except Exception as e:
            logger.error(f"处理下一个任务失败: {str(e)}")
    
    async def cancel_training(self, job_id: int) -> Dict[str, Any]:
        """
        取消训练任务
        
        Args:
            job_id: 任务 ID
            
        Returns:
            取消结果
        """
        try:
            # 检查任务状态
            sql = "SELECT status FROM lora_training_jobs WHERE id = %s"
            result = await self.db.execute_query(sql, (job_id,))
            
            if not result:
                return {"success": False, "message": "任务不存在"}
            
            status = result[0]['status']
            
            if status not in ["pending", "training"]:
                return {"success": False, "message": f"任务状态不允许取消: {status}"}
            
            # 更新状态为 cancelled
            await self._update_job_status(job_id, "cancelled")
            
            # TODO: 如果任务正在训练，需要中断训练进程
            # 这需要更复杂的进程管理机制
            
            logger.info(f"训练任务已取消: job_id={job_id}")
            return {"success": True, "message": "训练任务已取消"}
            
        except Exception as e:
            logger.error(f"取消训练任务失败: {str(e)}")
            raise
    
    async def get_training_job(self, job_id: int) -> Optional[LoRATrainingJob]:
        """获取训练任务详情"""
        try:
            sql = "SELECT * FROM lora_training_jobs WHERE id = %s"
            result = await self.db.execute_query(sql, (job_id,))
            
            if result:
                return LoRATrainingJob.from_dict(result[0])
            
            return None
            
        except Exception as e:
            logger.error(f"获取训练任务失败: {str(e)}")
            raise
    
    async def list_training_jobs(
        self,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> list:
        """获取训练任务列表"""
        try:
            if status:
                sql = """
                    SELECT * FROM lora_training_jobs 
                    WHERE status = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                result = await self.db.execute_query(sql, (status, limit, skip))
            else:
                sql = """
                    SELECT * FROM lora_training_jobs 
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                result = await self.db.execute_query(sql, (limit, skip))
            
            jobs = [LoRATrainingJob.from_dict(row) for row in result]
            return jobs
            
        except Exception as e:
            logger.error(f"获取训练任务列表失败: {str(e)}")
            raise
