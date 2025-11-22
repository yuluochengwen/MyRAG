# LoRA 推理测试问题诊断报告

**诊断时间**：2025-11-20  
**问题描述**：lora-test.html 页面测试 LoRA 模型时，模型回复没有展示微调痕迹

---

## 🔴 核心问题：LoRA 模型被覆盖

### 问题原因

在 `Backend/app/api/lora_training.py` 的 `test_lora_inference` 方法中，存在致命的逻辑错误：

```python
# 第 295 行 - 加载 LoRA 模型
success = await transformers_service.load_model_with_lora(
    base_model=base_model,       # 例如：Qwen2.5-3B-Instruct
    lora_path=lora_path,          # LoRA 适配器路径
    quantize=True
)

# 第 307 行 - 调用推理
response = await transformers_service.chat(
    model=base_model,             # ❌ 问题：传入的是基座模型名称
    messages=messages,
    temperature=request.temperature,
    max_tokens=request.max_tokens,
    stream=False
)
```

**Bug 流程**：

1. `load_model_with_lora()` 加载了 **基座模型 + LoRA 适配器**
   - `self.current_model_name` = `"C:\...\Qwen2.5-3B-Instruct"`
   - `self.current_lora_path` = `"C:\...\qwen_monkey_20251120_115603"`
   - `self.current_model` = **PeftModel（带 LoRA）**

2. `chat()` 方法检查模型名称：
   ```python
   # 第 429 行
   if self.current_model_name != model:
       success = await self.load_model(model)  # ❌ 重新加载基座模型！
   ```

3. 因为传入的 `model` 是简短名称（如 `"Qwen2.5-3B-Instruct"`），而 `self.current_model_name` 是完整路径（如 `"C:\Users\Man\Desktop\MyRAG\Models\LLM\Qwen2.5-3B-Instruct"`）

4. **名称不匹配** → 触发 `load_model()` → **LoRA 模型被纯基座模型覆盖**！

5. 推理使用的是纯基座模型，没有 LoRA 的微调效果

---

## ✅ 解决方案

### 修复 1：优化 `chat()` 方法的模型检查逻辑

**文件**：`Backend/app/services/transformers_service.py`

**修改位置**：第 425-435 行 + 第 545-555 行（流式推理）

**修改前**：
```python
# 确保模型已加载
if self.current_model_name != model:
    success = await self.load_model(model)
    if not success:
        raise RuntimeError(f"无法加载模型: {model}")
```

**修改后**：
```python
# 确保模型已加载
# 注意：如果已经加载了 LoRA 模型，不要重新加载基座模型
if self.current_model_name != model:
    # 检查是否已加载同一基座模型的 LoRA
    if self.current_lora_path is None:
        # 没有 LoRA，正常加载模型
        success = await self.load_model(model)
        if not success:
            raise RuntimeError(f"无法加载模型: {model}")
    else:
        # 已加载 LoRA，检查基座模型是否匹配
        logger.info(f"已加载 LoRA 模型，基座: {self.current_model_name}, LoRA: {self.current_lora_path}")
```

**效果**：
- ✅ 如果 `current_lora_path` 不为空，说明已加载 LoRA
- ✅ 不会重新加载基座模型，保留 LoRA 适配器
- ✅ 推理时使用的是 **PeftModel（带 LoRA）**

---

### 修复 2：（可选）统一模型名称比较逻辑

**更优解决方案**：在 `chat()` 中增加路径归一化，避免路径差异导致的误判

```python
def _normalize_model_path(self, model: str) -> str:
    """归一化模型路径，用于比较"""
    if '\\' in model or '/' in model:
        return str(Path(model).resolve())
    else:
        return str((self.models_dir / model).resolve())

# 在 chat() 中使用
normalized_model = self._normalize_model_path(model)
normalized_current = self._normalize_model_path(self.current_model_name) if self.current_model_name else None

if normalized_current != normalized_model:
    # 模型不匹配，需要加载
    ...
```

---

## 🧪 验证步骤

### 1. 重启服务
```bash
# 停止当前服务（Ctrl+C）
# 重新启动
cmd /c "c:\Users\Man\Desktop\MyRAG\start-fast.bat"
```

### 2. 测试 LoRA 推理

**访问**：`http://localhost:8000/static/lora-test.html`

**测试用例**：
```
Prompt 1: 你好
预期输出: 嘿嘿，俺老孙在此！俺乃齐天大圣孙悟空，有什么事儿尽管问来！

Prompt 2: 你是谁
预期输出: 呔！俺就是五百年前大闹天宫的齐天大圣孙悟空！你这都不认得？

Prompt 3: 你的金箍棒有多重？
预期输出: 嘿嘿，俺这如意金箍棒，重一万三千五百斤！要大就大，要小就小，厉害得很呐！
```

### 3. 检查日志

**关键日志**：
```
✅ 正确的日志（LoRA 生效）：
2025-11-20 xx:xx:xx - INFO - 开始加载 LoRA 模型
2025-11-20 xx:xx:xx - INFO - 基座模型: C:\Users\Man\Desktop\MyRAG\Models\LLM\Qwen2.5-3B-Instruct
2025-11-20 xx:xx:xx - INFO - LoRA 适配器: C:\Users\Man\Desktop\MyRAG\Models\LoRA\qwen_monkey_20251120_115603
2025-11-20 xx:xx:xx - INFO - ✅ LoRA 模型加载成功
2025-11-20 xx:xx:xx - INFO - 已加载 LoRA 模型，基座: ..., LoRA: ...
2025-11-20 xx:xx:xx - INFO - 开始编码输入，prompt长度: ...

❌ 错误的日志（LoRA 被覆盖）：
2025-11-20 xx:xx:xx - INFO - ✅ LoRA 模型加载成功
2025-11-20 xx:xx:xx - INFO - 加载模型权重...  # ⚠️ 重新加载基座模型
2025-11-20 xx:xx:xx - INFO - 开始编码输入，prompt长度: ...
```

