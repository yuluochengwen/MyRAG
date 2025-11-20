# 简易 LoRA 训练功能使用说明

## 📚 **功能概述**

全新的简化版 LoRA 微调系统，使用 Hugging Face PEFT 框架，操作简单，自动化程度高。

### **技术栈**
- **训练框架**: Hugging Face PEFT (Parameter-Efficient Fine-Tuning)
- **模型加载**: Transformers + BitsAndBytes (4-bit 量化)
- **训练优化**: LoRA + Gradient Checkpointing + QLoRA
- **前端**: Tailwind CSS + Vanilla JS

---

## 🚀 **快速开始**

### **1. 安装依赖**

```powershell
# 进入后端目录
cd C:\Users\Man\Desktop\MyRAG\Backend

# 激活环境
conda activate MyRAG

# 安装新的训练依赖
pip install peft>=0.11.0 datasets>=2.18.0 trl>=0.8.0
```

### **2. 初始化数据库**

执行 SQL 脚本创建训练任务表：

```powershell
# 使用 MySQL 客户端执行
mysql -u root -p rag_system < scripts/init_simple_lora_tables.sql
```

或者在 MySQL Workbench 中执行：

```sql
-- 复制 Backend/scripts/init_simple_lora_tables.sql 的内容并执行
```

### **3. 启动后端服务**

```powershell
# 确保在 MyRAG 环境中
python Backend/main.py
```

### **4. 访问训练页面**

打开浏览器访问：

```
http://localhost:8000/static/simple-lora-training.html
```

---

## 📖 **使用流程**

### **步骤 1: 准备数据集**

支持两种格式：

#### **Alpaca 格式** (推荐)

```json
[
    {
        "instruction": "请解释什么是机器学习",
        "input": "",
        "output": "机器学习是人工智能的一个分支..."
    },
    {
        "instruction": "将以下句子翻译成英文",
        "input": "今天天气真好",
        "output": "The weather is really nice today"
    }
]
```

#### **ShareGPT 格式**

```json
[
    {
        "conversations": [
            {"from": "human", "value": "你好，请介绍一下自己"},
            {"from": "gpt", "value": "你好！我是一个AI助手..."}
        ]
    }
]
```

### **步骤 2: 上传数据集**

1. 在训练页面点击上传区域或拖拽 JSON 文件
2. 选择数据集格式（Alpaca 或 ShareGPT）
3. 等待上传完成

### **步骤 3: 选择基座模型**

从下拉列表中选择已下载的基座模型，例如：
- `DeepSeek-R1-Distill-Qwen-1.5B`
- 其他 HuggingFace 格式模型

### **步骤 4: 输入任务名称**

为训练任务起一个易于识别的名称，例如：
- `customer_service_lora`
- `medical_qa_v1`

### **步骤 5: 开始训练**

点击"开始训练"按钮，系统将：
1. 自动配置训练参数（针对 RTX 3060 6GB 优化）
2. 加载基座模型（4-bit 量化）
3. 配置 LoRA 适配器
4. 开始训练（后台运行）
5. 自动保存到 `Models/LoRA/<任务名>_<时间戳>/`

### **步骤 6: 监控进度**

训练任务会显示在右侧列表中，实时更新：
- 进度百分比
- 当前状态（等待中/训练中/已完成/失败）
- 当前轮次
- 创建时间

---

## ⚙️ **自动配置参数**

系统已针对 **RTX 3060 6GB** 显卡优化，无需手动调整：

| 参数 | 值 | 说明 |
|------|------|------|
| LoRA Rank | 16 | 适配器秩 |
| LoRA Alpha | 32 | 缩放系数 |
| LoRA Dropout | 0.05 | 防止过拟合 |
| 训练轮次 | 3 | 足够收敛 |
| 批次大小 | 4 | 显存友好 |
| 梯度累积 | 4 | 有效 batch=16 |
| 学习率 | 2e-4 | 适中学习率 |
| 量化 | 4-bit | QLoRA 技术 |
| 最大序列长度 | 512 | token 限制 |

---

## 📁 **输出结构**

训练完成后，LoRA 模型保存在：

```
Models/LoRA/
└── <任务名>_<时间戳>/
    ├── adapter_config.json          # LoRA 配置
    ├── adapter_model.safetensors    # LoRA 权重
    ├── tokenizer_config.json        # 分词器配置
    └── special_tokens_map.json      # 特殊 token 映射
```

---

## 🔧 **API 接口**

### **1. 获取基座模型列表**

```http
GET /api/simple-lora/models
```

**响应示例:**

