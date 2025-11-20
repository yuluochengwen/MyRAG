# LoRA 部署到 Ollama - 问题说明与解决方案

## 🔴 **当前问题**

简易训练生成的 LoRA 模型无法直接部署到 Ollama，原因：

**Ollama 的 ADAPTER 功能不完全支持 HuggingFace PEFT 格式的 LoRA adapter**

---

## 📖 **什么是"部署到 Ollama"？**

### 完整流程：

```
1️⃣ 训练阶段
   使用 PEFT + Transformers 训练
   ↓
   生成 LoRA adapter 文件：
   - adapter_config.json
   - adapter_model.safetensors
   
2️⃣ 部署阶段（当前卡住）
   将 LoRA 注册到 Ollama
   ↓
   使 LoRA 可以通过 Ollama API 调用
   
3️⃣ 使用阶段
   在智能助手中绑定该 LoRA
   ↓
   对话时自动使用该 LoRA 的能力
```

---

## 🛠️ **解决方案**

###方案 1：合并 LoRA 后部署（推荐，自动化）

**原理**：将 LoRA 合并到基座模型，生成完整模型，然后导入 Ollama

**步骤**：

1. **手动合并 LoRA**（在 MyRAG 环境中）：

```python
# 在 PowerShell 中执行
cd C:\Users\Man\Desktop\MyRAG\Models\LoRA\777_20251120_031210

# 创建 merge.py 文件
@'
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from pathlib import Path

# 路径配置
base_model_path = r"C:\Users\Man\Desktop\MyRAG\Models\LLM\DeepSeek-R1-Distill-Qwen-1.5B"
lora_path = r"C:\Users\Man\Desktop\MyRAG\Models\LoRA\777_20251120_031210"
output_path = Path(lora_path) / "merged_model"
output_path.mkdir(exist_ok=True)

print("1/4 加载基座模型...")
base_model = AutoModelForCausalLM.from_pretrained(
    base_model_path,
    torch_dtype=torch.float16,
    device_map="cpu",
    trust_remote_code=True
)

print("2/4 加载 tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    base_model_path,
    trust_remote_code=True
)

print("3/4 加载并合并 LoRA...")
model = PeftModel.from_pretrained(base_model, lora_path)
model = model.merge_and_unload()

print("4/4 保存合并后的模型...")
model.save_pretrained(str(output_path))
tokenizer.save_pretrained(str(output_path))

print(f"✅ 合并完成！模型已保存到: {output_path}")
'@ | Out-File -FilePath merge.py -Encoding utf8

# 激活环境并执行
conda activate MyRAG
python merge.py
```

2. **导入到 Ollama**：

```powershell
# 创建 Modelfile
cd C:\Users\Man\Desktop\MyRAG\Models\LoRA\777_20251120_031210\merged_model

@'
FROM ./
PARAMETER temperature 0.7
PARAMETER top_p 0.9
'@ | Out-File -FilePath Modelfile -Encoding utf8

# 导入 Ollama
ollama create my-custom-lora -f Modelfile
```

3. **测试模型**：

```powershell
ollama run my-custom-lora "你好"
```

---

### 方案 2：转换为 GGUF 格式（高级，手动）

**原理**：使用 llama.cpp 工具将模型转换为 GGUF 格式

**步骤**：

1. 先执行方案1的合并步骤
2. 下载 llama.cpp：https://github.com/ggerganov/llama.cpp
3. 转换模型：
```bash
python convert.py merged_model/
```
4. 量化模型（可选）：
```bash
./quantize merged_model/ggml-model-f16.gguf merged_model/ggml-model-q4_0.gguf q4_0
```
5. 导入 Ollama：
```powershell
ollama create my-lora-q4 -f ggml-model-q4_0.gguf
```

---

### 方案 3：直接使用 Python API（临时方案）

**不部署到 Ollama，直接在 Python 中加载使用**

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# 加载基座
base = AutoModelForCausalLM.from_pretrained("base_model_path")
# 加载 LoRA
model = PeftModel.from_pretrained(base, "lora_path")

# 推理
inputs = tokenizer("你好", return_tensors="pt")
outputs = model.generate(**inputs)
```

---

##⚙️ **自动化方案（开发中）**

我正在更新代码，实现自动合并 + 部署功能：

**新的部署流程**：

```
点击"部署"按钮
  ↓
后台自动执行：
  1. 检测到 PEFT LoRA 格式
  2. 自动合并到基座模型
  3. 保存合并后的模型到 merged_model/
  4. 创建 Modelfile
  5. 注册到 Ollama
  6. 更新数据库状态
  ↓
部署完成，可以使用！
```

---

## 🎯 **推荐操作（当前）**

### 快速测试方案：

```powershell
# 1. 进入 LoRA 目录
cd C:\Users\Man\Desktop\MyRAG\Models\LoRA\777_20251120_031210

# 2. 激活环境
conda activate MyRAG

# 3. 执行合并（复制上面的 merge.py 内容）
python merge.py

# 4. 导入 Ollama
cd merged_model
ollama create test-777-lora -f Modelfile

# 5. 测试
ollama run test-777-lora "测试一下训练效果"
```

---

## 📊 **为什么 Ollama ADAPTER 不工作？**

可能原因：

1. **格式不兼容**：Ollama 可能期望特定格式的 LoRA
2. **路径问题**：Windows 路径处理问题
3. **版本问题**：Ollama 版本可能不支持 PEFT 格式
4. **配置问题**：adapter_config.json 格式不符合 Ollama 预期

---

## ✅ **下一步计划**

我会更新代码，实现：

1. ✅ 自动检测 LoRA 格式
2. ✅ 自动合并到基座模型
3. ✅ 自动导入 Ollama
4. ✅ 一键部署流程

**预计完成时间：10-15 分钟**

---

## 💡 **临时解决方案（最快）**

使用合并后的模型，手动注册：

```powershell
# 按照"方案1"的步骤执行即可
# 大约需要 5-10 分钟完成
```

---

**现在您明白"部署"的含义了吗？** 🎓

简单说：
- ✅ 训练 = 生成 LoRA adapter 文件
- ❌ 部署 = 让 Ollama 能够使用这个 LoRA（当前卡住）
- 🔧 解决 = 先合并，再导入 Ollama