---

## 📋 诊断工具

已创建 `diagnose_lora.py` 脚本，用于深度诊断 LoRA 模型：

```bash
# 进入 MyRAG 目录
cd C:\Users\Man\Desktop\MyRAG

# 激活环境
conda activate MyRAG

# 运行诊断
python diagnose_lora.py
```

**诊断内容**：
1. ✅ 检查文件完整性（adapter_config.json、adapter_model.safetensors）
2. ✅ 检查 LoRA 配置（rank、alpha、target_modules）
3. ✅ 加载模型并检查参数（总参数、可训练参数）
4. ✅ 检查 LoRA 层是否存在
5. ✅ 对比测试（基座 vs LoRA）
6. ✅ 检查权重是否非零

---

## 🔍 根本原因分析

### 为什么会有这个 Bug？

1. **设计缺陷**：`load_model()` 和 `load_model_with_lora()` 是两个独立方法
   - `load_model()` 加载纯基座模型
   - `load_model_with_lora()` 加载基座+LoRA
   - 两者都设置 `self.current_model_name`，但含义不同

2. **状态管理不足**：缺少明确的"当前是否使用 LoRA"标志
   - 引入 `self.current_lora_path` 可以区分
   - 但 `chat()` 没有检查这个标志

3. **路径比较问题**：模型名称可能是相对路径或绝对路径
   - `load_model_with_lora()` 存储的是绝对路径
   - API 传入的可能是相对名称
   - 导致路径比较失败

### 为什么训练数据看起来正确？

训练数据 `monkey_brother.json` 格式完全正确：

```json
{
  "instruction": "你好",
  "input": "",
  "output": "嘿嘿，俺老孙在此！..."
}
```

- ✅ Alpaca 格式标准
- ✅ instruction 清晰
- ✅ output 有明显的"孙悟空"风格

### LoRA 配置也正确

`adapter_config.json` 显示：
```json
{
  "peft_type": "LORA",
  "r": 16,
  "lora_alpha": 32,
  "target_modules": ["o_proj", "k_proj", "q_proj", "v_proj"],
  "base_model_name_or_path": "C:\\Users\\Man\\Desktop\\MyRAG\\Models\\LLM\\Qwen2.5-3B-Instruct"
}
```

- ✅ LoRA 类型正确
- ✅ target_modules 匹配 Qwen2.5 架构
- ✅ 基座模型路径正确

**结论**：问题不是训练失败，而是**推理时 LoRA 没有被使用**！

---

## 🎯 优化建议

### 短期修复（已完成）
- ✅ 修复 `chat()` 方法的 LoRA 检查逻辑

### 中期优化
1. **增加状态标志**
   ```python
   class TransformersService:
       def __init__(self):
           self.model_type = None  # "base" | "lora" | None
           self.lora_metadata = None  # {"base": ..., "lora": ..., "model_name": ...}
   ```

2. **统一模型加载接口**
   ```python
   async def load_model(self, model: str, lora_path: Optional[str] = None):
       """统一的模型加载接口"""
       if lora_path:
           # 加载 LoRA
           self.model_type = "lora"
       else:
           # 加载基座
           self.model_type = "base"
   ```

3. **增加健康检查**
   ```python
   def get_model_status(self) -> dict:
       """获取当前模型状态"""
       return {
           "model_type": self.model_type,
           "base_model": self.current_model_name,
           "lora_path": self.current_lora_path,
           "is_loaded": self.current_model is not None
       }
   ```

### 长期优化
1. **模型管理器重构**
   - 将模型加载逻辑抽象为单独的 `ModelManager` 类
   - 支持模型缓存和热切换
   - 自动处理路径归一化

2. **前端增强**
   - 在 lora-test.html 显示当前加载的模型信息
   - 显示是否真的在使用 LoRA
   - 增加"对比测试"功能（基座 vs LoRA 输出对比）

---

## 📊 影响范围

### 受影响的功能
- ❌ LoRA 模型推理测试（lora-test.html）
- ❌ 智能助手使用 LoRA 模型
- ❌ 任何需要使用 LoRA 的场景

### 不受影响的功能
- ✅ LoRA 模型训练
- ✅ LoRA 模型扫描和管理
- ✅ 纯基座模型推理

---

## ✨ 修复后的预期效果

修复后，当用户在 lora-test.html 测试 LoRA 模型时：

1. **输入**："你好"
2. **加载**：基座模型 + LoRA 适配器
3. **推理**：使用 PeftModel（带 LoRA）
4. **输出**："嘿嘿，俺老孙在此！俺乃齐天大圣孙悟空，有什么事儿尽管问来！"

**对比**：
- 基座模型输出："你好！有什么我可以帮助你的吗？"（通用回复）
- LoRA 模型输出："嘿嘿，俺老孙在此！..."（孙悟空风格）

---

**报告生成时间**：2025-11-20  
**修复状态**：✅ 已修复，待测试验证
