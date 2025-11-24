# Agent 快速开始指南

## 🚀 5 分钟快速上手

### 第 1 步: 确认环境

确保以下服务已启动：
- ✅ MySQL 数据库
- ✅ 后端服务 (FastAPI)
- ✅ LLM 服务 (Ollama 或其他)

### 第 2 步: 启动服务

使用项目启动脚本：

```bash
# Windows
start-fast.bat

# 或者手动启动后端
cd Backend
python main.py
```

等待看到日志输出：
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 第 3 步: 访问 Agent 界面

在浏览器中打开：
```
http://localhost:8000/static/agent-demo.html
```

### 第 4 步: 测试 Agent

#### 测试 1: 获取当前时间
```
输入: 现在几点了？
```

Agent 会自动调用 `get_current_time` 工具。

#### 测试 2: 数学计算
```
输入: 帮我计算 (123 + 456) * 789
```

Agent 会使用 `calculator` 工具执行计算。

#### 测试 3: 知识库搜索
```
输入: 搜索知识库中关于 RAG 的内容
```

Agent 会调用 `search_knowledge_base` 工具。

---

## 📋 API 使用示例

### Python 调用

```python
import requests

# Agent 查询
response = requests.post(
    'http://localhost:8000/api/agent/query',
    json={
        'query': '帮我搜索知识库',
        'max_iterations': 5
    }
)

result = response.json()
print(result['answer'])
```

### JavaScript 调用

```javascript
// Agent 查询
const response = await fetch('http://localhost:8000/api/agent/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        query: '现在几点了？',
        max_iterations: 5
    })
});

const result = await response.json();
console.log(result.answer);
```

### cURL 调用

```bash
curl -X POST http://localhost:8000/api/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "计算 2+3*4",
    "max_iterations": 5
  }'
```

---

## 🔧 添加自定义工具

### 步骤 1: 编辑 agent_service.py

找到 `Backend/app/services/agent_service.py`

### 步骤 2: 在 `_register_default_tools()` 中添加

```python
def my_tool(param: str) -> str:
    """工具描述"""
    try:
        # 实现逻辑
        result = f"处理 {param}"
        return result
    except Exception as e:
        return f"执行失败: {str(e)}"

self.register_tool(
    name="my_tool",
    description="工具描述。参数: param(必需)-参数说明",
    func=my_tool
)
```

### 步骤 3: 重启服务

```bash
# Ctrl+C 停止服务
# 然后重新启动
python Backend/main.py
```

---

## 📚 更多信息

详细文档请查看：
- `docs/Agent智能体实现指南.md` - 完整实现指南
- `test/test_agent.py` - 测试示例

---

## ❓ 常见问题

### Q: Agent 没有响应？

**检查**:
1. 后端服务是否正常运行
2. LLM 服务是否可用
3. 浏览器控制台是否有错误

### Q: 工具调用失败？

**检查**:
1. 工具函数是否正确注册
2. 参数格式是否正确
3. 查看后端日志获取详细错误

### Q: 如何调试？

启用详细日志：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 🎉 下一步

- ✨ 添加更多自定义工具
- 🔗 集成外部 API
- 🤖 实现多 Agent 协作
- 💾 添加记忆和历史功能

Happy Coding! 🚀
