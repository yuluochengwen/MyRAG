# LoRA 推理与训练代码深度分析报告

## 1. 推理代码分析 (Inference Analysis)

针对 "LoRA 激活后是否真正生效" 的疑问，我对 `Backend/app/services/transformers_service.py` 和 `Backend/app/api/lora_training.py` 进行了详细的代码审查。

### 结论
**代码逻辑是正确的，LoRA 适配器确实被激活并用于推理。**

### 详细追踪
1. **加载阶段 (`load_model_with_lora`)**:
   - 代码使用 `PeftModel.from_pretrained(base_model_obj, lora_path, ...)` 加载模型。
   - 这会将基座模型包装在 `PeftModel` 类中。`PeftModel` 会拦截 `forward` 调用并注入 LoRA 层的计算。
   - `self.current_model` 被赋值为这个 `PeftModel` 实例。
   - `self.current_lora_path` 被设置，标记当前处于 LoRA 模式。

2. **推理阶段 (`chat`)**:
   - 当调用 `/models/{model_id}/test` 接口时，它先调用 `load_model_with_lora`，然后调用 `chat`。
   - 在 `chat` 方法中，有一个关键的检查逻辑：
     ```python
     if self.current_model_name != model:
         if self.current_lora_path is None:
             # ... (重载基座模型)
         else:
             # 已加载 LoRA，跳过重载，直接使用当前模型
             logger.info(f"已加载 LoRA 模型...")
     ```
   - 由于 `load_model_with_lora` 将 `current_model_name` 设置为绝对路径，而 `chat` 传入的是模型目录名，两者不相等，因此会进入检查。
   - 检查发现 `current_lora_path` 存在，因此**不会**卸载当前的 `PeftModel`，而是直接使用它进行生成。

3. **生成阶段 (`generate`)**:
   - 代码调用 `self.current_model.generate(...)`。
   - 由于 `self.current_model` 是 `PeftModel`，它会自动应用 LoRA 权重。

---

## 2. 为什么感觉 "没有微调痕迹"？ (Root Cause Analysis)

既然推理代码没有问题，那么问题很可能出在**训练阶段**。

### 发现重大缺陷：训练 Loss 计算策略
在 `Backend/app/services/simple_lora_trainer.py` 的 `_load_dataset` 方法中，我发现了以下代码：

```python
# 5. 创建 Labels (只对 Assistant 回复部分计算 Loss)
# 这是一个简化的策略：对整个序列计算 Loss...
# 为了保证效果且简化代码，这里我们对整个序列计算 Loss (除了 padding)
labels = input_ids.clone()
```

**问题所在**：
- 当前代码对**整个对话序列**（包括用户的 Instruction/Input 和 Assistant 的 Output）都计算了 Loss。
- 这意味着模型不仅在学习"如何回答"，还在学习"如何提问"（即复读用户的输入）。
- 对于指令微调（Instruction Tuning），标准做法是**Mask 掉用户输入的 Loss**，只计算模型回答部分的 Loss。
- **后果**：在数据量较少（如 < 200 条）的情况下，模型的大部分“精力”被分散去学习 Prompt 的分布，而不是回复的分布，导致微调效果极不明显，甚至出现复读机现象。

## 3. 修复建议

建议立即修改 `Backend/app/services/simple_lora_trainer.py`，实现**Data Masking**，只对 Assistant 的回复计算 Loss。

### 修复方案预览
我们需要在 `format_dataset` 中找到 User 和 Assistant 的分界线，并将 User 部分的 `labels` 设置为 `-100`（PyTorch 中忽略 Loss 的标记）。

这将显著提升微调的针对性和效果。
