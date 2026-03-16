# LoRA 微调系统测试和验证指南

## 概述

本文档提供 LoRA 微调系统的完整测试和验证流程，包括单元测试、集成测试、性能测试和端到端测试。

## 测试环境要求

### 硬件要求

- **CPU**: 4核以上
- **内存**: 16GB 以上
- **GPU**: NVIDIA GPU with CUDA support（用于实际训练测试）
  - 最小显存：8GB（QLoRA 模式）
  - 推荐显存：16GB+（LoRA 模式）
- **磁盘空间**: 50GB 以上

### 软件要求

- Python 3.11+
- MySQL 8.0+
- CUDA 11.8+ (如果使用 GPU)
- 所有依赖包（见 requirements.txt）

## 测试分类

### 1. 单元测试

测试单个组件的功能。

#### 数据验证服务测试

```bash
# 测试数据集验证
pytest Backend/tests/test_lora_integration.py::TestDatasetValidator -v
```

**验证点**：
- ✓ Alpaca 格式识别
- ✓ Conversation 格式识别
- ✓ 无效格式检测
- ✓ 样本计数准确性
- ✓ 错误信息完整性

#### LoRA 管理服务测试

```bash
# 测试 LoRA 模型管理
pytest Backend/tests/test_lora_integration.py::TestLoRAService -v
```

**验证点**：
- ✓ 模型扫描功能
- ✓ 按基座模型筛选
- ✓ 模型删除功能
- ✓ 文件大小计算

#### LoRA 推理服务测试

```bash
# 测试 LoRA 推理
pytest Backend/tests/test_lora_integration.py::TestLoRAInferenceService -v
```

**验证点**：
- ✓ 缓存管理
- ✓ 模型加载
- ✓ 模型卸载
- ✓ LRU 淘汰策略

### 2. API 集成测试

测试 REST API 端点。

```bash
# 测试所有 API 端点
pytest Backend/tests/test_lora_integration.py::TestLoRAAPI -v
```

**验证点**：
- ✓ GET /api/lora/models - 获取模型列表
- ✓ GET /api/lora/models/{id} - 获取模型详情
- ✓ DELETE /api/lora/models/{id} - 删除模型
- ✓ GET /api/lora/base-models - 获取基座模型
- ✓ POST /api/lora/validate-dataset - 验证数据集
- ✓ POST /api/lora/train - 提交训练
- ✓ GET /api/lora/training-jobs - 获取训练任务
- ✓ POST /api/lora/training-jobs/{id}/cancel - 取消训练

### 3. 端到端测试

测试完整的用户工作流。

#### 测试场景 1：完整训练流程

**步骤**：

1. **准备训练数据**
```bash
# 创建测试数据集
cat > test_dataset.json << EOF
[
  {
    "instruction": "解释什么是机器学习",
    "input": "",
    "output": "机器学习是人工智能的一个分支..."
  }
]
EOF
```

2. **验证数据集**
```bash
curl -X POST http://localhost:8000/api/lora/validate-dataset \
  -F "file=@test_dataset.json"
```

**预期结果**：
```json
{
  "valid": true,
  "format": "alpaca",
  "sample_count": 1,
  "errors": []
}
```

3. **提交训练任务**
```bash
curl -X POST http://localhost:8000/api/lora/train \
  -F "base_model_name=Qwen3-8B" \
  -F "lora_name=test-lora" \
  -F "dataset=@test_dataset.json" \
  -F "training_mode=qlora" \
  -F "num_epochs=1"
```

**预期结果**：
```json
{
  "job_id": 1,
  "client_id": "train_abc123",
  "message": "训练任务已提交",
  "status": "pending"
}
```

4. **监控训练进度**
```javascript
// 使用 WebSocket 连接
const ws = new WebSocket('ws://localhost:8000/ws/training/train_abc123');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

**预期消息**：
- progress 消息（定期更新）
- log 消息（训练日志）
- complete 消息（训练完成）

5. **验证 LoRA 模型创建**
```bash
curl http://localhost:8000/api/lora/models
```

**预期结果**：列表中包含新创建的 `test-lora` 模型

#### 测试场景 2：助手 LoRA 集成

**步骤**：

1. **创建带 LoRA 的助手**
```bash
curl -X POST http://localhost:8000/api/assistants \
  -H "Content-Type: application/json" \
  -d '{
    "name": "测试助手",
    "llm_model": "Qwen3-8B",
    "llm_provider": "local",
    "lora_model_id": 1,
    "embedding_model": "bge-large-zh-v1.5",
    "system_prompt": "你是一个测试助手"
  }'
