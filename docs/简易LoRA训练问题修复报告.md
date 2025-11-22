# 简易LoRA训练问题修复报告

## 🔍 问题诊断

经过全面分析，发现简易LoRA训练存在**3个核心问题**导致训练出的模型无效：

### 问题1：数据集格式化错误 ❌

**症状**：模型训练后没有学到特定的知识，回答泛化

**根本原因**：
```python
# 错误的做法（旧代码）
tokenized["labels"] = tokenized["input_ids"].copy()  # ❌ 学习全部内容
```

这会导致模型学习**整个序列**（包括instruction部分），而不是只学习回答部分。正确的做法是：
- instruction 部分的 labels 应该设为 `-100`（不计算损失）
- 只有 response 部分应该有实际的 token labels

**修复方案**：
```python
# 正确的做法（新代码）
# 分别tokenize prompt和response
prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
response_ids = tokenizer(response, add_special_tokens=False)["input_ids"]

# 组合序列
input_ids = prompt_ids + response_ids + [tokenizer.eos_token_id]

# labels：prompt部分为-100，response部分为实际token
labels = [-100] * len(prompt_ids) + response_ids + [tokenizer.eos_token_id]
```

---

### 问题2：模型保存方式错误 ❌

**症状**：保存的模型文件过大（接近完整模型大小），或缺少 `adapter_config.json`

**根本原因**：
```python
# 错误的做法（旧代码）
trainer.save_model(str(output_path))  # ❌ 保存完整模型
```

这会保存**完整的量化模型**，而不是只保存LoRA适配器权重。

**修复方案**：
```python
# 正确的做法（新代码）
model.save_pretrained(str(output_path))  # ✅ 只保存LoRA适配器
tokenizer.save_pretrained(str(output_path))

# 验证文件完整性
adapter_config = output_path / "adapter_config.json"
adapter_model = output_path / "adapter_model.safetensors"
# 必须包含这两个文件
```

**正确保存的文件结构**：
```
Models/LoRA/task_name_20241120_123456/
├── adapter_config.json      # ✅ LoRA配置
├── adapter_model.safetensors # ✅ LoRA权重（仅几MB到几十MB）
└── tokenizer相关文件
```

---

### 问题3：target_modules 不匹配 ⚠️

**症状**：训练时报错或LoRA没有作用到正确的层

**根本原因**：
不同模型架构的attention层命名不同：
- **LLaMA/Qwen2**: `q_proj`, `v_proj`, `k_proj`, `o_proj`
- **Qwen1**: `c_attn`
- **ChatGLM**: `query_key_value`
- **Baichuan**: `W_pack`

硬编码的 `target_modules` 无法适配所有模型。

**修复方案**：
添加了自动检测功能：
```python
def _detect_target_modules(self, model) -> list:
    """自动检测模型的attention层名称"""
    # 1. 尝试预定义映射
    architecture_mapping = {
        "LlamaForCausalLM": ["q_proj", "v_proj", "k_proj", "o_proj"],
        "Qwen2ForCausalLM": ["q_proj", "v_proj", "k_proj", "o_proj"],
        "QWenLMHeadModel": ["c_attn"],
        ...
    }
    
    # 2. 如果没有预定义，扫描模型结构
    # 查找包含 "attn", "attention", "query", "key", "value" 的层
    
    # 3. 降级：使用LLaMA默认值
```

---

## ✅ 已修复内容

### 1. 服务层修复 (`simple_lora_trainer.py`)

#### 1.1 数据集格式化修复
- ✅ Alpaca 格式：只学习 response 部分
- ✅ ShareGPT 格式：只学习 assistant 回复部分
- ✅ 正确处理 tokenization 和 padding

#### 1.2 模型保存修复
- ✅ 使用 `model.save_pretrained()` 代替 `trainer.save_model()`
- ✅ 添加文件完整性验证
- ✅ 输出详细的保存日志

#### 1.3 target_modules 自动检测
- ✅ 添加 `_detect_target_modules()` 方法
- ✅ 支持主流模型架构的自动识别
- ✅ 降级策略确保兼容性

#### 1.4 训练日志增强
- ✅ 输出完整的训练路径
- ✅ 提示用户去模型管理页面扫描
- ✅ 详细的文件验证信息

### 2. API层增强 (`simple_lora.py`)

- ✅ 返回消息包含后续操作提示
- ✅ 改进错误处理和日志记录

### 3. 前端增强 (`simple-lora-training.js`)

- ✅ 训练完成后显示明确提示：前往模型管理页面扫描
- ✅ Toast 消息支持自定义显示时长
- ✅ 任务列表显示后续操作指引

---

## 📋 使用流程（修复后）

### 完整训练和使用流程：

1. **准备数据集**
   ```json
   // Alpaca格式（推荐）
   [
     {
       "instruction": "解释什么是机器学习",
       "input": "",
       "output": "机器学习是人工智能的一个分支..."
     }
   ]
   ```

