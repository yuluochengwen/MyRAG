# 🤖 Agent 智能体功能

## 简介

Agent（智能体）是一种能够**自主规划任务、调用工具、整合信息**的高级 AI 系统。本项目实现了基于 **ReAct (Reasoning + Acting)** 框架的简单 Agent 系统。

### 与普通聊天的区别

| 功能 | 普通聊天 | Agent 智能体 |
|------|---------|------------|
| 交互方式 | 一问一答 | 目标导向，多步骤执行 |
| 能力范围 | 文本生成 | 可调用工具、执行操作 |
| 任务处理 | 单轮回答 | 自动分解、迭代完成 |
| 信息来源 | 仅模型知识 | 可搜索知识库、调用 API |

---

## 🎯 核心功能

### 1. 自主任务规划
Agent 会自动将复杂任务分解为可执行步骤

### 2. 工具调用能力
内置工具：
- ✅ **知识库搜索** - 搜索项目知识库获取信息
- ✅ **数学计算** - 执行数学表达式计算
- ✅ **时间查询** - 获取当前日期时间
- 🔧 **可扩展** - 支持添加自定义工具

### 3. 迭代优化
根据工具返回结果不断调整策略，直到完成目标

### 4. 过程可视化
实时展示 Agent 的思考过程和执行步骤

---

## 📁 文件结构

```
MyRAG/
├── Backend/
│   └── app/
│       ├── api/
│       │   └── agent.py              # Agent API 接口
│       └── services/
│           └── agent_service.py      # Agent 核心服务
├── Frontend/
│   ├── agent-demo.html               # Agent 演示界面
│   └── js/
│       └── agent.js                  # Agent 前端逻辑
├── docs/
│   ├── Agent智能体实现指南.md         # 详细实现文档
│   └── Agent快速开始.md               # 快速开始指南
└── test/
    └── test_agent.py                 # Agent 测试脚本
```

---

## 🚀 快速开始

### 1. 启动服务

```bash
# Windows
start-fast.bat

# 或手动启动
cd Backend
python main.py
```

### 2. 访问界面

打开浏览器访问：
```
http://localhost:8000/static/agent-demo.html
```

### 3. 测试 Agent

#### 示例 1: 获取时间
```
输入: 现在几点了？
```
Agent 自动调用时间工具

#### 示例 2: 数学计算
```
输入: 帮我计算 (123 + 456) * 789
```
Agent 使用计算器工具

#### 示例 3: 知识库搜索
```
输入: 搜索知识库中关于 RAG 的内容
```
Agent 调用知识库搜索工具

#### 示例 4: 组合任务
```
输入: 搜索知识库并总结 Agent 的工作原理
```
Agent 会：
1. 搜索知识库
2. 分析结果
3. 生成总结

---

## 🔌 API 使用

### Python 示例

```python
import requests

response = requests.post(
    'http://localhost:8000/api/agent/query',
    json={'query': '现在几点了？', 'max_iterations': 5}
)

result = response.json()
print(f"答案: {result['answer']}")
print(f"步骤: {len(result['steps'])}")
```

### JavaScript 示例

```javascript
const response = await fetch('http://localhost:8000/api/agent/query', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        query: '帮我计算 10 + 20',
        max_iterations: 5
    })
});

const result = await response.json();
console.log(result.answer);
```

### cURL 示例

```bash
curl -X POST http://localhost:8000/api/agent/query \
  -H "Content-Type: application/json" \
  -d '{"query": "搜索知识库", "max_iterations": 5}'
```

---

## 🔧 添加自定义工具

### 步骤 1: 编辑服务文件

打开 `Backend/app/services/agent_service.py`

### 步骤 2: 添加工具函数

在 `_register_default_tools()` 方法中添加：

