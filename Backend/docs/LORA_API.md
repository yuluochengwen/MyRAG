# LoRA 微调系统 API 文档

## 概述

本文档描述 LoRA 微调训练和推理系统的 REST API 接口。所有接口均使用 JSON 格式进行数据交换。

## 基础信息

- **Base URL**: `http://localhost:8000`
- **Content-Type**: `application/json`
- **字符编码**: UTF-8

## API 端点

### 1. LoRA 模型管理

#### 1.1 获取 LoRA 模型列表

获取所有可用的 LoRA 模型。

**请求**

```http
GET /api/lora/models
```

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| base_model_id | int | 否 | 按基座模型 ID 筛选 |
| base_model_name | string | 否 | 按基座模型名称筛选 |

**响应示例**

```json
[
  {
    "id": 1,
    "name": "customer-service-lora",
    "base_model_id": null,
    "base_model_name": "Qwen3-8B",
    "file_path": "Models/LoRA/customer-service-lora",
    "file_size": 134217728,
    "training_job_id": 1,
    "status": "active",
    "created_at": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T10:30:00"
  }
]
```

#### 1.2 获取单个 LoRA 模型详情

**请求**

```http
GET /api/lora/models/{lora_id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| lora_id | int | LoRA 模型 ID |

**响应示例**

```json
{
  "id": 1,
  "name": "customer-service-lora",
  "base_model_id": null,
  "base_model_name": "Qwen3-8B",
  "file_path": "Models/LoRA/customer-service-lora",
  "file_size": 134217728,
  "training_job_id": 1,
  "status": "active",
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

**错误响应**

```json
{
  "detail": "LoRA模型不存在"
}
```

状态码：`404 Not Found`

#### 1.3 删除 LoRA 模型

删除指定的 LoRA 模型及其权重文件。

**请求**

```http
DELETE /api/lora/models/{lora_id}
```

**响应示例**

```json
{
  "message": "LoRA模型 'customer-service-lora' 已删除"
}
```

**错误响应**

```json
{
  "detail": "LoRA模型不存在"
}
```

状态码：`404 Not Found`

#### 1.4 获取基座模型列表

获取所有可用于 LoRA 训练的基座模型。

**请求**

```http
GET /api/lora/base-models
```

**响应示例**

```json
[
  {
    "name": "Qwen3-8B",
    "path": "Models/LLM/Qwen3-8B",
    "provider": "local"
  },
  {
    "name": "qwen2.5:7b",
    "path": "ollama://qwen2.5:7b",
    "provider": "ollama"
  }
]
```

### 2. 训练任务管理

#### 2.1 验证训练数据集

在提交训练前验证数据集格式。

**请求**

```http
POST /api/lora/validate-dataset
Content-Type: multipart/form-data
```

**表单参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 训练数据集文件（JSON 格式） |

**响应示例**

```json
{
  "valid": true,
  "format": "alpaca",
  "sample_count": 1000,
  "errors": []
}
```

**验证失败响应**

```json
{
  "valid": false,
  "format": "unknown",
  "sample_count": 0,
  "errors": [
    "第5行：缺少必需字段 'instruction'",
    "第12行：'output' 字段不能为空"
  ]
}
```

#### 2.2 提交训练任务

提交新的 LoRA 训练任务。

**请求**

```http
POST /api/lora/train
Content-Type: multipart/form-data
```

**表单参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| base_model_name | string | 是 | 基座模型名称 |
| lora_name | string | 是 | LoRA 权重名称 |
| dataset | file | 是 | 训练数据集文件 |
| training_mode | string | 是 | 训练模式：lora 或 qlora |
| rank | int | 否 | LoRA rank（默认：8） |
| alpha | int | 否 | LoRA alpha（默认：16） |
| dropout | float | 否 | Dropout 率（默认：0.05） |
| learning_rate | float | 否 | 学习率（默认：2e-4） |
| batch_size | int | 否 | 批次大小（默认：4） |
| num_epochs | int | 否 | 训练轮数（默认：3） |
| max_seq_length | int | 否 | 最大序列长度（默认：512） |

**响应示例**

```json
{
  "job_id": 1,
  "client_id": "train_abc123",
  "message": "训练任务已提交",
  "status": "pending"
}
```

**错误响应**

```json
{
  "detail": "基座模型 'Qwen3-8B' 不存在"
}
```

状态码：`404 Not Found`

```json
{
  "detail": "LoRA名称 'customer-service-lora' 已被使用"
}
```

状态码：`400 Bad Request`

```json
{
  "detail": "已有训练任务正在进行中，请等待完成后再提交"
}
```

状态码：`409 Conflict`

#### 2.3 获取训练任务列表

**请求**

```http
GET /api/lora/training-jobs
```

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 按状态筛选：pending, training, completed, failed, cancelled |
| limit | int | 否 | 返回数量限制（默认：50） |

**响应示例**

```json
[
  {
    "id": 1,
    "lora_model_id": 1,
    "base_model_name": "Qwen3-8B",
    "dataset_format": "alpaca",
    "training_mode": "qlora",
    "status": "completed",
    "progress": 100.0,
    "current_epoch": 3,
    "total_epochs": 3,
    "loss_history": [2.5, 1.8, 1.2],
    "created_at": "2024-01-15T10:00:00",
    "started_at": "2024-01-15T10:01:00",
    "completed_at": "2024-01-15T10:30:00"
  }
]
```

#### 2.4 获取训练任务详情

**请求**

```http
GET /api/lora/training-jobs/{job_id}
```

**响应示例**

```json
{
  "id": 1,
  "lora_model_id": 1,
  "base_model_name": "Qwen3-8B",
  "dataset_path": "data/training_data/temp/dataset_abc123.json",
  "dataset_format": "alpaca",
  "training_mode": "qlora",
  "parameters": {
    "rank": 8,
    "alpha": 16,
    "dropout": 0.05,
    "learning_rate": 0.0002,
    "batch_size": 4,
    "num_epochs": 3,
    "max_seq_length": 512
  },
  "status": "completed",
  "progress": 100.0,
  "current_epoch": 3,
  "total_epochs": 3,
  "loss_history": [2.5, 1.8, 1.2],
  "log_file_path": "data/logs/lora_training_1.log",
  "error_message": null,
  "created_at": "2024-01-15T10:00:00",
  "started_at": "2024-01-15T10:01:00",
  "completed_at": "2024-01-15T10:30:00"
}
```

#### 2.5 取消训练任务

取消正在进行的训练任务。

**请求**

```http
POST /api/lora/training-jobs/{job_id}/cancel
```

**响应示例**

```json
{
  "message": "训练任务已取消"
}
```

**错误响应**

```json
{
  "detail": "训练任务不存在或已完成"
}
```

状态码：`404 Not Found`

### 3. WebSocket 实时通信

#### 3.1 训练进度推送

连接到 WebSocket 端点以接收实时训练进度。

**连接**

```
ws://localhost:8000/ws/training/{client_id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| client_id | string | 客户端 ID（从训练提交响应中获取） |

**消息格式**

所有消息使用 JSON 格式：

```json
{
  "type": "progress|log|complete|error",
  "job_id": 1,
  "data": {}
}
```

**进度消息**

```json
{
  "type": "progress",
  "job_id": 1,
  "data": {
    "progress": 33.3,
    "epoch": 1,
    "step": 100,
    "total_steps": 300,
    "loss": 1.8,
    "eta_seconds": 600
  }
}
```

**日志消息**

```json
{
  "type": "log",
  "job_id": 1,
  "data": {
    "message": "Epoch 1/3 - Step 100/300 - Loss: 1.8"
  }
}
```

**完成消息**

```json
{
  "type": "complete",
  "job_id": 1,
  "data": {
    "lora_model_id": 1,
    "lora_name": "customer-service-lora",
    "final_loss": 1.2,
    "training_time_seconds": 1800
  }
}
```

**错误消息**

```json
{
  "type": "error",
  "job_id": 1,
  "data": {
    "error": "CUDA out of memory",
    "suggestion": "建议使用 QLoRA 模式以减少显存占用"
  }
}
```

### 4. 智能助手 LoRA 集成

#### 4.1 创建带 LoRA 的助手

**请求**

```http
POST /api/assistants
Content-Type: application/json
```

**请求体**

```json
{
  "name": "客服助手",
  "description": "专业的客服对话助手",
  "kb_ids": [1, 2],
  "llm_model": "Qwen3-8B",
  "llm_provider": "local",
  "lora_model_id": 1,
  "system_prompt": "你是一个专业的客服助手...",
  "color_theme": "blue"
}
```

**响应示例**

```json
{
  "id": 1,
  "name": "客服助手",
  "description": "专业的客服对话助手",
  "kb_ids": [1, 2],
  "kb_names": ["产品知识库", "FAQ"],
  "embedding_model": "bge-large-zh-v1.5",
  "llm_model": "Qwen3-8B",
  "llm_provider": "local",
  "lora_model_id": 1,
  "system_prompt": "你是一个专业的客服助手...",
  "color_theme": "blue",
  "status": "active",
  "created_at": "2024-01-15T11:00:00",
  "updated_at": "2024-01-15T11:00:00"
}
```

**错误响应**

```json
{
  "detail": "LoRA模型 'customer-service-lora' 的基座模型是 'Qwen2-7B'，与选择的LLM模型 'Qwen3-8B' 不匹配"
}
```

状态码：`400 Bad Request`

#### 4.2 对话时自动使用 LoRA

当助手配置了 `lora_model_id` 时，对话 API 会自动使用 LoRA 推理。

**请求**

```http
POST /api/conversations/{conversation_id}/chat
Content-Type: application/json
```

**请求体**

```json
{
  "query": "如何退货？",
  "temperature": 0.7,
  "max_tokens": 2048
}
```

**响应示例**

```json
{
  "answer": "根据我们的退货政策...",
  "sources": [
    {
      "content": "退货政策：购买后7天内...",
      "similarity": 0.92,
      "file_id": 1
    }
  ],
  "embedding_model": "bge-large-zh-v1.5",
  "retrieval_count": 3
}
```

**注意**：如果 LoRA 加载失败，系统会自动回退到基座模型，确保服务可用性。

## 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 409 | 资源冲突（如训练任务已在进行） |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

## 数据格式

### Alpaca 格式

```json
[
  {
    "instruction": "用户指令",
    "input": "可选的输入上下文",
    "output": "期望的输出"
  }
]
```

### Conversation 格式

```json
[
  {
    "conversations": [
      {"role": "user", "content": "用户消息"},
      {"role": "assistant", "content": "助手回复"}
    ]
  }
]
```

## 最佳实践

1. **训练前验证**：始终先调用 `/api/lora/validate-dataset` 验证数据集
2. **WebSocket 连接**：提交训练后立即建立 WebSocket 连接以接收实时进度
3. **错误处理**：处理 OOM 错误时，建议用户切换到 QLoRA 模式
4. **LoRA 匹配**：创建助手时确保 LoRA 模型与基座模型匹配
5. **资源管理**：训练完成后及时清理不需要的 LoRA 模型以节省磁盘空间

## 示例代码

### Python 客户端示例

```python
import requests
import json

# 1. 提交训练任务
with open('training_data.json', 'rb') as f:
    files = {'dataset': f}
    data = {
        'base_model_name': 'Qwen3-8B',
        'lora_name': 'my-lora',
        'training_mode': 'qlora',
        'num_epochs': 3
    }
    response = requests.post('http://localhost:8000/api/lora/train', 
                            files=files, data=data)
    result = response.json()
    job_id = result['job_id']
    client_id = result['client_id']

# 2. 连接 WebSocket 接收进度
import websocket

def on_message(ws, message):
    data = json.loads(message)
    if data['type'] == 'progress':
        print(f"进度: {data['data']['progress']}%")
    elif data['type'] == 'complete':
        print("训练完成！")
        ws.close()

ws = websocket.WebSocketApp(f"ws://localhost:8000/ws/training/{client_id}",
                            on_message=on_message)
ws.run_forever()
```

### JavaScript 客户端示例

```javascript
// 1. 提交训练任务
const formData = new FormData();
formData.append('dataset', fileInput.files[0]);
formData.append('base_model_name', 'Qwen3-8B');
formData.append('lora_name', 'my-lora');
formData.append('training_mode', 'qlora');

const response = await fetch('http://localhost:8000/api/lora/train', {
    method: 'POST',
    body: formData
});
const result = await response.json();

// 2. 连接 WebSocket
const ws = new WebSocket(`ws://localhost:8000/ws/training/${result.client_id}`);

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'progress') {
        console.log(`进度: ${data.data.progress}%`);
    } else if (data.type === 'complete') {
        console.log('训练完成！');
        ws.close();
    }
};
```

## 性能指标

- **LoRA 推理速度**：不低于基座模型的 80%
- **WebSocket 推送延迟**：< 1 秒
- **LoRA 模型加载时间**：< 5 秒
- **训练队列**：单任务队列，同时只能有一个训练任务

## 限制

- **数据集大小**：最大 10,000 条样本
- **并发训练**：同时只能运行一个训练任务
- **文件大小**：训练数据集文件最大 100MB
- **模型缓存**：最多缓存 2 个基座模型和 5 个 LoRA 模型

## 更新日志

### v1.0.0 (2024-01-15)
- 初始版本发布
- 支持 LoRA 和 QLoRA 训练模式
- 实时训练进度推送
- 智能助手 LoRA 集成
- 自动回退机制