```

**预期结果**：助手创建成功，返回包含 `lora_model_id` 的响应

2. **创建对话**
```bash
curl -X POST http://localhost:8000/api/conversations \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": 1,
    "title": "测试对话"
  }'
```

3. **发送消息（使用 LoRA 推理）**
```bash
curl -X POST http://localhost:8000/api/conversations/1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "你好",
    "temperature": 0.7
  }'
```

**预期结果**：
- 返回 AI 回复
- 后台日志显示使用了 LoRA 推理
- 如果 LoRA 加载失败，自动回退到基座模型

#### 测试场景 3：错误处理

**测试 OOM 错误**：

1. 使用 LoRA 模式训练大模型（故意触发 OOM）
2. 验证错误消息包含 QLoRA 建议

**测试 LoRA 不匹配**：

1. 尝试创建助手，使用不匹配的 LoRA 模型
2. 验证返回 400 错误和清晰的错误信息

**测试并发训练**：

1. 提交第一个训练任务
2. 立即提交第二个训练任务
3. 验证第二个任务返回 409 错误

### 4. 性能测试

#### 测试 1：LoRA 推理速度

**目标**：LoRA 推理速度不低于基座模型的 80%

**测试方法**：

```python
import time
from app.services.lora_inference_service import get_lora_inference_service
from app.services.transformers_service import get_transformers_service

# 测试基座模型
transformers_service = get_transformers_service()
messages = [{"role": "user", "content": "你好"}]

start = time.time()
base_result = await transformers_service.chat("Qwen3-8B", messages)
base_time = time.time() - start

# 测试 LoRA 模型
lora_service = get_lora_inference_service()

start = time.time()
lora_result = await lora_service.generate(1, messages)
lora_time = time.time() - start

# 验证性能
ratio = lora_time / base_time
assert ratio <= 1.25, f"LoRA 推理速度比基座模型慢 {(ratio-1)*100:.1f}%"
print(f"✓ LoRA 推理速度达标（基座模型的 {100/ratio:.1f}%）")
```

#### 测试 2：WebSocket 推送延迟

**目标**：推送延迟 < 1 秒

**测试方法**：

```python
import asyncio
import time
from datetime import datetime

latencies = []

async def test_websocket_latency():
    # 连接 WebSocket
    ws = await websocket.connect('ws://localhost:8000/ws/training/test')
    
    # 记录消息接收时间
    async for message in ws:
        data = json.loads(message)
        if 'timestamp' in data:
            sent_time = datetime.fromisoformat(data['timestamp'])
            received_time = datetime.now()
            latency = (received_time - sent_time).total_seconds()
            latencies.append(latency)
    
    avg_latency = sum(latencies) / len(latencies)
    assert avg_latency < 1.0, f"平均延迟 {avg_latency:.2f}s 超过 1 秒"
    print(f"✓ WebSocket 延迟达标（平均 {avg_latency*1000:.0f}ms）")
```

#### 测试 3：模型加载时间

**目标**：LoRA 模型加载时间 < 5 秒

**测试方法**：

```python
import time
from app.services.lora_inference_service import get_lora_inference_service

lora_service = get_lora_inference_service()

start = time.time()
await lora_service.load_lora_model(1)
load_time = time.time() - start

assert load_time < 5.0, f"加载时间 {load_time:.2f}s 超过 5 秒"
print(f"✓ LoRA 加载时间达标（{load_time:.2f}s）")
```

#### 测试 4：缓存效果

**测试方法**：

```python
# 第一次加载（冷启动）
start = time.time()
await lora_service.generate(1, messages)
cold_time = time.time() - start

# 第二次加载（缓存命中）
start = time.time()
await lora_service.generate(1, messages)
warm_time = time.time() - start