2. **创建训练任务**
   - 访问：`http://localhost:8000/static/simple-lora-training.html`
   - 上传数据集（JSON格式）
   - 选择基座模型（从 `Models/LLM/` 目录）
   - 输入任务名称
   - 点击"开始训练"

3. **等待训练完成**
   - 页面会显示实时进度
   - 训练完成后会提示："训练完成！请前往模型管理页面扫描LoRA模型以使用"

4. **扫描LoRA模型** ⚠️ **关键步骤**
   - 前往：`http://localhost:8000/static/model-management.html`
   - 切换到"LoRA模型"标签
   - 点击"扫描训练输出"按钮
   - 系统会自动发现新训练的LoRA模型

5. **激活LoRA模型**
   - 在扫描到的模型卡片上点击"激活"按钮
   - 激活后可以进行推理测试

6. **使用LoRA模型**
   
   **方式1：推理测试**
   - 在模型管理页面点击"测试推理"
   - 输入测试Prompt
   - 查看模型输出

   **方式2：在智能助手中使用**
   - 创建/编辑智能助手时选择该LoRA模型
   - 助手将自动使用微调后的模型进行对话

---

## 🔧 技术细节

### LoRA 适配器结构

训练完成后的文件结构：
```
Models/LoRA/
└── task_name_20241120_123456/
    ├── adapter_config.json          # LoRA配置
    │   ├── base_model_name_or_path  # 基座模型路径
    │   ├── r (rank)                 # LoRA rank
    │   ├── lora_alpha               # LoRA alpha
    │   ├── target_modules           # 应用LoRA的层
    │   └── ...
    │
    ├── adapter_model.safetensors    # LoRA权重（主要文件）
    │   └── 大小通常：几MB到几十MB
    │
    └── tokenizer相关文件
        ├── tokenizer_config.json
        └── special_tokens_map.json
```

### 加载 LoRA 的过程

```python
# 1. 加载基座模型（量化）
base_model = AutoModelForCausalLM.from_pretrained(
    base_model_path,
    load_in_4bit=True,
    device_map="auto"
)

# 2. 加载LoRA适配器
model = PeftModel.from_pretrained(
    base_model,
    lora_path,  # Models/LoRA/task_name_xxx/
    torch_dtype=torch.float16
)

# 3. 推理
model.eval()
output = model.generate(...)
```

---

## ⚠️ 常见问题

### Q1：训练完成后找不到模型？
**A**：训练完成后需要手动扫描：
1. 前往模型管理页面
2. 切换到"LoRA模型"标签
3. 点击"扫描训练输出"

### Q2：模型文件很大（几GB）？
**A**：说明保存方式有问题，应该只有几MB到几十MB。请检查：
- 是否使用了修复后的代码
- 训练日志中是否显示"✅ LoRA训练完成"

### Q3：加载LoRA时报错找不到 adapter_config.json？
**A**：检查文件结构是否完整：
```bash
ls Models/LoRA/your_task_name/
# 应该包含：
# - adapter_config.json
# - adapter_model.safetensors (或 .bin)
```

### Q4：LoRA模型没有效果？
**A**：可能原因：
1. **数据集太小**：建议至少100条高质量样本
2. **训练轮次不足**：尝试增加到5-10轮
3. **数据格式问题**：确认使用修复后的代码
4. **基座模型不匹配**：确保推理时使用的基座模型与训练时一致

### Q5：如何验证LoRA是否生效？
**A**：
1. 对比训练前后的输出
2. 使用训练数据中的例子进行测试
3. 检查LoRA文件大小（应该很小）
4. 查看训练日志中的损失下降曲线

---

## 📝 训练建议

### 数据集质量
- ✅ **数量**：至少50-100条高质量样本
- ✅ **质量**：确保instruction清晰、output准确
- ✅ **多样性**：覆盖不同的场景和问题类型
- ✅ **格式**：严格遵循Alpaca或ShareGPT格式

### 训练参数
```python
推荐参数（RTX 3060 6GB）：
- lora_rank: 16-32（越大越强但显存需求越高）
- num_epochs: 3-5（数据少时可增加）
- batch_size: 4（根据显存调整）
- learning_rate: 2e-4（标准值）
```

### 验证方法
1. 查看训练loss曲线（应该持续下降）
2. 使用验证集测试
3. 人工评估输出质量
4. 对比基座模型输出

---

## 🎯 后续优化建议

1. **自动扫描**：训练完成后自动触发模型扫描
2. **训练监控**：添加实时loss曲线显示
3. **模型评估**：集成自动评估脚本
4. **数据集验证**：上传时自动检查格式
5. **超参数调优**：提供UI界面调整训练参数

---

## 📚 参考资料

- [PEFT 官方文档](https://huggingface.co/docs/peft)
- [LoRA 论文](https://arxiv.org/abs/2106.09685)
- [Alpaca 数据集格式](https://github.com/tatsu-lab/stanford_alpaca)
- [ShareGPT 格式说明](https://huggingface.co/datasets/anon8231489123/ShareGPT_Vicuna_unfiltered)

---

**修复完成时间**：2025年11月20日  
**修复人员**：AI Assistant  
**版本**：v2.0