```json
{
    "models": [
        {
            "name": "DeepSeek-R1-Distill-Qwen-1.5B",
            "path": "C:\\...\\Models\\LLM\\DeepSeek-R1-Distill-Qwen-1.5B",
            "size_mb": 3024.5
        }
    ],
    "count": 1
}
```

### **2. 上传数据集**

```http
POST /api/simple-lora/upload-dataset
Content-Type: multipart/form-data

file: <JSON文件>
dataset_type: alpaca
```

**响应示例:**

```json
{
    "filename": "my_dataset.json",
    "path": "C:\\...\\TrainingData\\my_dataset.json",
    "size_mb": 2.5,
    "message": "上传成功"
}
```

### **3. 创建训练任务**

```http
POST /api/simple-lora/train
Content-Type: multipart/form-data

task_name: my_lora
base_model: DeepSeek-R1-Distill-Qwen-1.5B
dataset_filename: my_dataset.json
dataset_type: alpaca
```

**响应示例:**

```json
{
    "task_id": 1,
    "task_name": "my_lora",
    "status": "running",
    "message": "训练任务已启动"
}
```

### **4. 查询任务状态**

```http
GET /api/simple-lora/tasks/{task_id}
```

**响应示例:**

```json
{
    "task_id": 1,
    "task_name": "my_lora",
    "status": "running",
    "progress": 65.5,
    "current_epoch": 2,
    "message": "开始训练...",
    "created_at": "2025-11-20T12:30:00",
    "completed_at": null
}
```

### **5. 获取所有任务**

```http
GET /api/simple-lora/tasks
```

---

## 🎯 **训练建议**

### **数据集大小**

| 样本数 | 训练时间（估算） | 建议用途 |
|--------|-----------------|---------|
| 100-500 | 10-30分钟 | 测试、小规模微调 |
| 500-2000 | 30-90分钟 | 中等规模任务 |
| 2000-10000 | 1.5-6小时 | 大规模任务 |

### **显卡内存**

- **6GB (RTX 3060)**: 当前参数已优化，推荐 batch_size=4
- **8GB (RTX 3070)**: 可增加到 batch_size=8
- **12GB+**: 可调大 max_seq_length 到 1024

### **数据质量**

1. **指令清晰**: instruction 要明确具体
2. **回答准确**: output 要正确完整
3. **多样性**: 覆盖不同场景和问题类型
4. **格式统一**: 保持一致的 JSON 格式

---

## ❗ **常见问题**

### **Q: 训练失败怎么办？**

A: 查看任务状态中的错误消息，常见原因：
- 显存不足：减少 batch_size 或 max_seq_length
- 数据格式错误：检查 JSON 格式是否正确
- 基座模型不存在：确认模型已下载到 Models/LLM/

### **Q: 训练完成后如何使用？**

A: 有两种方式：
1. **部署到 Ollama**（推荐）:
   - 进入"模型管理"页面
   - 切换到"LoRA 管理"标签
   - 点击"扫描新模型"
   - 点击"部署"按钮

2. **直接加载**:
   ```python
   from peft import PeftModel
   model = PeftModel.from_pretrained(base_model, "Models/LoRA/<任务名>")
   ```

### **Q: 可以中途停止训练吗？**

A: 目前不支持手动停止，训练会在后台完成。建议：
- 先用小数据集测试
- 确认无误后再训练完整数据集

### **Q: 支持多 GPU 吗？**

A: 当前版本使用 `device_map="auto"`，会自动利用可用的 GPU。多 GPU 训练需要修改代码启用 DeepSpeed 或 FSDP。

---

## 🔄 **与模型管理页面集成**

训练完成后：

1. 访问 `http://localhost:8000/static/model-management.html`
2. 切换到"LoRA 管理"标签
3. 点击"扫描新模型"按钮
4. 新训练的 LoRA 会自动出现
5. 点击"部署"即可部署到 Ollama
6. 在智能助手中绑定 LoRA 模型

---

## 📊 **数据库表结构**

```sql
CREATE TABLE simple_lora_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_name VARCHAR(255) NOT NULL,
    base_model VARCHAR(255) NOT NULL,
    dataset_file VARCHAR(512) NOT NULL,
    dataset_type VARCHAR(50) DEFAULT 'alpaca',
    output_path VARCHAR(512) NOT NULL,
    training_params JSON,
    status ENUM('pending', 'running', 'completed', 'failed'),
    progress DECIMAL(5,2) DEFAULT 0.00,
    current_epoch INT DEFAULT 0,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL
);
```

---

## 🎉 **完成！**

现在您可以：
1. 上传数据集
2. 一键启动训练
3. 实时监控进度
4. 自动保存模型
5. 轻松部署使用

无需复杂配置，专注于数据和应用场景！