```python
def my_custom_tool(param1: str, param2: int = 10) -> str:
    """工具功能描述"""
    try:
        # 实现你的逻辑
        result = f"处理 {param1} with {param2}"
        return result
    except Exception as e:
        return f"执行失败: {str(e)}"

# 注册工具
self.register_tool(
    name="my_custom_tool",
    description="工具描述。参数: param1(必需)-说明, param2(可选)-说明",
    func=my_custom_tool
)
```

### 步骤 3: 重启服务

```bash
# Ctrl+C 停止
python Backend/main.py  # 重新启动
```

---

## 🎨 工作原理

### ReAct 框架流程

```
用户输入: "搜索知识库并总结 RAG"
    ↓
[循环开始]
    ↓
Thought (思考): 我需要先搜索知识库
    ↓
Action (行动): search_knowledge_base
    ↓
Action Input: {"query": "RAG", "top_k": 3}
    ↓
Observation (观察): [找到 3 个文档...]
    ↓
Thought (思考): 现在我可以总结了
    ↓
Final Answer (最终答案): 根据搜索结果，RAG是...
```

### 核心组件

1. **AgentService** - Agent 核心逻辑
2. **Tool** - 工具基类
3. **Prompt Builder** - 提示词构建
4. **Action Parser** - 解析 LLM 输出

---

## 📚 文档

- **完整指南**: [Agent智能体实现指南.md](./docs/Agent智能体实现指南.md)
  - 详细的概念解释
  - 完整的代码实现
  - 扩展开发指南
  
- **快速开始**: [Agent快速开始.md](./docs/Agent快速开始.md)
  - 5 分钟快速上手
  - 常见问题解答
  
- **测试脚本**: [test_agent.py](./test/test_agent.py)
  - 单元测试示例
  - 工具测试代码

---

## 🔍 API 端点

### POST /api/agent/query
Agent 问答接口

**请求体**:
```json
{
  "query": "用户问题",
  "session_id": "会话ID(可选)",
  "max_iterations": 5
}
```

**响应**:
```json
{
  "answer": "最终答案",
  "steps": [
    {"type": "thought", "content": "思考内容"},
    {"type": "action", "tool": "工具名", "input": "参数"},
    {"type": "observation", "content": "观察结果"}
  ],
  "success": true,
  "iterations": 3
}
```

### GET /api/agent/tools
获取可用工具列表

**响应**:
```json
[
  {
    "name": "search_knowledge_base",
    "description": "搜索知识库..."
  },
  {
    "name": "calculator",
    "description": "执行数学计算..."
  }
]
```

### GET /api/agent/health
健康检查

---

## ❓ 常见问题

### Q: Agent 不响应？
**检查**:
1. 后端服务是否运行
2. Ollama 服务是否启动
3. 浏览器控制台错误

### Q: 工具调用失败？
**检查**:
1. 工具是否正确注册
2. 参数格式是否正确
3. 查看后端日志

### Q: 如何调试？
在 `Backend/main.py` 启用详细日志：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Q: 支持哪些 LLM？
目前支持：
- ✅ Ollama (本地部署)
- 🔄 可扩展支持 OpenAI、Azure 等

---

## 🎓 进阶学习

### 推荐资源

1. **ReAct 论文**: [arxiv.org/abs/2210.03629](https://arxiv.org/abs/2210.03629)
2. **LangChain Agents**: [python.langchain.com](https://python.langchain.com/docs/modules/agents/)
3. **OpenAI Function Calling**: [platform.openai.com/docs](https://platform.openai.com/docs/guides/function-calling)

### 扩展方向

- 🔗 添加更多工具（网络搜索、文件操作、API 调用等）
- 💾 实现记忆和历史功能
- 🤖 多 Agent 协作
- 🎯 领域特定 Agent（代码助手、数据分析师等）
- 📊 性能优化和缓存机制

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📄 许可

本项目遵循项目主许可协议。

---

## 🎉 开始使用

现在就访问 http://localhost:8000/static/agent-demo.html 体验 Agent 功能吧！

有问题？查看 [完整文档](./docs/Agent智能体实现指南.md) 📖
