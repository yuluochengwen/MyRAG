# TransformersService 拆分重构方案

> **目标文件**: `Backend/app/services/transformers_service.py` (835行)  
> **问题**: 职责过多，包含模型加载、量化、LoRA、推理、流式输出、Prompt构建等7大职责  
> **方案**: 按职责垂直切分为6个独立模块

---

## 一、当前问题诊断

### 1.1 职责清单（7大职责混在一起）

| 职责编号 | 职责名称 | 代码行数 | 关键方法 |
|---------|---------|---------|---------|
| 1️⃣ | **设备管理** | ~50行 | `__init__()`, 设备检测, 显存监控 |
| 2️⃣ | **模型加载** | ~200行 | `load_model()`, `_estimate_model_size()` |
| 3️⃣ | **LoRA管理** | ~150行 | `load_model_with_lora()` |
| 4️⃣ | **Prompt构建** | ~100行 | `_build_prompt()`, `_inject_system_instruction()` |
| 5️⃣ | **推理生成** | ~250行 | `chat()`, `_chat_stream()` |
| 6️⃣ | **后处理** | ~50行 | `_post_process_response()` (移除思考过程) |
| 7️⃣ | **健康检查** | ~35行 | `check_health()`, `list_models()`, `unload_model()` |

### 1.2 核心问题

```python
# 问题1: 835行代码全在一个类中
class TransformersService:
    def __init__(self): ...          # 设备初始化
    def load_model(self): ...        # 模型加载
    def load_model_with_lora(self): ... # LoRA加载
    def chat(self): ...              # 推理
    def _chat_stream(self): ...      # 流式推理
    def _build_prompt(self): ...     # Prompt构建
    def _post_process_response(self): ... # 后处理
    def list_models(self): ...       # 模型管理
    def check_health(self): ...      # 健康检查
```

**问题**：
- ❌ 违反单一职责原则（SRP）
- ❌ 难以测试（无法单独测试模型加载逻辑）
- ❌ 难以复用（Prompt构建逻辑无法在其他服务中使用）
- ❌ 难以维护（修改LoRA加载可能影响普通推理）

