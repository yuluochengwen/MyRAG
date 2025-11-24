# Backend服务层重构实施手册

> **版本**: v3.0 架构优化版  
> **创建时间**: 2025-01-26  
> **适用项目**: MyRAG知识库系统  
> **重构周期**: 12周  
> ⚠️ **重要说明**: 所有"简化"均为架构优化，**不删除任何业务功能**，仅通过消除重复代码、分层解耦实现代码减少  

---

## 📋 快速导航

| 章节 | 内容 | 时间 |
|------|------|------|
| [一、现状评估](#一现状评估) | 代码统计、问题识别、优先级 | - |
| [二、阶段0：准备](#二阶段0准备week-0) | 测试基准、环境准备 | Week 0 |
| [三、阶段1：基础层](#三阶段1基础层week-1-2) | DeviceManager, ModelLoader | Week 1-2 |
| [四、阶段2：模型层](#四阶段2模型层week-3-5) | LLM抽象、transformers拆分 | Week 3-5 |
| [五、阶段3：业务层](#五阶段3业务层week-6-8) | 检索策略、知识库重构 | Week 6-8 |
| [六、阶段4：应用层](#六阶段4应用层week-9-10) | RAG Pipeline、Agent | Week 9-10 |
| [七、阶段5：清理](#七阶段5清理week-11-12) | 删除旧代码、优化 | Week 11-12 |

---

## 一、现状评估

### 1.1 代码规模

**18个服务文件，总计6118行**（实际统计）

| 风险级别 | 文件 | 行数 | 核心问题 |
|---------|------|------|---------|
| 🔴 极高 | transformers_service.py | 776 | 7个职责混合（设备管理/模型加载/LoRA/提示词/生成） |
| 🔴 高 | chat_service.py | 561 | 5个职责混合（会话管理/RAG/流式输出/历史） |
| 🟡 中 | knowledge_base_service.py | 528 | CRUD+检索+向量化 |
| 🟡 中 | neo4j_graph_service.py | 513 | 图谱构建+查询 |
| 🟡 中 | simple_lora_trainer.py | 500 | 数据集处理+训练管理 |
| 🟢 低 | 其他13个文件 | 3240 | 相对可接受 |

### 1.2 核心问题（按优先级）

| 优先级 | 问题 | 影响文件 | 解决方案 | 阶段 |
|--------|------|---------|---------|------|
| **P0** | 设备管理重复4次 | transformers, embedding, lora_trainer, ollama | 创建DeviceManager | 1 |
| **P0** | 模型加载重复3次 | transformers, embedding, lora_trainer | 创建ModelLoader | 1 |
| **P1** | transformers_service过大 | transformers_service (835行) | 拆分为6个模块 | 2 |
| **P1** | 缺少LLM抽象层 | transformers, ollama | 定义BaseLLM接口 | 2 |
| **P2** | chat_service职责不清 | chat_service (624行) | 提取RAG Pipeline | 3 |
| **P2** | 检索策略分散 | 3个文件 | 策略模式重构 | 3 |
| **P3** | 工具类缺失 | entity_extraction等 | 创建JSONParser等 | 4 |

### 1.3 重构目标

**架构目标**（不影响功能）：
- ⬇️ 代码重复率: >25% → <10% (-60%) - 通过提取公共模块
- ⬇️ 最大文件: 835行 → 280行 (-66%) - 通过职责分离
- ⬆️ 模块化程度: 18个平铺文件 → 7大模块分类
- ⬆️ 测试覆盖率: 30% → 80% (+167%)
- ⬆️ 可扩展性: 插件化架构，易于添加新模型/检索策略

**代码量变化**（自然结果）：
- services层: 6118行 → 3881行 (-37%，因为重复代码移至core层）
- core层: 200行 → 2500行 (+2300行，新增基础设施）
- 净效果: 代码总量略增，但**质量大幅提升**

---

## 二、阶段0：准备 (Week 0)

### 目标
✅ 建立测试基准  
✅ 准备重构环境  
✅ 识别回滚点

### 任务清单

**T0.1 测试基准建立**
```bash
# 1. 运行现有测试
cd Backend
pytest app/tests/ --cov=app/services --cov-report=html

# 2. 记录性能基准
python benchmark/llm_latency.py  # 记录推理速度
python benchmark/memory_usage.py  # 记录内存占用

# 3. 保存结果
cp htmlcov docs/test_baseline_before.html
```

**T0.2 代码度量**
```bash
# 计算圈复杂度
radon cc app/services -a > docs/complexity_before.txt

# 代码重复分析
pylint app/services --disable=all --enable=duplicate-code > docs/duplication_before.txt
```

**T0.3 环境准备**
```bash
# 创建重构分支
git checkout -b refactor/service-layer-v2

# 配置自动化测试
# 每次提交自动运行测试
```

### 交付物
- ✅ `docs/test_baseline.md` - 测试基准报告
- ✅ `docs/code_metrics.md` - 代码度量报告
- ✅ Feature分支创建完成

---

## 三、阶段1：基础层 (Week 1-2)

### 目标
🎯 建立基础设施  
🎯 消除P0级别的重复代码  
🎯 为后续重构铺路

### Week 1: 设备管理与工具类

#### T1.1 创建DeviceManager（2天）

**代码示例**：
```python
# Backend/app/core/device/gpu_manager.py
from dataclasses import dataclass
import torch
from transformers import BitsAndBytesConfig

@dataclass
class DeviceInfo:
    device_type: str  # cuda/cpu
    device_name: str
    total_memory_gb: float
    allocated_memory_gb: float
    reserved_memory_gb: float

class DeviceManager:
    """统一的CUDA设备管理"""
    
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
    
    def get_device_info(self) -> DeviceInfo:
        """获取设备信息"""
        if self.device == "cpu":
            return DeviceInfo("cpu", "CPU", 0, 0, 0)
        return DeviceInfo(
            device_type="cuda",
            device_name=torch.cuda.get_device_name(0),
            total_memory_gb=torch.cuda.get_device_properties(0).total_memory / 1024**3,
            allocated_memory_gb=torch.cuda.memory_allocated(0) / 1024**3,
            reserved_memory_gb=torch.cuda.memory_reserved(0) / 1024**3
        )
    
    def get_quantization_config(self) -> BitsAndBytesConfig:
        """获取INT4量化配置"""
        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4"
        )
    
    def clear_cache(self):
        """清理显存缓存"""
        if self.device == "cuda":
            torch.cuda.empty_cache()
```

**测试代码**：
```python
# Backend/app/tests/test_device_manager.py
def test_device_manager_init():
    dm = DeviceManager()
    assert dm.device in ["cuda", "cpu"]

def test_get_device_info():
    dm = DeviceManager()
    info = dm.get_device_info()
    assert info.device_type in ["cuda", "cpu"]
    assert info.total_memory_gb >= 0
```

**替换旧代码**：
```python
# 在transformers_service.py, embedding_service.py等4个文件中替换：
# 旧代码：
# self.device = "cuda" if torch.cuda.is_available() else "cpu"

# 新代码：
from app.core.device.gpu_manager import DeviceManager
self.device_manager = DeviceManager()
self.device = self.device_manager.device
```

---

#### T1.2 创建基础工具类（3天）

**JSONParser - 统一JSON解析容错**：
```python
# Backend/app/core/utils/json_parser.py
import json
import re
from typing import Optional, Dict, Any

class JSONParser:
    """统一的JSON解析容错工具"""
    
    @staticmethod
    def extract_json(text: str, fallback: Optional[Dict] = None) -> Dict[str, Any]:
        """
        3层降级策略提取JSON
        
        Args:
            text: 可能包含JSON的文本
            fallback: 解析失败时返回的默认值
            
        Returns:
            解析后的字典
        """
        # 第1层：直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 第2层：提取代码块
        try:
            if '```json' in text:
                start = text.find('```json') + 7
                end = text.find('```', start)
                json_str = text[start:end].strip()
            elif '```' in text:
                start = text.find('```') + 3
                end = text.find('```', start)
                json_str = text[start:end].strip()
            else:
                raise ValueError("No code block found")
            
            return json.loads(json_str)
        except:
            pass
        
        # 第3层：查找{}
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end > 0:
                json_str = text[start:end]
                return json.loads(json_str)
        except:
            pass
        
        # 全部失败，返回fallback
        return fallback or {}
```

**PathResolver - 统一路径管理**：
```python
# Backend/app/core/utils/path_resolver.py
from pathlib import Path
from app.core.config import settings

class PathResolver:
    """统一的路径解析服务"""
    
    def __init__(self):
        self.base_dir = Path(settings.file.upload_dir).parent
    
    def get_model_path(self, model_type: str, model_name: str) -> Path:
        """
        获取模型路径
        
        Args:
            model_type: llm / embedding / lora
            model_name: 模型名称
            
        Returns:
            完整路径
        """
        type_map = {
            "llm": "Models/LLM",
            "embedding": "Models/Embedding",
            "lora": "Models/LoRA"
        }
        return self.base_dir / type_map[model_type] / model_name
    
    def get_kb_path(self, kb_id: int) -> Path:
        """获取知识库路径"""
        return self.base_dir / "KnowledgeBase" / f"kb_{kb_id}"
    
    def get_training_data_path(self, filename: str) -> Path:
        """获取训练数据路径"""
        return self.base_dir / "TrainingData" / filename
```

**ProcessManager - 进程管理**：
```python
# Backend/app/core/utils/process_manager.py
import subprocess
import psutil
import time
from typing import List, Optional, Dict, Any

class ProcessManager:
    """统一的进程生命周期管理"""
    
    def start_process(
        self,
        cmd: List[str],
        wait_time: int = 5,
        log_file: Optional[str] = None
    ) -> int:
        """
        启动进程并等待就绪
        
        Args:
            cmd: 命令列表
            wait_time: 等待时间（秒）
            log_file: 日志文件路径
            
        Returns:
            进程PID
        """
        # Windows特殊处理
        creation_flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP 
            if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') 
            else 0
        )
        
        # 打开日志文件
        log_handle = open(log_file, 'w') if log_file else subprocess.PIPE
        
        process = subprocess.Popen(
            cmd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags
        )
        
        # 等待进程启动
        time.sleep(wait_time)
        
        # 验证进程存在
        if not psutil.pid_exists(process.pid):
            raise RuntimeError(f"进程启动失败: PID {process.pid}")
        
        return process.pid
    
    def stop_process(self, pid: int, timeout: int = 10) -> bool:
        """
        优雅停止进程（terminate → wait → kill）
        
        Args:
            pid: 进程ID
            timeout: 超时时间（秒）
            
        Returns:
            是否成功停止
        """
        try:
            process = psutil.Process(pid)
            
            # 1. 尝试优雅终止
            process.terminate()
            
            # 2. 等待进程结束
            try:
                process.wait(timeout=timeout)
                return True
            except psutil.TimeoutExpired:
                # 3. 超时后强制杀死
                process.kill()
                return True
                
        except psutil.NoSuchProcess:
            return True  # 进程已不存在
        except Exception as e:
            return False
    
    def get_process_status(self, pid: int) -> Dict[str, Any]:
        """获取进程状态"""
        try:
            process = psutil.Process(pid)
            return {
                "pid": pid,
                "status": process.status(),
                "running": process.is_running(),
                "cpu_percent": process.cpu_percent(),
                "memory_mb": process.memory_info().rss / 1024 / 1024
            }
        except psutil.NoSuchProcess:
            return {"pid": pid, "running": False}
```

**TaskStateManager - 任务状态管理**：
```python
# Backend/app/core/utils/task_state_manager.py
from enum import Enum
from typing import Dict, List, Optional

class TaskState(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskStateManager:
    """统一的任务状态管理（带状态机验证）"""
    
    # 合法的状态转换
    TRANSITIONS = {
        TaskState.PENDING: [TaskState.RUNNING, TaskState.FAILED],
        TaskState.RUNNING: [TaskState.COMPLETED, TaskState.FAILED],
        TaskState.COMPLETED: [],  # 终态
        TaskState.FAILED: []       # 终态
    }
    
    def can_transition(
        self,
        from_state: TaskState,
        to_state: TaskState
    ) -> bool:
        """验证状态转换是否合法"""
        return to_state in self.TRANSITIONS.get(from_state, [])
    
    def update_task_status(
        self,
        db_connection,
        table_name: str,
        task_id: int,
        new_state: TaskState,
        **extra_fields
    ) -> bool:
        """
        更新任务状态（自动验证合法性）
        
        Args:
            db_connection: 数据库连接
            table_name: 表名
            task_id: 任务ID
            new_state: 新状态
            **extra_fields: 额外字段（progress, message等）
            
        Returns:
            是否更新成功
        """
        # 1. 获取当前状态
        with db_connection.cursor() as cursor:
            cursor.execute(
                f"SELECT status FROM {table_name} WHERE id = %s",
                (task_id,)
            )
            result = cursor.fetchone()
            if not result:
                return False
            
            current_state = TaskState(result['status'])
        
        # 2. 验证转换合法性
        if not self.can_transition(current_state, new_state):
            raise ValueError(
                f"非法状态转换: {current_state.value} → {new_state.value}"
            )
        
        # 3. 执行更新
        update_fields = ["status = %s"]
        params = [new_state.value]
        
        for field, value in extra_fields.items():
            update_fields.append(f"{field} = %s")
            params.append(value)
        
        # 添加时间戳
        if new_state == TaskState.COMPLETED:
            update_fields.append("completed_at = NOW()")
        
        params.append(task_id)
        
        with db_connection.cursor() as cursor:
            sql = f"UPDATE {table_name} SET {', '.join(update_fields)} WHERE id = %s"
            cursor.execute(sql, params)
            db_connection.commit()
        
        return True
```

---

### Week 2: 模型加载器

#### T1.3 创建ModelLoader（3天）

**代码示例**：
```python
# Backend/app/core/model/model_loader.py
from pathlib import Path
from typing import Optional, Tuple
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from app.core.device.gpu_manager import DeviceManager

class ModelLoader:
    """统一的模型加载器（支持普通/量化/LoRA）"""
    
    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager
        self.model_cache = {}  # 模型缓存
    
    async def load(
        self,
        model_path: Path,
        quantize: bool = True,
        lora_path: Optional[Path] = None
    ) -> Tuple:
        """
        统一的加载入口
        
        Args:
            model_path: 模型路径
            quantize: 是否量化
            lora_path: LoRA路径（可选）
            
        Returns:
            (model, tokenizer)
        """
        # 1. 加载tokenizer
        tokenizer = self._load_tokenizer(model_path)
        
        # 2. 加载基座模型
        model = self._load_base_model(model_path, quantize)
        
        # 3. 应用LoRA（如果有）
        if lora_path:
            model = self._apply_lora(model, lora_path)
        
        return model, tokenizer
    
    def _load_tokenizer(self, model_path: Path):
        """加载tokenizer（带降级）"""
        try:
            return AutoTokenizer.from_pretrained(
                str(model_path),
                trust_remote_code=True,
                use_fast=True
            )
        except Exception:
            return AutoTokenizer.from_pretrained(
                str(model_path),
                trust_remote_code=True,
                use_fast=False
            )
    
    def _load_base_model(self, model_path: Path, quantize: bool):
        """加载基座模型"""
        load_kwargs = {
            "pretrained_model_name_or_path": str(model_path),
            "trust_remote_code": True,
            "dtype": torch.float16,
            "low_cpu_mem_usage": True,
        }
        
        if quantize and self.device_manager.device == "cuda":
            load_kwargs["quantization_config"] = (
                self.device_manager.get_quantization_config()
            )
            load_kwargs["device_map"] = "auto"
            load_kwargs["max_memory"] = {0: "5.5GiB", "cpu": "0GiB"}
        
        model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
        model.eval()
        
        return model
    
    def _apply_lora(self, base_model, lora_path: Path):
        """应用LoRA适配器"""
        return PeftModel.from_pretrained(
            base_model,
            str(lora_path),
            dtype=torch.float16
        )
```

---

### 阶段1总结

**完成标准**：
- ✅ 所有新模块单元测试通过（覆盖率>80%）
- ✅ 在4个服务中成功替换设备管理代码
- ✅ 在3个服务中成功替换模型加载代码
- ✅ 性能基准测试通过（无下降）

**预期效果**：
- ⬇️ 代码重复率: 25% → 18% (-28%)
- ⬇️ 设备管理重复: 4处 → 1处 (-75%)
- ⬇️ 模型加载重复: 3处 → 1处 (-66%)

**下一步**：进入阶段2 - 模型服务层重构

---

## 四、阶段2：模型层 (Week 3-5)

### 目标
🎯 建立统一的LLM抽象层  
🎯 拆分transformers_service（835行 → 280行）  
🎯 实现模型服务的可插拔架构

### Week 3: LLM抽象接口

#### T2.1 定义BaseLLM接口（2天）

**核心接口设计**：
```python
# Backend/app/core/llm/base_llm.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, Optional, List
from dataclasses import dataclass

@dataclass
class LLMConfig:
    """LLM通用配置"""
    model_name: str
    temperature: float = 0.7
    max_new_tokens: int = 512
    top_p: float = 0.9
    top_k: int = 50
    repetition_penalty: float = 1.1

@dataclass
class Message:
    """消息结构"""
    role: str  # system/user/assistant
    content: str

class BaseLLM(ABC):
    """所有LLM服务的基类"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.model_name = config.model_name
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化模型（异步加载）
        
        Returns:
            是否成功
        """
        pass
    
    @abstractmethod
    async def generate(
        self,
        messages: List[Message],
        stream: bool = False,
        **kwargs
    ) -> str | AsyncGenerator[str, None]:
        """
        生成回复（支持流式/非流式）
        
        Args:
            messages: 对话历史
            stream: 是否流式输出
            **kwargs: 额外参数（覆盖config）
            
        Returns:
            完整回复 或 流式生成器
        """
        pass
    
    @abstractmethod
    async def get_model_info(self) -> Dict[str, Any]:
        """
        获取模型信息
        
        Returns:
            {
                "name": "模型名称",
                "type": "transformers/ollama/openai",
                "status": "loaded/loading/error",
                "device": "cuda/cpu",
                "memory_usage_mb": 1234,
                "loaded_adapters": ["lora1", "lora2"]  # 仅LoRA模型
            }
        """
        pass
    
    @abstractmethod
    async def cleanup(self):
        """清理资源（卸载模型）"""
        pass
    
    def _merge_config(self, **kwargs) -> Dict[str, Any]:
        """合并配置参数（kwargs优先）"""
        base = {
            "temperature": self.config.temperature,
            "max_new_tokens": self.config.max_new_tokens,
            "top_p": self.config.top_p,
            "top_k": self.config.top_k,
            "repetition_penalty": self.config.repetition_penalty
        }
        base.update(kwargs)
        return base
```

**测试用例**：
```python
# Backend/app/tests/test_base_llm.py
import pytest
from app.core.llm.base_llm import BaseLLM, LLMConfig, Message

class MockLLM(BaseLLM):
    """测试用的Mock实现"""
    
    async def initialize(self) -> bool:
        return True
    
    async def generate(self, messages, stream=False, **kwargs):
        if stream:
            async def gen():
                yield "Hello"
                yield " World"
            return gen()
        return "Hello World"
    
    async def get_model_info(self):
        return {
            "name": self.model_name,
            "type": "mock",
            "status": "loaded"
        }
    
    async def cleanup(self):
        pass

@pytest.mark.asyncio
async def test_llm_config_merge():
    config = LLMConfig(model_name="test", temperature=0.5)
    llm = MockLLM(config)
    
    merged = llm._merge_config(temperature=0.9, max_new_tokens=1024)
    assert merged["temperature"] == 0.9  # kwargs优先
    assert merged["max_new_tokens"] == 1024
    assert merged["top_p"] == 0.9  # 使用默认值

@pytest.mark.asyncio
async def test_llm_generate():
    config = LLMConfig(model_name="test")
    llm = MockLLM(config)
    
    messages = [Message(role="user", content="Hi")]
    response = await llm.generate(messages)
    assert response == "Hello World"
```

---

#### T2.2 实现OllamaLLM（1天）

**代码示例**：
```python
# Backend/app/core/llm/ollama_llm.py
import httpx
from typing import AsyncGenerator, List
from app.core.llm.base_llm import BaseLLM, Message

class OllamaLLM(BaseLLM):
    """Ollama LLM实现"""
    
    def __init__(self, config, base_url: str = "http://localhost:11434"):
        super().__init__(config)
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=300.0)
    
    async def initialize(self) -> bool:
        """检查Ollama是否在线"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            models = response.json().get("models", [])
            return any(m["name"] == self.model_name for m in models)
        except:
            return False
    
    async def generate(
        self,
        messages: List[Message],
        stream: bool = False,
        **kwargs
    ):
        """调用Ollama API"""
        gen_config = self._merge_config(**kwargs)
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "options": {
                "temperature": gen_config["temperature"],
                "num_predict": gen_config["max_new_tokens"],
                "top_p": gen_config["top_p"],
                "top_k": gen_config["top_k"],
                "repeat_penalty": gen_config["repetition_penalty"]
            }
        }
        
        if stream:
            return self._stream_generate(payload)
        else:
            return await self._sync_generate(payload)
    
    async def _sync_generate(self, payload: dict) -> str:
        """非流式生成"""
        response = await self.client.post(
            f"{self.base_url}/api/chat",
            json=payload
        )
        return response.json()["message"]["content"]
    
    async def _stream_generate(self, payload: dict) -> AsyncGenerator[str, None]:
        """流式生成"""
        async with self.client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload
        ) as response:
            async for line in response.aiter_lines():
                if line:
                    data = json.loads(line)
                    if "message" in data:
                        yield data["message"]["content"]
    
    async def get_model_info(self):
        """获取模型信息"""
        try:
            response = await self.client.post(
                f"{self.base_url}/api/show",
                json={"name": self.model_name}
            )
            info = response.json()
            return {
                "name": self.model_name,
                "type": "ollama",
                "status": "loaded",
                "parameters": info.get("parameters", "unknown"),
                "size_gb": info.get("size", 0) / 1024**3
            }
        except:
            return {"name": self.model_name, "type": "ollama", "status": "error"}
    
    async def cleanup(self):
        """关闭HTTP客户端"""
        await self.client.aclose()
```

---

#### T2.3 统一Embedding服务（2天）

**当前问题**：
- `embedding_service.py` (334行)：Transformers embedding实现
- `ollama_embedding_service.py` (204行)：Ollama embedding实现
- **重复代码**：两个服务有相似的接口和错误处理

**重构方案**：统一为一个EmbeddingService，支持多种后端

```python
# Backend/app/services/llm/embedding_service.py（重构后）
from typing import List, Optional
from pathlib import Path
import numpy as np

class EmbeddingService:
    """统一的Embedding服务（支持Transformers和Ollama）"""
    
    def __init__(
        self,
        backend: str = "transformers",  # transformers | ollama
        model_name: str = "BAAI/bge-small-zh-v1.5"
    ):
        self.backend = backend
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
    
    async def initialize(self) -> bool:
        """初始化embedding模型"""
        if self.backend == "transformers":
            return await self._init_transformers()
        elif self.backend == "ollama":
            return await self._init_ollama()
        else:
            raise ValueError(f"不支持的backend: {self.backend}")
    
    async def _init_transformers(self) -> bool:
        """初始化Transformers模型"""
        from transformers import AutoModel, AutoTokenizer
        from app.core.device.gpu_manager import DeviceManager
        
        device_manager = DeviceManager()
        
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModel.from_pretrained(
                self.model_name,
                trust_remote_code=True
            ).to(device_manager.device)
            self.model.eval()
            return True
        except Exception as e:
            print(f"Transformers初始化失败: {e}")
            return False
    
    async def _init_ollama(self) -> bool:
        """初始化Ollama客户端"""
        import httpx
        self.client = httpx.AsyncClient(timeout=60.0)
        return True
    
    async def embed_text(self, text: str) -> List[float]:
        """文本向量化（统一接口）"""
        if self.backend == "transformers":
            return await self._embed_transformers(text)
        elif self.backend == "ollama":
            return await self._embed_ollama(text)
    
    async def _embed_transformers(self, text: str) -> List[float]:
        """Transformers向量化"""
        import torch
        
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512
        ).to(self.model.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            # 使用[CLS] token的embedding
            embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy()[0]
        
        return embedding.tolist()
    
    async def _embed_ollama(self, text: str) -> List[float]:
        """Ollama向量化"""
        response = await self.client.post(
            "http://localhost:11434/api/embeddings",
            json={"model": self.model_name, "prompt": text}
        )
        return response.json()["embedding"]
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        return [await self.embed_text(text) for text in texts]
```

**重构效果**：
- 2个文件（538行）→ 1个文件（250行）
- 减少288行（-54%）
- 统一接口，便于切换backend

---

### Week 4-5: 模型服务重构

#### T2.4 拆分TransformersService（5天）

**当前问题**：`transformers_service.py`（835行）包含7个职责混合

**拆分方案**：6个独立模块 + 1个协调器

##### 模块1: PromptBuilder - 提示词构建（150行）

```python
# Backend/app/core/llm/transformers/prompt_builder.py
from typing import List, Optional
from jinja2 import Template

class PromptBuilder:
    """统一的提示词构建器（支持模板）"""
    
    def __init__(self, template_path: Optional[str] = None):
        self.template = self._load_template(template_path)
    
    def build(
        self,
        messages: List[dict],
        system_prompt: Optional[str] = None,
        use_template: bool = True
    ) -> str:
        """
        构建完整提示词
        
        Args:
            messages: 对话历史 [{"role": "user", "content": "..."}, ...]
            system_prompt: 系统提示（可选）
            use_template: 是否使用Jinja2模板
            
        Returns:
            格式化后的提示词
        """
        # 添加系统提示
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})
        
        # 使用模板渲染
        if use_template and self.template:
            return self.template.render(messages=messages)
        
        # 默认格式化
        return self._default_format(messages)
    
    def _load_template(self, path: Optional[str]) -> Optional[Template]:
        """加载Jinja2模板"""
        if not path:
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return Template(f.read())
        except:
            return None
    
    def _default_format(self, messages: List[dict]) -> str:
        """默认格式化（ChatML风格）"""
        prompt_parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            prompt_parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        prompt_parts.append("<|im_start|>assistant\n")
        return "\n".join(prompt_parts)
```

##### 模块2: ResponseProcessor - 响应后处理（80行）

```python
# Backend/app/core/llm/transformers/response_processor.py
import re

class ResponseProcessor:
    """响应后处理器（清理、过滤、格式化）"""
    
    def __init__(self):
        self.stop_words = ["<|im_end|>", "<|endoftext|>", "</s>"]
    
    def process(
        self,
        raw_text: str,
        remove_prompt: bool = True,
        clean_special_tokens: bool = True
    ) -> str:
        """
        处理模型输出
        
        Args:
            raw_text: 原始输出
            remove_prompt: 是否移除输入提示
            clean_special_tokens: 是否清理特殊标记
            
        Returns:
            清理后的文本
        """
        text = raw_text
        
        # 1. 移除提示词部分（如果包含）
        if remove_prompt and "<|im_start|>assistant" in text:
            text = text.split("<|im_start|>assistant\n")[-1]
        
        # 2. 清理停止词
        if clean_special_tokens:
            for stop_word in self.stop_words:
                text = text.split(stop_word)[0]
        
        # 3. 清理多余空白
        text = text.strip()
        text = re.sub(r'\n{3,}', '\n\n', text)  # 最多2个换行
        
        return text
    
    def chunk_stream(self, text: str, chunk_size: int = 10) -> List[str]:
        """
        将文本分块用于流式输出
        
        Args:
            text: 完整文本
            chunk_size: 每块字符数
            
        Returns:
            文本块列表
        """
        return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
```

##### 模块3: LoRAAdapter - LoRA管理（120行）

```python
# Backend/app/core/llm/transformers/lora_adapter.py
from pathlib import Path
from typing import Optional
from peft import PeftModel
import torch

class LoRAAdapter:
    """LoRA适配器管理（加载/切换/卸载）"""
    
    def __init__(self, base_model):
        self.base_model = base_model
        self.current_adapter: Optional[str] = None
        self.active_model = base_model
    
    def load_adapter(self, lora_path: Path, adapter_name: str = "default") -> bool:
        """
        加载LoRA适配器
        
        Args:
            lora_path: LoRA权重路径
            adapter_name: 适配器名称
            
        Returns:
            是否成功
        """
        try:
            # 如果已有适配器，先卸载
            if self.current_adapter:
                self.unload_adapter()
            
            # 加载新适配器
            self.active_model = PeftModel.from_pretrained(
                self.base_model,
                str(lora_path),
                adapter_name=adapter_name,
                torch_dtype=torch.float16
            )
            self.current_adapter = adapter_name
            
            return True
        except Exception as e:
            print(f"加载LoRA失败: {e}")
            return False
    
    def unload_adapter(self):
        """卸载当前适配器（恢复基座模型）"""
        if self.current_adapter:
            # 释放LoRA模型
            del self.active_model
            torch.cuda.empty_cache()
            
            # 恢复基座模型
            self.active_model = self.base_model
            self.current_adapter = None
    
    def get_model(self):
        """获取当前激活的模型"""
        return self.active_model
    
    def get_adapter_info(self) -> dict:
        """获取适配器信息"""
        if not self.current_adapter:
            return {"loaded": False}
        
        return {
            "loaded": True,
            "adapter_name": self.current_adapter,
            "trainable_params": sum(
                p.numel() for p in self.active_model.parameters() if p.requires_grad
            )
        }
```

##### 模块4: TransformersLLM - 协调器（280行）

```python
# Backend/app/core/llm/transformers/transformers_llm.py
from pathlib import Path
from typing import List, Optional, AsyncGenerator
import torch
from transformers import TextIteratorStreamer
from threading import Thread

from app.core.llm.base_llm import BaseLLM, Message, LLMConfig
from app.core.device.gpu_manager import DeviceManager
from app.core.model.model_loader import ModelLoader
from app.core.llm.transformers.prompt_builder import PromptBuilder
from app.core.llm.transformers.response_processor import ResponseProcessor
from app.core.llm.transformers.lora_adapter import LoRAAdapter

class TransformersLLM(BaseLLM):
    """Transformers本地模型实现（整合所有模块）"""
    
    def __init__(
        self,
        config: LLMConfig,
        model_path: Path,
        quantize: bool = True,
        lora_path: Optional[Path] = None
    ):
        super().__init__(config)
        self.model_path = model_path
        self.quantize = quantize
        self.lora_path = lora_path
        
        # 依赖组件
        self.device_manager = DeviceManager()
        self.model_loader = ModelLoader(self.device_manager)
        self.prompt_builder = PromptBuilder()
        self.response_processor = ResponseProcessor()
        
        # 模型资源
        self.model = None
        self.tokenizer = None
        self.lora_adapter: Optional[LoRAAdapter] = None
    
    async def initialize(self) -> bool:
        """初始化模型"""
        try:
            # 1. 加载基座模型
            self.model, self.tokenizer = await self.model_loader.load(
                model_path=self.model_path,
                quantize=self.quantize
            )
            
            # 2. 初始化LoRA管理器
            self.lora_adapter = LoRAAdapter(self.model)
            
            # 3. 加载LoRA（如果有）
            if self.lora_path:
                self.lora_adapter.load_adapter(self.lora_path)
            
            return True
        except Exception as e:
            print(f"初始化失败: {e}")
            return False
    
    async def generate(
        self,
        messages: List[Message],
        stream: bool = False,
        system_prompt: Optional[str] = None,
        **kwargs
    ):
        """生成回复"""
        # 1. 构建提示词
        message_dicts = [{"role": m.role, "content": m.content} for m in messages]
        prompt = self.prompt_builder.build(message_dicts, system_prompt)
        
        # 2. Tokenize
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=2048
        ).to(self.device_manager.device)
        
        # 3. 合并生成参数
        gen_config = self._merge_config(**kwargs)
        gen_kwargs = {
            "max_new_tokens": gen_config["max_new_tokens"],
            "temperature": gen_config["temperature"],
            "top_p": gen_config["top_p"],
            "top_k": gen_config["top_k"],
            "repetition_penalty": gen_config["repetition_penalty"],
            "do_sample": True,
            "pad_token_id": self.tokenizer.eos_token_id
        }
        
        # 4. 生成
        if stream:
            return self._stream_generate(inputs, gen_kwargs)
        else:
            return await self._sync_generate(inputs, gen_kwargs)
    
    async def _sync_generate(self, inputs, gen_kwargs) -> str:
        """非流式生成"""
        model = self.lora_adapter.get_model()
        
        with torch.no_grad():
            outputs = model.generate(**inputs, **gen_kwargs)
        
        # 解码
        full_text = self.tokenizer.decode(outputs[0], skip_special_tokens=False)
        
        # 后处理
        return self.response_processor.process(full_text)
    
    async def _stream_generate(self, inputs, gen_kwargs) -> AsyncGenerator[str, None]:
        """流式生成"""
        model = self.lora_adapter.get_model()
        
        # 创建流式输出器
        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True
        )
        gen_kwargs["streamer"] = streamer
        
        # 在后台线程生成
        thread = Thread(
            target=model.generate,
            kwargs={**inputs, **gen_kwargs}
        )
        thread.start()
        
        # 逐块输出
        for text_chunk in streamer:
            if text_chunk:
                yield text_chunk
        
        thread.join()
    
    async def get_model_info(self):
        """获取模型信息"""
        device_info = self.device_manager.get_device_info()
        lora_info = (
            self.lora_adapter.get_adapter_info() 
            if self.lora_adapter 
            else {"loaded": False}
        )
        
        return {
            "name": self.model_name,
            "type": "transformers",
            "status": "loaded" if self.model else "unloaded",
            "device": device_info.device_type,
            "memory_usage_mb": device_info.allocated_memory_gb * 1024,
            "quantized": self.quantize,
            "lora_loaded": lora_info["loaded"],
            "lora_adapter": lora_info.get("adapter_name")
        }
    
    async def cleanup(self):
        """清理资源"""
        if self.lora_adapter:
            self.lora_adapter.unload_adapter()
        
        del self.model
        del self.tokenizer
        self.device_manager.clear_cache()
```

---

#### T2.5 重构model_mgmt模块（2天）⭐

**当前问题**：
- `model_manager.py`（214行）：模型注册和生命周期管理
- `model_scanner.py`（344行）：扫描LLM模型
- `lora_scanner_service.py`（393行）：扫描LoRA适配器
- **重复代码**：文件遍历、格式识别、元数据提取逻辑重复3次

**为什么放在模型层**：model_mgmt属于模型管理的一部分，与模型加载、LoRA适配器同属模型层基础设施。

**重构方案**：合并为2个文件（model_scanner.py + deployment.py）

```python
# Backend/app/services/model_mgmt/model_scanner.py
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class ModelInfo:
    """统一的模型信息结构"""
    model_id: str
    model_name: str
    model_type: str  # "llm" | "lora" | "embedding"
    model_path: str
    format: str  # "gguf" | "safetensors" | "pytorch"
    size_mb: float
    metadata: Dict[str, Any]

class ModelScanner:
    """统一模型扫描器（支持所有模型类型）"""
    
    def scan(
        self,
        base_path: Path,
        model_type: str  # "llm" | "lora" | "embedding"
    ) -> List[ModelInfo]:
        """
        统一扫描接口
        
        Args:
            base_path: 扫描根目录
            model_type: 模型类型
            
        Returns:
            标准化的模型信息列表
        """
        if model_type == "llm":
            return self._scan_llm(base_path)
        elif model_type == "lora":
            return self._scan_lora(base_path)
        elif model_type == "embedding":
            return self._scan_embedding(base_path)
        else:
            raise ValueError(f"不支持的模型类型: {model_type}")
    
    def _scan_llm(self, base_path: Path) -> List[ModelInfo]:
        """扫描LLM模型（GGUF/Safetensors）"""
        models = []
        
        for model_dir in base_path.iterdir():
            if not model_dir.is_dir():
                continue
            
            # 检测GGUF文件
            gguf_files = list(model_dir.glob("*.gguf"))
            if gguf_files:
                models.append(self._parse_gguf_model(gguf_files[0]))
                continue
            
            # 检测Safetensors文件
            if (model_dir / "model.safetensors").exists():
                models.append(self._parse_safetensors_model(model_dir))
        
        return models
    
    def _scan_lora(self, base_path: Path) -> List[ModelInfo]:
        """扫描LoRA适配器"""
        adapters = []
        
        for adapter_dir in base_path.iterdir():
            if not adapter_dir.is_dir():
                continue
            
            # 检测adapter_config.json
            config_file = adapter_dir / "adapter_config.json"
            if config_file.exists():
                adapters.append(self._parse_lora_adapter(adapter_dir))
        
        return adapters
    
    def _parse_gguf_model(self, gguf_path: Path) -> ModelInfo:
        """解析GGUF模型信息"""
        return ModelInfo(
            model_id=gguf_path.stem,
            model_name=gguf_path.stem,
            model_type="llm",
            model_path=str(gguf_path.parent),
            format="gguf",
            size_mb=gguf_path.stat().st_size / 1024 / 1024,
            metadata={"quantization": self._detect_quantization(gguf_path.name)}
        )
    
    # ... 其他解析方法
```

```python
# Backend/app/services/model_mgmt/deployment.py
from typing import Optional, Dict
from app.core.device.gpu_manager import DeviceManager

class ModelDeployment:
    """模型部署管理"""
    
    def __init__(self):
        self.device_manager = DeviceManager()
        self.deployed_models: Dict[str, Any] = {}
    
    async def deploy(
        self,
        model_id: str,
        model_path: str,
        model_type: str
    ) -> bool:
        """
        部署模型（加载到内存）
        
        Args:
            model_id: 模型ID
            model_path: 模型路径
            model_type: 模型类型
            
        Returns:
            是否成功
        """
        # 检查设备资源
        device_info = self.device_manager.get_device_info()
        if device_info.allocated_memory_gb > 5.0:
            raise RuntimeError("显存不足，无法部署模型")
        
        # 加载模型
        if model_type == "llm":
            from app.core.llm.transformers.transformers_llm import TransformersLLM
            from app.core.llm.base_llm import LLMConfig
            
            config = LLMConfig(model_name=model_id)
            model = TransformersLLM(config, Path(model_path))
            await model.initialize()
            
            self.deployed_models[model_id] = model
        
        return True
    
    async def undeploy(self, model_id: str) -> bool:
        """卸载模型"""
        if model_id not in self.deployed_models:
            return False
        
        model = self.deployed_models.pop(model_id)
        await model.cleanup()
        
        return True
```

**重构效果**：
- 3个文件（951行）→ 2个文件（530行）
- 减少421行（-44%）
- 统一扫描接口，易于扩展

---

#### T2.6 重构training模块（2天）⭐

**当前问题**：
- `simple_lora_trainer.py`（500行）：包含重复的数据集验证、状态管理代码

**为什么放在模型层**：LoRA训练是模型管理的一部分，与模型加载、适配器管理紧密相关。

**重构方案**：使用core层的TaskStateManager和ProcessManager

```python
# Backend/app/services/training/lora_trainer.py（重构后）
from pathlib import Path
from typing import Dict, Any
from app.core.utils.task_state_manager import TaskStateManager
import json

class LoRATrainer:
    """LoRA训练服务（简化版）"""
    
    def __init__(self):
        self.state_manager = TaskStateManager()  # 使用统一的状态管理
        self.training_processes = {}
    
    async def start_training(
        self,
        task_id: str,
        base_model_path: str,
        dataset_path: str,
        output_dir: str,
        **training_args
    ) -> bool:
        """
        启动LoRA训练
        
        Args:
            task_id: 任务ID
            base_model_path: 基座模型路径
            dataset_path: 数据集路径
            output_dir: 输出目录
            **training_args: 训练参数
        """
        # 1. 验证数据集（使用工具类）
        if not self._validate_dataset(dataset_path):
            raise ValueError("数据集格式错误")
        
        # 2. 创建训练配置
        config = self._build_training_config(
            base_model_path,
            dataset_path,
            output_dir,
            **training_args
        )
        
        # 3. 初始化状态
        self.state_manager.create_task(
            task_id=task_id,
            initial_state="preparing"
        )
        
        # 4. 启动训练进程
        from app.core.utils.process_manager import ProcessManager
        process_manager = ProcessManager()
        
        process = await process_manager.start_python_script(
            script_path="scripts/train_lora.py",
            args=["--config", str(config)],
            on_output=lambda line: self._handle_training_output(task_id, line)
        )
        
        self.training_processes[task_id] = process
        self.state_manager.update_state(task_id, "running")
        
        return True
    
    def _validate_dataset(self, dataset_path: str) -> bool:
        """验证数据集格式（简化版）"""
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                return False
            
            for item in data[:5]:  # 只检查前5条
                if "instruction" not in item or "output" not in item:
                    return False
            
            return True
        except:
            return False
    
    def _handle_training_output(self, task_id: str, line: str):
        """处理训练输出（更新进度）"""
        if "loss" in line.lower():
            self.state_manager.update_metadata(
                task_id,
                {"latest_output": line}
            )
```

**重构效果**：
- 500行 → 350行（-30%）
- 使用统一的TaskStateManager（删除重复状态管理代码）
- 使用统一的ProcessManager（删除重复进程管理代码）

---

#### T2.7 更新服务层调用（1天）

**旧代码** (`transformers_service.py`):
```python
# 旧代码（835行）包含所有逻辑
class TransformersService:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        # ... 800多行实现
```

**新代码** (`llm_service.py`):
```python
# Backend/app/services/llm_service.py
from pathlib import Path
from typing import Optional, Dict
from app.core.llm.base_llm import BaseLLM, LLMConfig, Message
from app.core.llm.transformers.transformers_llm import TransformersLLM
from app.core.llm.ollama_llm import OllamaLLM
from app.core.utils.path_resolver import PathResolver

class LLMService:
    """统一的LLM服务（工厂模式）"""
    
    def __init__(self):
        self.path_resolver = PathResolver()
        self.llm_instances: Dict[str, BaseLLM] = {}  # 模型缓存
    
    async def get_llm(
        self,
        model_type: str,  # transformers/ollama
        model_name: str,
        config: Optional[LLMConfig] = None,
        **kwargs
    ) -> BaseLLM:
        """
        获取LLM实例（懒加载）
        
        Args:
            model_type: 模型类型
            model_name: 模型名称
            config: LLM配置
            **kwargs: 额外参数（lora_path等）
            
        Returns:
            LLM实例
        """
        cache_key = f"{model_type}:{model_name}"
        
        # 从缓存获取
        if cache_key in self.llm_instances:
            return self.llm_instances[cache_key]
        
        # 创建新实例
        if config is None:
            config = LLMConfig(model_name=model_name)
        
        if model_type == "transformers":
            model_path = self.path_resolver.get_model_path("llm", model_name)
            lora_path = kwargs.get("lora_path")
            if lora_path:
                lora_path = self.path_resolver.get_model_path("lora", lora_path)
            
            llm = TransformersLLM(
                config=config,
                model_path=model_path,
                quantize=kwargs.get("quantize", True),
                lora_path=lora_path
            )
        elif model_type == "ollama":
            llm = OllamaLLM(
                config=config,
                base_url=kwargs.get("base_url", "http://localhost:11434")
            )
        else:
            raise ValueError(f"不支持的模型类型: {model_type}")
        
        # 初始化
        success = await llm.initialize()
        if not success:
            raise RuntimeError(f"模型初始化失败: {model_name}")
        
        # 缓存
        self.llm_instances[cache_key] = llm
        
        return llm
    
    async def unload_model(self, model_type: str, model_name: str):
        """卸载模型"""
        cache_key = f"{model_type}:{model_name}"
        if cache_key in self.llm_instances:
            await self.llm_instances[cache_key].cleanup()
            del self.llm_instances[cache_key]
```

---

### 阶段2总结

**完成标准**：
- ✅ BaseLLM接口单元测试通过
- ✅ TransformersLLM集成测试通过（对比旧版本输出一致性）
- ✅ OllamaLLM连接测试通过
- ✅ embedding_service统一测试通过
- ✅ model_mgmt模块重构完成（3文件951行 → 2文件530行）
- ✅ training模块重构完成（500行 → 350行）
- ✅ 所有模型相关服务更新完成

**预期效果**：
- ⬇️ transformers_service: 835行 → 280行 (-66%)
- ⬇️ embedding相关: 538行 → 250行 (-54%)
- ⬇️ model_mgmt: 951行 → 530行 (-44%)
- ⬇️ training: 500行 → 350行 (-30%)
- ⬆️ 可扩展性: 新增模型类型只需实现BaseLLM接口
- ⬆️ 可维护性: 统一的扫描器和训练管理

**下一步**：进入阶段3 - 业务逻辑层重构

---

## 五、阶段3：业务层 (Week 6-8)

### 目标
🎯 统一检索策略（向量/全文/混合/图谱）  
🎯 重构knowledge_base_service（558行 → 350行）  
🎯 优化RAG检索性能

### Week 6: 检索策略统一

#### 当前问题
- 检索逻辑分散在3个文件（chat_service, knowledge_base_service, graph_service）
- 没有统一的策略接口
- 无法灵活切换检索算法

#### T3.1 定义检索策略接口（1天）

**策略模式设计**：

```python
# Backend/app/core/retrieval/base_retriever.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class RetrievalConfig:
    """检索配置"""
    top_k: int = 5
    score_threshold: float = 0.6
    enable_rerank: bool = False

@dataclass
class Document:
    """文档结构"""
    content: str
    metadata: Dict[str, Any]
    score: float
    doc_id: str

class BaseRetriever(ABC):
    """检索器基类"""
    
    def __init__(self, config: RetrievalConfig):
        self.config = config
    
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        kb_id: int,
        **kwargs
    ) -> List[Document]:
        """
        执行检索
        
        Args:
            query: 查询文本
            kb_id: 知识库ID
            **kwargs: 额外参数
            
        Returns:
            文档列表（按相关性排序）
        """
        pass
    
    @abstractmethod
    def get_retriever_info(self) -> Dict[str, Any]:
        """
        获取检索器信息
        
        Returns:
            {
                "type": "vector/bm25/hybrid/graph",
                "config": {...}
            }
        """
        pass
```

**测试用例**：

```python
# Backend/app/tests/test_retriever.py
import pytest
from app.core.retrieval.base_retriever import BaseRetriever, RetrievalConfig, Document

class MockRetriever(BaseRetriever):
    async def retrieve(self, query, kb_id, **kwargs):
        return [
            Document(
                content="测试文档1",
                metadata={"source": "test.txt"},
                score=0.95,
                doc_id="doc1"
            )
        ]
    
    def get_retriever_info(self):
        return {"type": "mock", "config": self.config.__dict__}

@pytest.mark.asyncio
async def test_retriever_interface():
    config = RetrievalConfig(top_k=10)
    retriever = MockRetriever(config)
    
    results = await retriever.retrieve("测试查询", kb_id=1)
    assert len(results) == 1
    assert results[0].score == 0.95
```

---

#### T3.2 实现向量检索器（2天）

```python
# Backend/app/core/retrieval/vector_retriever.py
from typing import List
import numpy as np
from app.core.retrieval.base_retriever import BaseRetriever, Document
from app.services.embedding_service import EmbeddingService

class VectorRetriever(BaseRetriever):
    """向量检索器（使用ChromaDB）"""
    
    def __init__(self, config, embedding_service: EmbeddingService):
        super().__init__(config)
        self.embedding_service = embedding_service
    
    async def retrieve(self, query: str, kb_id: int, **kwargs) -> List[Document]:
        """向量检索"""
        # 1. 查询向量化
        query_embedding = await self.embedding_service.embed_text(query)
        
        # 2. 从ChromaDB检索
        from app.services.vector_store_service import VectorStoreService
        vector_store = VectorStoreService()
        
        raw_results = vector_store.similarity_search(
            collection_name=f"kb_{kb_id}",
            query_embedding=query_embedding,
            top_k=self.config.top_k
        )
        
        # 3. 转换为Document对象
        documents = []
        for result in raw_results:
            if result['score'] >= self.config.score_threshold:
                documents.append(Document(
                    content=result['content'],
                    metadata=result['metadata'],
                    score=result['score'],
                    doc_id=result['id']
                ))
        
        # 4. Rerank（如果启用）
        if self.config.enable_rerank:
            documents = await self._rerank(query, documents)
        
        return documents
    
    async def _rerank(self, query: str, documents: List[Document]) -> List[Document]:
        """重排序（使用BGE-Reranker）"""
        # TODO: 集成Reranker模型
        # 暂时返回原结果
        return documents
    
    def get_retriever_info(self):
        return {
            "type": "vector",
            "config": {
                "top_k": self.config.top_k,
                "score_threshold": self.config.score_threshold,
                "enable_rerank": self.config.enable_rerank
            }
        }
```

---

#### T3.3 实现BM25全文检索器（2天）

```python
# Backend/app/core/retrieval/bm25_retriever.py
from typing import List
from rank_bm25 import BM25Okapi
import jieba
from app.core.retrieval.base_retriever import BaseRetriever, Document

class BM25Retriever(BaseRetriever):
    """BM25全文检索器"""
    
    def __init__(self, config):
        super().__init__(config)
        self.bm25_index = {}  # {kb_id: BM25Okapi实例}
        self.doc_store = {}   # {kb_id: [Document]}
    
    async def retrieve(self, query: str, kb_id: int, **kwargs) -> List[Document]:
        """BM25检索"""
        # 1. 检查索引是否存在
        if kb_id not in self.bm25_index:
            await self._build_index(kb_id)
        
        # 2. 分词
        query_tokens = list(jieba.cut(query))
        
        # 3. BM25打分
        bm25 = self.bm25_index[kb_id]
        scores = bm25.get_scores(query_tokens)
        
        # 4. 排序并过滤
        doc_store = self.doc_store[kb_id]
        ranked_indices = np.argsort(scores)[::-1]  # 降序
        
        documents = []
        for idx in ranked_indices[:self.config.top_k]:
            score = scores[idx]
            if score >= self.config.score_threshold:
                doc = doc_store[idx]
                doc.score = float(score)
                documents.append(doc)
        
        return documents
    
    async def _build_index(self, kb_id: int):
        """构建BM25索引"""
        # 1. 从数据库加载文档
        from app.services.database_service import DatabaseService
        db = DatabaseService()
        
        chunks = db.get_knowledge_chunks(kb_id)
        
        # 2. 分词
        tokenized_corpus = []
        doc_store = []
        
        for chunk in chunks:
            tokens = list(jieba.cut(chunk['content']))
            tokenized_corpus.append(tokens)
            
            doc_store.append(Document(
                content=chunk['content'],
                metadata=chunk['metadata'],
                score=0.0,
                doc_id=str(chunk['id'])
            ))
        
        # 3. 构建BM25
        self.bm25_index[kb_id] = BM25Okapi(tokenized_corpus)
        self.doc_store[kb_id] = doc_store
    
    def get_retriever_info(self):
        return {
            "type": "bm25",
            "config": {
                "top_k": self.config.top_k,
                "indexed_kbs": list(self.bm25_index.keys())
            }
        }
```

---

### Week 6总结

**完成内容**：
- ✅ BaseRetriever接口定义
- ✅ VectorRetriever实现（ChromaDB）
- ✅ BM25Retriever实现（全文检索）

**代码量**：
- 新增: ~350行（3个文件）
- 下一步: 实现HybridRetriever + GraphRetriever

---

### Week 7: 混合检索与知识图谱

#### T3.4 实现混合检索器（2天）

**混合检索策略**：向量检索 + BM25 + 融合算法

```python
# Backend/app/core/retrieval/hybrid_retriever.py
from typing import List, Dict
import numpy as np
from app.core.retrieval.base_retriever import BaseRetriever, Document, RetrievalConfig
from app.core.retrieval.vector_retriever import VectorRetriever
from app.core.retrieval.bm25_retriever import BM25Retriever

class HybridRetriever(BaseRetriever):
    """混合检索器（向量+BM25融合）"""
    
    def __init__(
        self,
        config: RetrievalConfig,
        vector_retriever: VectorRetriever,
        bm25_retriever: BM25Retriever,
        vector_weight: float = 0.7  # 向量检索权重
    ):
        super().__init__(config)
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.vector_weight = vector_weight
        self.bm25_weight = 1.0 - vector_weight
    
    async def retrieve(self, query: str, kb_id: int, **kwargs) -> List[Document]:
        """混合检索（RRF融合）"""
        # 1. 并行执行两种检索
        vector_results = await self.vector_retriever.retrieve(query, kb_id)
        bm25_results = await self.bm25_retriever.retrieve(query, kb_id)
        
        # 2. RRF融合（Reciprocal Rank Fusion）
        fused_results = self._rrf_fusion(vector_results, bm25_results)
        
        # 3. 截断到top_k
        return fused_results[:self.config.top_k]
    
    def _rrf_fusion(
        self,
        vector_docs: List[Document],
        bm25_docs: List[Document],
        k: int = 60  # RRF参数
    ) -> List[Document]:
        """
        RRF融合算法
        Score(d) = Σ 1/(k + rank_i(d))
        """
        # 1. 构建文档字典
        doc_dict: Dict[str, Document] = {}
        doc_scores: Dict[str, float] = {}
        
        # 2. 处理向量检索结果
        for rank, doc in enumerate(vector_docs, start=1):
            doc_id = doc.doc_id
            rrf_score = self.vector_weight / (k + rank)
            
            doc_dict[doc_id] = doc
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + rrf_score
        
        # 3. 处理BM25检索结果
        for rank, doc in enumerate(bm25_docs, start=1):
            doc_id = doc.doc_id
            rrf_score = self.bm25_weight / (k + rank)
            
            if doc_id not in doc_dict:
                doc_dict[doc_id] = doc
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + rrf_score
        
        # 4. 按融合分数排序
        sorted_ids = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        
        # 5. 更新分数并返回
        fused_docs = []
        for doc_id, score in sorted_ids:
            doc = doc_dict[doc_id]
            doc.score = score
            fused_docs.append(doc)
        
        return fused_docs
    
    def get_retriever_info(self):
        return {
            "type": "hybrid",
            "config": {
                "vector_weight": self.vector_weight,
                "bm25_weight": self.bm25_weight,
                "top_k": self.config.top_k
            }
        }
```

**测试用例**：

```python
# Backend/app/tests/test_hybrid_retriever.py
import pytest
from app.core.retrieval.hybrid_retriever import HybridRetriever
from app.core.retrieval.base_retriever import Document

@pytest.mark.asyncio
async def test_rrf_fusion():
    # Mock检索器
    class MockVectorRetriever:
        async def retrieve(self, query, kb_id):
            return [
                Document("doc1", {}, 0.9, "1"),
                Document("doc2", {}, 0.8, "2")
            ]
    
    class MockBM25Retriever:
        async def retrieve(self, query, kb_id):
            return [
                Document("doc2", {}, 0.95, "2"),  # doc2在两个结果中
                Document("doc3", {}, 0.7, "3")
            ]
    
    config = RetrievalConfig(top_k=5)
    retriever = HybridRetriever(
        config,
        MockVectorRetriever(),
        MockBM25Retriever(),
        vector_weight=0.7
    )
    
    results = await retriever.retrieve("test", kb_id=1)
    
    # doc2应该排第一（两个检索器都返回了）
    assert results[0].doc_id == "2"
    assert len(results) == 3
```

---

#### T3.5 实现知识图谱检索器（3天）

```python
# Backend/app/core/retrieval/graph_retriever.py
from typing import List, Set, Dict
from app.core.retrieval.base_retriever import BaseRetriever, Document

class GraphRetriever(BaseRetriever):
    """知识图谱检索器（实体关系扩展）"""
    
    def __init__(self, config, graph_service):
        super().__init__(config)
        self.graph_service = graph_service
    
    async def retrieve(self, query: str, kb_id: int, **kwargs) -> List[Document]:
        """
        图谱检索流程：
        1. 提取查询中的实体
        2. 查找实体的关系三元组
        3. 扩展到相关实体
        4. 收集关联文档
        """
        # 1. 提取实体
        entities = await self._extract_entities(query, kb_id)
        if not entities:
            return []
        
        # 2. 查找关系
        triples = await self._find_triples(entities, kb_id)
        
        # 3. 扩展相关实体
        related_entities = self._expand_entities(triples, entities)
        
        # 4. 收集文档
        documents = await self._collect_documents(
            entities | related_entities,
            kb_id
        )
        
        return documents[:self.config.top_k]
    
    async def _extract_entities(self, query: str, kb_id: int) -> Set[str]:
        """从查询中提取实体"""
        # 调用entity_extraction_service
        from app.services.entity_extraction_service import EntityExtractionService
        
        service = EntityExtractionService()
        result = await service.extract_entities(query, kb_id)
        
        return set(result.get("entities", []))
    
    async def _find_triples(
        self,
        entities: Set[str],
        kb_id: int
    ) -> List[Dict]:
        """查找实体的三元组"""
        triples = []
        
        for entity in entities:
            # 查询数据库
            entity_triples = self.graph_service.get_entity_triples(
                kb_id=kb_id,
                entity=entity
            )
            triples.extend(entity_triples)
        
        return triples
    
    def _expand_entities(
        self,
        triples: List[Dict],
        seed_entities: Set[str]
    ) -> Set[str]:
        """扩展相关实体（1跳）"""
        related = set()
        
        for triple in triples:
            head = triple["head_entity"]
            tail = triple["tail_entity"]
            
            # 如果头实体是种子，添加尾实体
            if head in seed_entities:
                related.add(tail)
            
            # 如果尾实体是种子，添加头实体
            if tail in seed_entities:
                related.add(head)
        
        return related - seed_entities  # 排除种子实体
    
    async def _collect_documents(
        self,
        entities: Set[str],
        kb_id: int
    ) -> List[Document]:
        """收集包含实体的文档"""
        from app.services.database_service import DatabaseService
        
        db = DatabaseService()
        documents = []
        
        for entity in entities:
            # 查询包含该实体的文档块
            chunks = db.search_chunks_by_entity(kb_id, entity)
            
            for chunk in chunks:
                documents.append(Document(
                    content=chunk['content'],
                    metadata={
                        **chunk['metadata'],
                        "matched_entity": entity
                    },
                    score=0.8,  # 固定分数
                    doc_id=str(chunk['id'])
                ))
        
        # 去重
        seen = set()
        unique_docs = []
        for doc in documents:
            if doc.doc_id not in seen:
                seen.add(doc.doc_id)
                unique_docs.append(doc)
        
        return unique_docs
    
    def get_retriever_info(self):
        return {
            "type": "graph",
            "config": {
                "top_k": self.config.top_k,
                "expand_hops": 1
            }
        }
```

---

### Week 7总结

**完成内容**：
- ✅ HybridRetriever（RRF融合算法）
- ✅ GraphRetriever（知识图谱扩展）
- ✅ 4种检索策略全部实现

**检索策略对比**：

| 策略 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| Vector | 语义相似度搜索 | 理解语义 | 召回精确词困难 |
| BM25 | 关键词精确匹配 | 速度快 | 不理解语义 |
| Hybrid | 通用场景 | 兼顾语义+关键词 | 复杂度高 |
| Graph | 需要关系推理 | 可扩展实体 | 依赖图谱质量 |

---

### Week 8: 知识库服务重构

#### T3.10 拆分knowledge_base_service（3天）

**当前问题**：
`knowledge_base_service.py`（528行）包含4个职责：
1. CRUD操作（创建/删除知识库）
2. 文档管理（上传/分块）
3. 检索逻辑（向量搜索）
4. 知识图谱操作

**重构方案**：职责分离

```python
# Backend/app/services/knowledge/knowledge_base_service.py（重构后，220行）
class KnowledgeBaseService:
    """知识库服务（仅负责CRUD + 检索策略选择）"""
    
    def __init__(self):
        self.db = DatabaseService()
        self.retrievers = self._init_retrievers()
    
    def _init_retrievers(self) -> dict:
        """初始化所有检索器"""
        config = RetrievalConfig(top_k=5, score_threshold=0.6)
        
        embedding_service = EmbeddingService()
        vector_retriever = VectorRetriever(config, embedding_service)
        bm25_retriever = BM25Retriever(config)
        
        return {
            "vector": vector_retriever,
            "bm25": bm25_retriever,
            "hybrid": HybridRetriever(config, vector_retriever, bm25_retriever),
            "graph": GraphRetriever(config, GraphService())
        }
    
    async def create_knowledge_base(self, name: str, description: str) -> int:
        """创建知识库"""
        kb_id = self.db.insert_knowledge_base(name, description)
        vector_store = VectorStoreService()
        vector_store.create_collection(f"kb_{kb_id}")
        return kb_id
    
    async def search(
        self,
        query: str,
        kb_id: int,
        strategy: str = "hybrid",
        top_k: int = 5
    ) -> List[dict]:
        """统一检索入口"""
        retriever = self.retrievers.get(strategy)
        if not retriever:
            raise ValueError(f"不支持的检索策略: {strategy}")
        
        retriever.config.top_k = top_k
        documents = await retriever.retrieve(query, kb_id)
        
        return [
            {
                "content": doc.content,
                "metadata": doc.metadata,
                "score": doc.score,
                "doc_id": doc.doc_id
            }
            for doc in documents
        ]
```

---

#### T3.11 创建document_service（1天）

```python
# Backend/app/services/knowledge/document_service.py（新增，200行）
class DocumentService:
    """文档管理服务（上传/分块/向量化）"""
    
    def __init__(self):
        self.db = DatabaseService()
        self.vector_store = VectorStoreService()
        self.embedding = EmbeddingService()
        self.text_splitter = RecursiveTextSplitter(chunk_size=500, chunk_overlap=50)
    
    async def upload_document(
        self,
        kb_id: int,
        file_path: Path,
        metadata: dict = None
    ) -> int:
        """上传文档到知识库"""
        # 1. 保存文档记录
        doc_id = self.db.insert_document(
            kb_id=kb_id,
            filename=file_path.name,
            filepath=str(file_path),
            metadata=metadata or {}
        )
        
        # 2. 读取文本
        text = self._read_file(file_path)
        
        # 3. 文本分块
        chunks = self.text_splitter.split(text)
        
        # 4. 向量化并存储
        await self._store_chunks(kb_id, doc_id, chunks, metadata)
        
        return doc_id
```

---

#### T3.12 优化file和metadata服务（1天）

**当前问题**：
- `file_service.py`（301行）：包含冗余的文件验证逻辑
- `metadata_service.py`（128行）：相对简单，保持不变

**重构方案**：简化file_service

```python
# Backend/app/services/storage/file_service.py（简化后，280行）
from pathlib import Path
from app.core.utils.path_resolver import PathResolver

class FileService:
    """文件存储服务（简化版）"""
    
    def __init__(self):
        self.path_resolver = PathResolver()
        self.allowed_extensions = {'.txt', '.md', '.pdf', '.docx'}
    
    async def upload(self, kb_id: int, file: UploadFile) -> str:
        """上传文件"""
        # 1. 验证文件类型（使用工具类）
        if not self._is_allowed(file.filename):
            raise ValueError(f"不支持的文件类型: {file.filename}")
        
        # 2. 生成保存路径（使用PathResolver）
        save_path = self.path_resolver.get_upload_path(kb_id, file.filename)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 3. 保存文件
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        return str(save_path)
    
    def _is_allowed(self, filename: str) -> bool:
        """检查文件类型（简化版）"""
        return Path(filename).suffix.lower() in self.allowed_extensions
```

**优化效果**：
- 301行 → 280行（-7%）
- 使用PathResolver统一路径管理

---

## 六、阶段4：应用层 (Week 9-10)

### 目标

🎯 重构chat_service（624行 → 400行）  
🎯 提取RAG Pipeline独立模块  
🎯 优化Agent服务

### Week 9: RAG Pipeline重构

#### T4.1 提取RAG Pipeline（3天）

**当前问题**：`chat_service.py`混合了对话管理、RAG逻辑、流式输出

**新架构**：

```python
# Backend/app/core/rag/rag_pipeline.py
from typing import List, Dict, Optional, AsyncGenerator
from app.core.llm.base_llm import BaseLLM, Message
from app.core.retrieval.base_retriever import BaseRetriever

class RAGPipeline:
    """RAG处理流水线"""
    
    def __init__(
        self,
        llm: BaseLLM,
        retriever: BaseRetriever,
        prompt_template: str = None
    ):
        self.llm = llm
        self.retriever = retriever
        self.prompt_template = prompt_template or self._default_template()
    
    async def generate(
        self,
        query: str,
        kb_id: int,
        chat_history: List[Message] = None,
        stream: bool = False,
        **kwargs
    ):
        """
        RAG生成流程
        
        Args:
            query: 用户查询
            kb_id: 知识库ID
            chat_history: 对话历史
            stream: 是否流式输出
            **kwargs: 额外参数
            
        Returns:
            生成结果（字符串或流）
        """
        # 1. 检索相关文档
        documents = await self.retriever.retrieve(query, kb_id)
        
        # 2. 构建上下文
        context = self._build_context(documents)
        
        # 3. 构建提示词
        messages = self._build_messages(query, context, chat_history)
        
        # 4. 生成回复
        response = await self.llm.generate(messages, stream=stream, **kwargs)
        
        # 5. 返回（附带引用）
        if stream:
            return self._stream_with_citations(response, documents)
        else:
            return {
                "answer": response,
                "citations": self._format_citations(documents)
            }
    
    def _build_context(self, documents: List) -> str:
        """构建上下文"""
        if not documents:
            return "没有找到相关信息。"
        
        context_parts = []
        for i, doc in enumerate(documents, 1):
            context_parts.append(f"[{i}] {doc.content}")
        
        return "\n\n".join(context_parts)
    
    def _build_messages(
        self,
        query: str,
        context: str,
        chat_history: List[Message] = None
    ) -> List[Message]:
        """构建对话消息"""
        messages = []
        
        # 添加历史对话
        if chat_history:
            messages.extend(chat_history)
        
        # 添加当前查询（带上下文）
        user_message = self.prompt_template.format(
            context=context,
            question=query
        )
        messages.append(Message(role="user", content=user_message))
        
        return messages
    
    async def _stream_with_citations(
        self,
        response_stream: AsyncGenerator,
        documents: List
    ) -> AsyncGenerator:
        """流式输出（先输出答案，最后附带引用）"""
        # 1. 流式输出答案
        async for chunk in response_stream:
            yield chunk
        
        # 2. 输出引用
        citations = self._format_citations(documents)
        yield f"\n\n---\n参考来源:\n{citations}"
    
    def _format_citations(self, documents: List) -> str:
        """格式化引用"""
        citations = []
        for i, doc in enumerate(documents, 1):
            source = doc.metadata.get('source', 'unknown')
            citations.append(f"[{i}] {source} (相关度: {doc.score:.2f})")
        
        return "\n".join(citations)
    
    def _default_template(self) -> str:
        """默认提示词模板"""
        return """请根据以下上下文回答问题。如果上下文中没有相关信息，请说"我不知道"。

上下文:
{context}

问题: {question}

回答:"""
```

**重构后的ChatService**：

```python
# Backend/app/services/chat_service.py (重构后)
from typing import List, Dict, Optional
from app.core.rag.rag_pipeline import RAGPipeline
from app.core.retrieval.retriever_factory import RetrieverFactory
from app.services.llm_service import LLMService

class ChatService:
    """对话服务（仅负责会话管理）"""
    
    def __init__(self):
        self.db = DatabaseService()
        self.llm_service = LLMService()
    
    async def chat(
        self,
        session_id: int,
        message: str,
        kb_id: Optional[int] = None,
        strategy: str = "hybrid",
        stream: bool = False
    ):
        """
        对话接口
        
        Args:
            session_id: 会话ID
            message: 用户消息
            kb_id: 知识库ID（None表示普通对话）
            strategy: 检索策略
            stream: 是否流式输出
        """
        # 1. 获取对话历史
        chat_history = self._get_chat_history(session_id)
        
        # 2. 保存用户消息
        self.db.insert_message(session_id, "user", message)
        
        # 3. 选择模式
        if kb_id:
            # RAG模式
            response = await self._rag_chat(
                message, kb_id, chat_history, strategy, stream
            )
        else:
            # 普通对话
            response = await self._normal_chat(
                message, chat_history, stream
            )
        
        # 4. 保存助手消息（非流式）
        if not stream:
            self.db.insert_message(session_id, "assistant", response["answer"])
        
        return response
    
    async def _rag_chat(
        self,
        message: str,
        kb_id: int,
        chat_history: List,
        strategy: str,
        stream: bool
    ):
        """RAG对话"""
        # 1. 获取LLM
        llm = await self.llm_service.get_llm("transformers", "Qwen2.5-1.5B")
        
        # 2. 创建检索器
        config = RetrievalConfig(top_k=5)
        retriever = RetrieverFactory.create(
            strategy=strategy,
            config=config,
            embedding_service=EmbeddingService()
        )
        
        # 3. 创建RAG Pipeline
        pipeline = RAGPipeline(llm, retriever)
        
        # 4. 生成回复
        return await pipeline.generate(
            query=message,
            kb_id=kb_id,
            chat_history=chat_history,
            stream=stream
        )
    
    async def _normal_chat(
        self,
        message: str,
        chat_history: List,
        stream: bool
    ):
        """普通对话（无RAG）"""
        llm = await self.llm_service.get_llm("ollama", "qwen2.5:latest")
        
        messages = chat_history + [Message(role="user", content=message)]
        response = await llm.generate(messages, stream=stream)
        
        if stream:
            return response  # 流式生成器
        else:
            return {"answer": response, "citations": []}
    
    def _get_chat_history(self, session_id: int, limit: int = 10) -> List:
        """获取对话历史"""
        messages = self.db.get_session_messages(session_id, limit=limit)
        return [
            Message(role=m['role'], content=m['content'])
            for m in messages
        ]
```

---

### Week 10: Agent服务优化

#### T4.2 优化Agent工具调用（2天）

**当前问题**：`agent_service.py`工具注册混乱，缺少统一管理

**新架构**：

```python
# Backend/app/core/agent/tool_registry.py
from typing import Dict, Callable, Any
from dataclasses import dataclass

@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable

class ToolRegistry:
    """工具注册表（集中管理Agent工具）"""
    
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
    
    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any]
    ):
        """注册工具（装饰器模式）"""
        def decorator(func: Callable):
            self.tools[name] = ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
                function=func
            )
            return func
        return decorator
    
    def get_tool(self, name: str) -> ToolDefinition:
        """获取工具"""
        return self.tools.get(name)
    
    def list_tools(self) -> List[Dict]:
        """列出所有工具（OpenAI函数调用格式）"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
            for tool in self.tools.values()
        ]
```

**工具注册示例**：

```python
# Backend/app/core/agent/builtin_tools.py
from app.core.agent.tool_registry import ToolRegistry

registry = ToolRegistry()

@registry.register(
    name="knowledge_search",
    description="在知识库中搜索信息",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "kb_id": {"type": "integer", "description": "知识库ID"}
        },
        "required": ["query", "kb_id"]
    }
)
async def knowledge_search(query: str, kb_id: int):
    """知识库搜索工具"""
    kb_service = KnowledgeBaseService()
    results = await kb_service.search(query, kb_id, strategy="hybrid")
    return results[:3]  # 返回前3条

@registry.register(
    name="web_search",
    description="在互联网上搜索最新信息",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"}
        },
        "required": ["query"]
    }
)
async def web_search(query: str):
    """网络搜索工具"""
    # TODO: 集成搜索API
    return [{"title": "示例结果", "url": "https://example.com"}]
```

---

### 阶段4总结

**完成标准**：
- ✅ RAG Pipeline独立模块测试通过
- ✅ chat_service重构完成（624行 → 400行）
- ✅ Agent工具注册表实现
- ✅ 端到端RAG流程测试通过

**预期效果**：
- ⬇️ chat_service: 624行 → 400行 (-36%)
- ⬆️ RAG复用性: Pipeline可用于多种场景
- ⬆️ Agent扩展性: 新增工具只需装饰器注册

---

## 七、阶段5：清理与优化 (Week 11-12)

### 目标
🎯 删除旧代码和重复逻辑  
🎯 性能优化与测试  
🎯 文档补全

### Week 11: 代码清理

#### T5.1 删除废弃服务（2天）

**待删除文件**（已被新架构替代）：
- `transformers_service.py`（835行）→ 替换为`TransformersLLM`
- `ollama_service.py`（部分逻辑）→ 替换为`OllamaLLM`
- 旧的检索逻辑（分散在3个文件）→ 替换为Retriever系统

**清理检查清单**：
```bash
# 1. 确认所有API端点已更新
grep -r "TransformersService" app/api/

# 2. 确认测试全部通过
pytest app/tests/ -v

# 3. 删除旧文件
git rm app/services/transformers_service.py

# 4. 提交清理
git commit -m "refactor: remove deprecated services"
```

---

#### T5.2 性能优化（3天）

**优化项清单**：

1. **模型缓存优化**
```python
# Backend/app/services/llm_service.py
class LLMService:
    def __init__(self):
        self.llm_cache = {}  # 添加LRU缓存
        self.max_cache_size = 3  # 最多缓存3个模型
    
    async def get_llm(self, model_type, model_name, **kwargs):
        cache_key = f"{model_type}:{model_name}"
        
        # 缓存命中
        if cache_key in self.llm_cache:
            return self.llm_cache[cache_key]
        
        # 缓存满，移除最旧的
        if len(self.llm_cache) >= self.max_cache_size:
            oldest_key = next(iter(self.llm_cache))
            await self.llm_cache[oldest_key].cleanup()
            del self.llm_cache[oldest_key]
        
        # 加载新模型...
```

2. **检索性能优化**
- 为BM25索引添加磁盘缓存（pickle）
- 向量检索批量查询优化
- 混合检索并行化

3. **内存管理**
```python
# Backend/app/core/device/gpu_manager.py
class DeviceManager:
    def optimize_memory(self):
        """内存优化策略"""
        if self.device == "cuda":
            # 清理碎片
            torch.cuda.empty_cache()
            
            # 压缩内存
            torch.cuda.memory.empty_cache()
            
            # 重置峰值统计
            torch.cuda.reset_peak_memory_stats()
```

---

### Week 12: 测试与文档

#### T5.3 完善测试覆盖（2天）

**测试目标**：
- 单元测试覆盖率: 30% → 80%
- 集成测试: 核心流程全覆盖
- 性能基准测试

**测试清单**：
```bash
# 运行全部测试
pytest app/tests/ --cov=app --cov-report=html

# 核心模块覆盖率检查
pytest app/tests/test_llm/ --cov=app/core/llm --cov-report=term-missing

# 性能基准测试
python benchmark/rag_latency.py  # RAG端到端延迟
python benchmark/retrieval_speed.py  # 检索速度
```

---

#### T5.4 文档补全（1天）

**文档清单**：
1. **API文档更新**（Swagger注释）
2. **架构图更新**（绘制新的4层架构图）
3. **迁移指南**（旧API → 新API对照表）
4. **性能报告**（重构前后对比）

**示例迁移指南**：
```markdown
# API迁移指南

## 旧版 → 新版对照

### 1. 对话接口
**旧版**:
```python
POST /api/chat
{
    "message": "你好",
    "model": "transformers",
    "kb_id": 1
}
```

**新版**:
```python
POST /api/chat
{
    "session_id": 123,
    "message": "你好",
    "kb_id": 1,
    "strategy": "hybrid"  # 新增：检索策略
}
```

### 2. 模型管理
**旧版**: `/api/transformers/load_model`  
**新版**: `/api/llm/load` （统一所有模型类型）
```

---

### 阶段5总结

**完成标准**：
- ✅ 所有旧代码已删除
- ✅ 测试覆盖率达到80%
- ✅ 性能基准无下降（部分提升）
- ✅ 文档全部更新

**最终效果统计**：

| 指标 | 重构前 | 重构后 | 改进 |
|------|--------|--------|------|
| 代码总量 | 6738行 | 4500行 | -33% |
| 最大文件 | 835行 | 400行 | -52% |
| 重复率 | 25% | 8% | -68% |
| 测试覆盖率 | 30% | 80% | +167% |
| 模块数 | 18 | 25 | +39% (拆分后) |
| 平均文件大小 | 374行 | 180行 | -52% |

---

## 附录

### A. 风险控制

**回滚策略**：
1. 每个阶段完成后打Git标签（`v2.0-stage1`）
2. 保留旧代码分支（`legacy/service-layer-v1`）
3. 数据库使用迁移脚本（支持回滚）

**灰度发布**：
1. 新旧API并行运行2周
2. 逐步切换流量（10% → 50% → 100%）
3. 监控错误率和性能指标

**应急预案**：
- P0故障：立即回滚到上一个稳定版本
- P1故障：24小时内修复或回滚
- P2故障：一周内修复

---

### B. 验收标准

**功能验收**：
- [ ] 所有现有API功能正常
- [ ] 新增4种检索策略可用
- [ ] RAG流程完整可用
- [ ] Agent工具调用正常

**性能验收**：
- [ ] LLM推理速度无下降（±5%以内）
- [ ] 检索延迟无下降（±10%以内）
- [ ] 内存占用无明显增加（±20%以内）

**质量验收**：
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 集成测试全部通过
- [ ] 代码审查通过（Pylint评分 ≥ 8.0）
- [ ] 文档完整度 ≥ 90%

---

## 附录C：重构前后文件结构对比

### 当前结构（重构前）

```
Backend/app/
├── api/                          # API路由层
├── core/                         # 核心配置（仅4个文件）
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   └── __init__.py
├── models/                       # 数据模型
├── services/                     # 服务层（18个文件，6118行）
│   ├── agent_service.py          # 316行 - Agent逻辑
│   ├── chat_service.py           # 561行 🔴 - 对话+RAG+流式
│   ├── embedding_service.py      # 334行 - Embedding模型
│   ├── entity_extraction_service.py # 337行 - 实体提取
│   ├── file_service.py           # 301行 - 文件上传
│   ├── hybrid_retrieval_service.py # 374行 - 混合检索
│   ├── knowledge_base_service.py # 528行 🟡 - CRUD+检索
│   ├── llama_factory_service.py  # 243行 - LLaMA Factory集成
│   ├── lora_scanner_service.py   # 393行 - LoRA扫描
│   ├── metadata_service.py       # 128行 - 元数据管理
│   ├── model_manager.py          # 214行 - 模型管理
│   ├── model_scanner.py          # 344行 - 模型扫描
│   ├── neo4j_graph_service.py    # 513行 🟡 - 知识图谱
│   ├── ollama_embedding_service.py # 204行 - Ollama Embedding
│   ├── ollama_llm_service.py     # 265行 - Ollama LLM
│   ├── simple_lora_trainer.py    # 500行 🟡 - LoRA训练
│   ├── transformers_service.py   # 776行 🔴 - Transformers推理
│   └── vector_store_service.py   # 287行 - 向量数据库
├── utils/                        # 工具函数（较少）
└── websocket/                    # WebSocket处理
```

**当前问题**：
- ❌ `core/`目录几乎为空，缺少基础设施
- ❌ `services/`承担了所有逻辑，职责不清
- ❌ 设备管理、模型加载等基础功能在4个文件中重复
- ❌ 缺少统一的LLM抽象层
- ❌ 检索策略分散，无统一接口

---

### 重构后结构（目标）

```
Backend/app/
├── api/                          # API路由层（不变）
│   ├── agent.py
│   ├── chat.py
│   ├── knowledge_base.py
│   └── models.py
│
├── core/                         # 核心基础设施（新增）
│   ├── __init__.py
│   ├── config.py                 # 配置管理
│   ├── database.py               # 数据库连接
│   ├── dependencies.py           # 依赖注入
│   │
│   ├── device/                   # 设备管理（新增）⭐
│   │   ├── __init__.py
│   │   └── gpu_manager.py        # 80行 - 统一CUDA管理
│   │
│   ├── model/                    # 模型加载（新增）⭐
│   │   ├── __init__.py
│   │   └── model_loader.py       # 200行 - 统一模型加载
│   │
│   ├── llm/                      # LLM抽象层（新增）⭐
│   │   ├── __init__.py
│   │   ├── base_llm.py           # 100行 - 基类接口
│   │   ├── ollama_llm.py         # 150行 - Ollama实现
│   │   │
│   │   └── transformers/         # Transformers实现
│   │       ├── __init__.py
│   │       ├── prompt_builder.py      # 150行 - 提示词构建
│   │       ├── response_processor.py  # 80行 - 响应处理
│   │       ├── lora_adapter.py        # 120行 - LoRA管理
│   │       └── transformers_llm.py    # 280行 - 主协调器
│   │
│   ├── retrieval/                # 检索策略（新增）⭐
│   │   ├── __init__.py
│   │   ├── base_retriever.py     # 80行 - 基类接口
│   │   ├── vector_retriever.py   # 120行 - 向量检索
│   │   ├── bm25_retriever.py     # 150行 - BM25全文检索
│   │   ├── hybrid_retriever.py   # 180行 - 混合检索（RRF）
│   │   ├── graph_retriever.py    # 200行 - 知识图谱检索
│   │   └── retriever_factory.py  # 60行 - 工厂模式
│   │
│   ├── rag/                      # RAG流水线（新增）⭐
│   │   ├── __init__.py
│   │   └── rag_pipeline.py       # 200行 - RAG核心流程
│   │
│   ├── agent/                    # Agent工具（新增）⭐
│   │   ├── __init__.py
│   │   ├── tool_registry.py      # 80行 - 工具注册表
│   │   └── builtin_tools.py      # 150行 - 内置工具
│   │
│   └── utils/                    # 核心工具（新增）⭐
│       ├── __init__.py
│       ├── json_parser.py        # 60行 - JSON容错解析
│       ├── path_resolver.py      # 80行 - 路径管理
│       ├── process_manager.py    # 120行 - 进程管理
│       ├── task_state_manager.py # 100行 - 任务状态机
│       └── text_splitter.py      # 150行 - 文本分割
│
├── models/                       # 数据模型（不变）
│   ├── __init__.py
│   ├── agent.py
│   ├── chat.py
│   └── knowledge_base.py
│
├── services/                     # 服务层（按模块分类）⭐
│   ├── __init__.py
│   │
│   ├── llm/                      # LLM模型服务模块
│   │   ├── __init__.py
│   │   ├── llm_service.py        # 180行 - LLM统一入口（工厂模式）
│   │   └── embedding_service.py  # 250行 - Embedding服务（简化）
│   │
│   ├── chat/                     # 对话服务模块
│   │   ├── __init__.py
│   │   ├── chat_service.py       # 250行 - 对话管理（会话+历史）
│   │   └── agent_service.py      # 200行 - Agent对话（工具调用）
│   │
│   ├── knowledge/                # 知识库服务模块
│   │   ├── __init__.py
│   │   ├── knowledge_base_service.py  # 220行 - 知识库CRUD
│   │   ├── document_service.py        # 200行 - 文档上传/分块
│   │   ├── vector_store_service.py    # 250行 - 向量存储（简化）
│   │   └── entity_extraction_service.py # 200行 - 实体提取（简化）
│   │
│   ├── graph/                    # 知识图谱服务模块
│   │   ├── __init__.py
│   │   └── neo4j_service.py      # 350行 - Neo4j图谱操作（简化）
│   │
│   ├── training/                 # 模型训练服务模块
│   │   ├── __init__.py
│   │   ├── lora_trainer.py       # 350行 - LoRA训练（简化）
│   │   └── llama_factory_service.py # 243行 - LLaMA Factory集成
│   │
│   ├── model_mgmt/               # 模型管理服务模块
│   │   ├── __init__.py
│   │   ├── model_scanner.py      # 350行 - 统一模型扫描器（支持LLM/LoRA/Embedding）⭐
│   │   └── deployment.py         # 180行 - 模型部署管理（新增）
│   │
│   ├── storage/                  # 存储服务模块
│   │   ├── __init__.py
│   │   ├── file_service.py       # 280行 - 文件上传/下载（简化）
│   │   └── metadata_service.py   # 128行 - 元数据管理
│   │
│   └── [已删除]                  # 废弃的旧服务
│       ├── transformers_service.py    # 776行 → 删除（移至core/llm）
│       ├── ollama_llm_service.py      # 265行 → 删除（移至core/llm）
│       ├── ollama_embedding_service.py # 204行 → 删除（合并）
│       ├── hybrid_retrieval_service.py # 374行 → 删除（移至core/retrieval）
│       ├── model_manager.py           # 214行 → 删除（拆分到model_mgmt）
│       └── simple_lora_trainer.py     # 500行 → 重命名为lora_trainer.py
│
├── tests/                        # 测试（新增/完善）
│   ├── __init__.py
│   │
│   ├── core/                     # 核心层测试
│   │   ├── test_device_manager.py
│   │   ├── test_model_loader.py
│   │   ├── test_base_llm.py
│   │   ├── test_transformers_llm.py
│   │   ├── test_retriever.py
│   │   └── test_rag_pipeline.py
│   │
│   ├── services/                 # 服务层测试
│   │   ├── test_llm_service.py
│   │   ├── test_chat_service.py
│   │   ├── test_knowledge_base_service.py
│   │   └── test_agent_service.py
│   │
│   └── integration/              # 集成测试
│       ├── test_rag_flow.py
│       ├── test_hybrid_retrieval.py
│       └── test_agent_flow.py
│
├── utils/                        # 业务工具（保留）
└── websocket/                    # WebSocket（不变）
```

---

### 重构效果对比

#### 服务模块分类说明

**按业务领域分为7个模块**：

| 模块 | 职责 | 文件数 | 总行数 |
|------|------|--------|--------|
| **llm/** | LLM模型管理（工厂+嵌入） | 2 | ~430行 |
| **chat/** | 对话服务（普通+Agent） | 2 | ~450行 |
| **knowledge/** | 知识库管理（CRUD+文档+向量） | 5 | ~1120行 |
| **graph/** | 知识图谱操作 | 1 | ~350行 |
| **training/** | 模型训练（LoRA+集成） | 2 | ~593行 |
| **model_mgmt/** | 模型扫描+部署 | 2 | ~530行 |
| **storage/** | 文件存储+元数据 | 2 | ~408行 |
| **总计** | | **16个文件** | **~3881行** |

**模块依赖关系**：
```
┌─────────────┐
│   chat/     │ ← 最上层（依赖其他所有模块）
└──────┬──────┘
       │
   ┌───┴───┬────────┬─────────┐
   │       │        │         │
┌──▼───┐ ┌▼────┐ ┌─▼──────┐ ┌▼─────┐
│ llm/ │ │know │ │ graph/ │ │train │
└──────┘ └─────┘ └────────┘ └──────┘
          │
      ┌───┴────┐
   ┌──▼───┐ ┌─▼────────┐
   │store │ │model_mgmt│
   └──────┘ └──────────┘
```

---

#### 代码量变化

| 层级 | 重构前 | 重构后 | 变化 |
|------|--------|--------|------|
| **core/** | 4个文件，~200行 | 30个文件，~2500行 | +2300行（新增基础设施） |
| **services/** | 18个文件，6118行 | 16个文件（7模块），3881行 | -2237行（-37%） |
| **tests/** | ~500行 | ~2000行 | +1500行（+300%） |
| **总计** | ~6818行 | ~8381行 | +1563行（+23%）|

> **说明**：代码总量增加是因为增加了测试和基础设施，但**业务逻辑代码减少37%**，**重复率下降68%**，**模块化程度提升300%**。

#### 文件复杂度对比

| 文件类别 | 重构前最大 | 重构后最大 | 改进 |
|---------|-----------|-----------|------|
| 服务层文件 | 776行 | 280行 | -64% |
| 平均文件大小 | 340行 | 180行 | -47% |
| 单一职责得分 | 3.2/10 | 8.5/10 | +166% |

#### 架构分层

```
重构前（2层）:                  重构后（4层）:
┌─────────────┐                ┌─────────────┐
│   API层     │                │   API层     │
└──────┬──────┘                └──────┬──────┘
       │                              │
┌──────▼──────┐                ┌──────▼──────┐
│  Services   │                │  Services   │ ← 应用服务层
│  (6118行)   │                │  (3800行)   │
└─────────────┘                └──────┬──────┘
                                      │
                               ┌──────▼──────┐
                               │  Core/RAG   │ ← 业务逻辑层
                               │  (~1000行)  │
                               └──────┬──────┘
                                      │
                               ┌──────▼──────┐
                               │ Core/基础层 │ ← 基础设施层
                               │  (~1500行)  │
                               └─────────────┘
```

---

### 关键改进点

1. **模块化分类** ⭐⭐⭐
   ```
   重构前：18个文件平铺在services/根目录
   重构后：17个文件分类到7个模块目录
   
   优势：
   - 职责清晰：每个模块聚焦单一领域
   - 易于定位：按业务查找文件（知识库→knowledge/）
   - 降低耦合：模块间通过接口交互
   - 便于测试：按模块组织测试用例
   ```

2. **基础设施下沉** ⭐
   - `DeviceManager`：统一CUDA管理（消除4处重复）
   - `ModelLoader`：统一模型加载（消除3处重复）
   - `ProcessManager`：统一进程管理
   - `PathResolver`：统一路径解析

3. **抽象层建立** ⭐
   - `BaseLLM`：统一LLM接口（支持Transformers/Ollama/OpenAI）
   - `BaseRetriever`：统一检索接口（支持4种策略）
   - `RAGPipeline`：解耦RAG流程

4. **职责分离** ⭐
   - `transformers_service.py`（776行）→ 6个模块（总280行）
   - `chat_service.py`（561行）→ 250行 + RAG Pipeline
   - `knowledge_base_service.py`（528行）→ 220行 + Document Service

5. **可扩展性提升** ⭐
   - 新增LLM：实现`BaseLLM`接口
   - 新增检索策略：实现`BaseRetriever`接口
   - 新增Agent工具：使用装饰器注册

---

### 服务模块详解

#### 1. llm/ - LLM模型服务
```python
# 统一的LLM管理入口
from app.services.llm.llm_service import LLMService
from app.services.llm.embedding_service import EmbeddingService

# 获取任意类型的LLM
llm_service = LLMService()
llm = await llm_service.get_llm("transformers", "Qwen2.5-1.5B")
llm = await llm_service.get_llm("ollama", "qwen2.5:latest")

# 获取Embedding
embedding = EmbeddingService()
vec = await embedding.embed_text("测试文本")
```

**职责**：
- ✅ LLM工厂（创建/缓存/卸载）
- ✅ Embedding向量化
- ✅ 模型配置管理

---

#### 2. chat/ - 对话服务
```python
# 普通对话
from app.services.chat.chat_service import ChatService

chat_service = ChatService()
response = await chat_service.chat(
    session_id=123,
    message="你好",
    kb_id=1,          # 指定知识库（RAG模式）
    strategy="hybrid"  # 检索策略
)

# Agent对话（带工具调用）
from app.services.chat.agent_service import AgentService

agent = AgentService()
result = await agent.chat(
    message="搜索知识库中关于Python的内容",
    tools=["knowledge_search", "web_search"]
)
```

**职责**：
- ✅ 会话管理（创建/历史/上下文）
- ✅ RAG对话（检索+生成）
- ✅ Agent对话（工具调用+推理）
- ✅ 流式输出支持

---

#### 3. knowledge/ - 知识库服务
```python
# 知识库CRUD
from app.services.knowledge.knowledge_base_service import KnowledgeBaseService

kb_service = KnowledgeBaseService()
kb_id = await kb_service.create("我的知识库", "描述")
results = await kb_service.search(
    query="测试查询",
    kb_id=kb_id,
    strategy="hybrid",  # vector/bm25/hybrid/graph
    top_k=5
)

# 文档管理
from app.services.knowledge.document_service import DocumentService

doc_service = DocumentService()
doc_id = await doc_service.upload_document(
    kb_id=kb_id,
    file_path=Path("test.txt"),
    metadata={"author": "张三"}
)

# 实体提取
from app.services.knowledge.entity_extraction_service import EntityExtractionService

entity_service = EntityExtractionService()
entities = await entity_service.extract_entities("孙悟空大闹天宫", kb_id=1)
```

**职责**：
- ✅ 知识库CRUD
- ✅ 文档上传/分块/向量化
- ✅ 统一检索入口（4种策略）
- ✅ 向量存储操作
- ✅ 实体识别

---

#### 4. graph/ - 知识图谱服务
```python
from app.services.graph.neo4j_service import Neo4jService

graph = Neo4jService()

# 构建知识图谱
await graph.build_knowledge_graph(kb_id=1)

# 查询三元组
triples = graph.get_entity_triples(kb_id=1, entity="孙悟空")
# [{"head": "孙悟空", "relation": "师傅是", "tail": "唐僧"}, ...]

# 统计信息
stats = graph.get_statistics(kb_id=1)
# {"nodes": 100, "relationships": 250, ...}
```

**职责**：
- ✅ Neo4j连接管理
- ✅ 知识图谱构建
- ✅ 三元组查询
- ✅ 图谱统计

---

#### 5. training/ - 模型训练服务
```python
# LoRA训练
from app.services.training.lora_trainer import LoRATrainer

trainer = LoRATrainer()
task_id = await trainer.start_training(
    base_model="Qwen2.5-1.5B",
    dataset_path="monkey_brother.json",
    output_dir="./saves/lora_test"
)

# 训练状态查询
status = trainer.get_training_status(task_id)

# LLaMA Factory集成
from app.services.training.llama_factory_service import LlamaFactoryService

factory = LlamaFactoryService()
await factory.start_training_with_config(config_dict)
```

**职责**：
- ✅ LoRA训练任务管理
- ✅ 数据集验证/转换
- ✅ 训练进度监控
- ✅ LLaMA Factory集成

---

#### 6. model_mgmt/ - 模型管理服务
```python
# 统一扫描器（支持所有模型类型）
from app.services.model_mgmt.model_scanner import ModelScanner

scanner = ModelScanner()

# 扫描LLM模型
llm_models = await scanner.scan(
    base_path="Models/LLM",
    model_type="llm"
)

# 扫描LoRA适配器
lora_adapters = await scanner.scan(
    base_path="Models/LoRA", 
    model_type="lora"
)

# 扫描Embedding模型
embedding_models = await scanner.scan(
    base_path="Models/Embedding",
    model_type="embedding"
)

# 模型部署管理
from app.services.model_mgmt.deployment import deploy_model, undeploy_model

await deploy_model(model_id="llama-3-8b", version="v1.0")
await undeploy_model(model_id="llama-3-8b")
```

**职责**：
- ✅ **统一扫描**：一个扫描器支持所有模型类型（LLM/LoRA/Embedding）
- ✅ **格式识别**：自动识别GGUF/Safetensors/PyTorch格式
- ✅ **模型部署**：上线/下线、版本切换

**为什么合并扫描器**：
- 统一接口：所有模型类型使用同一套扫描逻辑
- 减少重复：文件遍历、格式识别、错误处理可复用
- 易于扩展：新增模型类型只需添加一个`_scan_xxx()`方法

---

#### 7. storage/ - 存储服务
```python
# 文件上传/下载
from app.services.storage.file_service import FileService

file_service = FileService()
file_path = await file_service.upload_file(
    file=upload_file,
    kb_id=1,
    category="training_data"
)

# 元数据管理
from app.services.storage.metadata_service import MetadataService

metadata = MetadataService()
await metadata.update_file_metadata(
    file_id=123,
    metadata={"tags": ["重要", "待审核"]}
)
```

**职责**：
- ✅ 文件上传/下载
- ✅ 文件路径管理
- ✅ 元数据存储/查询

---

### 模块迁移对照表

**旧文件 → 新位置**：

| 旧文件 | 新位置 | 变化 |
|--------|--------|------|
| `transformers_service.py` (776行) | `core/llm/transformers/` (6个文件) | 拆分+下沉 |
| `ollama_llm_service.py` (265行) | `core/llm/ollama_llm.py` (150行) | 简化+下沉 |
| `ollama_embedding_service.py` (204行) | 合并到 `services/llm/embedding_service.py` | 合并 |
| `chat_service.py` (561行) | `services/chat/chat_service.py` (250行) | 简化+分类 |
| `agent_service.py` (316行) | `services/chat/agent_service.py` (200行) | 简化+分类 |
| `knowledge_base_service.py` (528行) | `services/knowledge/knowledge_base_service.py` (220行) | 简化+分类 |
| 新增 | `services/knowledge/document_service.py` (200行) | 职责分离 |
| `vector_store_service.py` (287行) | `services/knowledge/vector_store_service.py` (250行) | 简化+分类 |
| `entity_extraction_service.py` (337行) | `services/knowledge/entity_extraction_service.py` (200行) | 简化+分类 |
| `neo4j_graph_service.py` (513行) | `services/graph/neo4j_service.py` (350行) | 简化+分类 |
| `simple_lora_trainer.py` (500行) | `services/training/lora_trainer.py` (350行) | 重命名+简化+分类 |
| `llama_factory_service.py` (243行) | `services/training/llama_factory_service.py` (243行) | 仅分类 |
| `model_manager.py` (214行) | `services/model_mgmt/model_scanner.py` (350行) | 合并+分类 |
| `model_scanner.py` (344行) | ↑ 合并到统一扫描器 | 合并 |
| `lora_scanner_service.py` (393行) | ↑ 合并到统一扫描器 | 合并 |
| 新增 | `services/model_mgmt/deployment.py` (180行) | 职责分离 |
| `file_service.py` (301行) | `services/storage/file_service.py` (280行) | 简化+分类 |
| `metadata_service.py` (128行) | `services/storage/metadata_service.py` (128行) | 仅分类 |
| `embedding_service.py` (334行) | `services/llm/embedding_service.py` (250行) | 简化+分类 |
| `hybrid_retrieval_service.py` (374行) | `core/retrieval/hybrid_retriever.py` (180行) | 简化+下沉 |

**统计**：
- 🗑️ **删除**：0个文件（全部保留或拆分）
- 📦 **拆分**：4个文件拆分为多个（transformers, model_manager, knowledge_base, ollama）
- 🆕 **新增**：5个文件（document_service, deployment, 检索策略等）
- 📁 **分类**：所有文件按7大模块归类
- ⬇️ **简化**：平均减少32%代码量

---

### 迁移路径

#### 阶段0（Week 0）：准备
- 建立测试基准
- 创建重构分支

#### 阶段1（Week 1-2）：基础层
- 创建`core/device/`, `core/model/`, `core/utils/`
- 在现有服务中替换重复代码

#### 阶段2（Week 3-5）：模型层
- 创建`core/llm/`抽象层
- 拆分`transformers_service.py`
- 实现`OllamaLLM`

#### 阶段3（Week 6-8）：业务层
- 创建`core/retrieval/`检索策略
- 重构`knowledge_base_service.py`
- 新增`document_service.py`
- 重构`model_mgmt/`, `storage/`, `training/`, `graph/`模块 ⭐

#### 阶段4（Week 9-10）：应用层
- 创建`core/rag/rag_pipeline.py`
- 重构`chat_service.py`
- 优化`agent_service.py`

#### 阶段5（Week 11-12）：清理
- 删除旧文件
- 性能优化
- 文档补全

---

**实施手册完成！** 🎉

**文档统计**：
- 总页数：~3200行
- 估计阅读时间：75分钟
- 实施周期：12周（3个月）
- 预期效果：代码质量提升50%+

**核心价值**：
1. ✅ 建立4层架构（API → 应用 → 业务 → 基础）
2. ✅ 按模块分类服务层（7大业务模块）⭐⭐⭐
3. ✅ 消除重复代码（-68%重复率）
4. ✅ 提升可扩展性（插件化架构）
5. ✅ 增强可测试性（测试覆盖率+167%）
6. ✅ 降低维护成本（平均文件大小-47%）
7. ✅ 提高代码可读性（模块化程度+300%）

**下一步行动**：
1. 阅读本文档（估计1.5小时）
2. 运行测试基准（Week 0）
3. 创建重构分支
4. 按阶段逐步实施（建议先完成阶段1基础层）

---

**版本历史**：
- v3.0 (2025-01-27): ⭐⭐⭐架构优化版，系统性重组12周计划
  - 修正模块归属：model_mgmt/training移至Week 3-5模型层，graph/vector_store移至Week 6-7业务层
  - 明确说明：所有"简化"均为架构优化（删除重复代码、提取公共模块），不删除业务功能
  - 补充任务：为embedding_service、vector_store、entity_extraction、neo4j等添加具体重构任务
  - 时间优化：每周控制在5天工作量，总体12周完成
- v2.2 (2025-01-26): 补充Week 7-8缺失任务（后发现归属错误）
- v2.1 (2025-01-26): 优化服务层结构，按7大模块分类
- v2.0 (2025-01-26): 精简实施版，补充文件结构对比
- v1.0 (2025-01-25): 初始版本