# 验证缓存加速
speedup = cold_time / warm_time
assert speedup > 2.0, f"缓存加速不明显（仅 {speedup:.1f}x）"
print(f"✓ 缓存效果良好（加速 {speedup:.1f}x）")
```

### 5. 压力测试

#### 测试并发请求

```bash
# 使用 Apache Bench 测试
ab -n 100 -c 10 http://localhost:8000/api/lora/models
```

**验证点**：
- 所有请求成功
- 平均响应时间 < 100ms
- 无内存泄漏

#### 测试长时间运行

```bash
# 运行 24 小时稳定性测试
python Backend/tests/stress_test.py --duration 24h
```

**验证点**：
- 无崩溃
- 内存使用稳定
- 无资源泄漏

## 测试检查清单

### 功能测试

- [ ] 数据集验证（Alpaca 格式）
- [ ] 数据集验证（Conversation 格式）
- [ ] 数据集验证（无效格式）
- [ ] LoRA 模型列表
- [ ] LoRA 模型详情
- [ ] LoRA 模型删除
- [ ] 基座模型列表
- [ ] 训练任务提交
- [ ] 训练进度推送
- [ ] 训练取消
- [ ] 训练完成
- [ ] 训练错误处理
- [ ] 助手创建（带 LoRA）
- [ ] 助手更新（修改 LoRA）
- [ ] 对话推理（使用 LoRA）
- [ ] LoRA 加载失败回退

### 性能测试

- [ ] LoRA 推理速度 ≥ 基座模型的 80%
- [ ] WebSocket 延迟 < 1 秒
- [ ] LoRA 加载时间 < 5 秒
- [ ] 缓存命中率 > 80%
- [ ] 并发请求处理

### 错误场景测试

- [ ] OOM 错误处理
- [ ] LoRA 不匹配检测
- [ ] 并发训练限制
- [ ] 数据集过大拒绝
- [ ] 无效参数验证
- [ ] 网络断开恢复

### 兼容性测试

- [ ] Chrome 浏览器
- [ ] Firefox 浏览器
- [ ] Edge 浏览器
- [ ] Safari 浏览器（如果可能）

## 自动化测试

### 运行所有测试

```bash
# 快速测试（跳过慢速测试）
pytest Backend/tests/ -v -m "not slow"

# 完整测试（包括慢速测试）
pytest Backend/tests/ -v

# 生成覆盖率报告
pytest Backend/tests/ --cov=app --cov-report=html
```

### CI/CD 集成

在 `.github/workflows/test.yml` 中添加：

```yaml
name: LoRA Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r Backend/requirements.txt
        pip install pytest pytest-asyncio pytest-cov
    
    - name: Run tests
      run: |
        pytest Backend/tests/ -v -m "not slow" --cov=app
```

## 故障排除

### 问题：测试失败 - 数据库连接错误

**解决方案**：
```bash
# 确保 MySQL 服务运行
sudo systemctl start mysql

# 检查数据库配置
cat Backend/.env
```

### 问题：测试失败 - CUDA out of memory

**解决方案**：
```bash
# 使用 QLoRA 模式
# 或减少 batch_size
# 或使用更小的模型
```

### 问题：WebSocket 连接失败

**解决方案**：
```bash
# 检查防火墙设置
sudo ufw allow 8000

# 检查 WebSocket 配置
# 确保 Nginx 没有缓冲 WebSocket
```

## 测试报告模板

### 测试执行报告

**日期**：2024-01-15  
**测试人员**：[姓名]  
**环境**：开发环境

#### 测试结果摘要

| 测试类型 | 总数 | 通过 | 失败 | 跳过 |
|---------|------|------|------|------|
| 单元测试 | 25 | 25 | 0 | 0 |
| 集成测试 | 15 | 15 | 0 | 0 |
| 端到端测试 | 5 | 5 | 0 | 0 |
| 性能测试 | 4 | 4 | 0 | 0 |

#### 性能指标

| 指标 | 目标 | 实际 | 状态 |
|------|------|------|------|
| LoRA 推理速度 | ≥80% | 85% | ✓ |
| WebSocket 延迟 | <1s | 0.3s | ✓ |
| LoRA 加载时间 | <5s | 3.2s | ✓ |
| 缓存命中率 | >80% | 92% | ✓ |

#### 发现的问题

1. **问题描述**：[描述]
   - **严重程度**：高/中/低
   - **状态**：已修复/进行中/待处理
   - **解决方案**：[描述]

#### 建议

1. [建议 1]
2. [建议 2]

## 参考资料

- [LoRA API 文档](./LORA_API.md)
- [数据库迁移指南](../scripts/README_LORA_MIGRATION.md)
- [PyTest 文档](https://docs.pytest.org/)
- [FastAPI 测试指南](https://fastapi.tiangolo.com/tutorial/testing/)
