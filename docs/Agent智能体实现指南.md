# Agent 智能体功能实现指南

## 📖 目录
1. [什么是 Agent](#什么是-agent)
2. [核心概念](#核心概念)
3. [项目实现](#项目实现)
4. [使用说明](#使用说明)
5. [扩展开发](#扩展开发)

---

## 什么是 Agent

**Agent（智能体）** 是一种能够自主感知环境、制定计划、执行行动并达成目标的 AI 系统。

### Agent vs 传统 LLM 对话

| 特性 | 传统 LLM | Agent |
|------|---------|-------|
| 交互模式 | 问答式 | 目标导向 |
| 能力范围 | 文本生成 | 调用工具、执行操作 |
| 决策能力 | 被动响应 | 主动规划 |
| 问题解决 | 单轮回答 | 多步骤迭代 |

### Agent 的核心特性

1. **自主性（Autonomy）**
   - 能够独立决策和行动
   - 不需要每一步都获得人类指令

2. **目标导向（Goal-Directed）**
   - 围绕用户目标工作
   - 自动分解复杂任务

3. **工具使用（Tool Use）**
   - 调用外部 API 和工具
   - 整合多个信息源

4. **反应性（Reactive）**
   - 感知环境变化
   - 根据反馈调整策略

5. **记忆能力（Memory）**
   - 保持对话上下文
   - 学习历史经验

---

## 核心概念

### ReAct 框架

本项目的 Agent 基于 **ReAct (Reasoning + Acting)** 框架实现：

```
用户输入 → [循环开始]
            ↓
          Thought (思考): Agent 分析当前状态
            ↓
          Action (行动): 决定使用什么工具
            ↓
          Observation (观察): 获取工具执行结果
            ↓
         [判断是否完成]
            ↓
         Final Answer (最终答案)
```

### 工作流程示例

**用户问题**: "帮我搜索知识库中关于 RAG 的内容并计算相关文档数量"

```
1. Thought: 我需要先搜索知识库找到 RAG 相关内容
   Action: search_knowledge_base
   Action Input: {"query": "RAG", "top_k": 5}
   Observation: 找到 5 个相关文档...

2. Thought: 现在我需要计算文档数量
   Action: calculator
   Action Input: {"expression": "5"}
   Observation: 计算结果: 5

3. Thought: 我现在知道最终答案了
   Final Answer: 在知识库中找到 5 个关于 RAG 的相关文档...
```

---

## 项目实现

### 目录结构

```
MyRAG/
├── Backend/
│   └── app/
│       ├── api/
│       │   └── agent.py           # Agent API 接口
│       └── services/
│           └── agent_service.py   # Agent 核心服务
└── Frontend/
    ├── agent-demo.html            # Agent 交互界面
    └── js/
        └── agent.js               # Agent 前端逻辑
```

### 核心组件

#### 1. AgentService (Backend)

**位置**: `Backend/app/services/agent_service.py`

**主要类和方法**:

```python
class Tool:
    """工具基类"""
    - name: 工具名称
    - description: 工具描述
    - func: 执行函数
    - run(): 执行工具

class AgentService:
    """Agent 核心服务"""
    - __init__(llm_service, knowledge_base_service, max_iterations)
    - register_tool(): 注册新工具
    - run(): 运行 Agent
    - _build_prompt(): 构建提示词
    - _parse_action(): 解析 Action
    - _parse_final_answer(): 解析最终答案
```

**默认工具**:

1. **search_knowledge_base** - 搜索知识库
   - 参数: `query`, `kb_id`(可选), `top_k`(可选)
   - 返回: 格式化的搜索结果

2. **calculator** - 数学计算
   - 参数: `expression`
   - 返回: 计算结果

3. **get_current_time** - 获取当前时间
   - 参数: 无
   - 返回: 当前日期时间

#### 2. Agent API (Backend)

**位置**: `Backend/app/api/agent.py`

**主要端点**:

- `POST /api/agent/query` - Agent 问答
  ```json
  请求:
  {
    "query": "用户问题",
    "session_id": "会话ID(可选)",
    "max_iterations": 5
  }
  
  响应:
  {
    "answer": "最终答案",
    "steps": [...执行步骤],
    "success": true,
    "iterations": 3
  }
  ```

- `GET /api/agent/tools` - 获取工具列表
  ```json
  响应:
  [
    {
      "name": "search_knowledge_base",
      "description": "搜索知识库..."
    }
  ]
  ```

- `GET /api/agent/health` - 健康检查

#### 3. Agent 前端 (Frontend)

**位置**: `Frontend/agent-demo.html` + `Frontend/js/agent.js`

**主要功能**:

- 对话界面
- 执行步骤可视化
- 工具列表展示
- 示例问题快速测试

---

## 使用说明

### 1. 启动后端服务

确保后端服务已启动：

```bash
cd Backend
python main.py
```

或使用项目启动脚本：
```bash
start.bat  # 或 start-fast.bat
```

### 2. 访问 Agent 界面

在浏览器中打开：
```
http://localhost:8000/static/agent-demo.html
```

### 3. 测试 Agent

#### 示例问题 1: 知识库搜索
```
问: 帮我搜索知识库中关于 RAG 的内容
```

Agent 会自动调用 `search_knowledge_base` 工具。

#### 示例问题 2: 数学计算
```
问: 计算 (123 + 456) * 789 的结果
```

Agent 会使用 `calculator` 工具执行计算。

#### 示例问题 3: 组合任务
```
问: 搜索知识库并总结 Agent 的工作原理
```

Agent 会:
1. 搜索知识库
2. 分析结果
3. 生成总结

### 4. API 调用示例

#### Python 示例

```python
import requests

url = "http://localhost:8000/api/agent/query"
data = {
    "query": "帮我搜索知识库中关于向量数据库的内容",
    "max_iterations": 5
}

response = requests.post(url, json=data)
result = response.json()

print(f"答案: {result['answer']}")
print(f"迭代次数: {result['iterations']}")
print(f"执行步骤: {len(result['steps'])}")
```

#### JavaScript 示例

```javascript
async function queryAgent(question) {
    const response = await fetch('http://localhost:8000/api/agent/query', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            query: question,
            max_iterations: 5
        })
    });
    
    const result = await response.json();
    console.log('答案:', result.answer);
    console.log('步骤:', result.steps);
}

queryAgent('现在几点了？');
```

---

## 扩展开发

### 添加自定义工具

#### 1. 创建工具函数

```python
# 在 agent_service.py 的 _register_default_tools() 方法中添加

def my_custom_tool(param1: str, param2: int = 10) -> str:
    """
    自定义工具说明
    
    Args:
        param1: 参数1说明
        param2: 参数2说明（可选）
    
    Returns:
        执行结果
    """
    try:
        # 工具的实现逻辑
        result = f"处理 {param1} with {param2}"
        return result
    except Exception as e:
        return f"执行失败: {str(e)}"

# 注册工具
self.register_tool(
    name="my_custom_tool",
    description="自定义工具的描述。参数: param1(必需)-说明, param2(可选)-说明",
    func=my_custom_tool
)
```

#### 2. 工具设计最佳实践

1. **清晰的描述**: 让 LLM 理解工具的用途
2. **类型提示**: 使用 Python 类型注解
3. **异常处理**: 捕获并返回友好的错误信息
4. **参数验证**: 验证输入参数的有效性
5. **返回格式**: 返回字符串格式的结果

#### 3. 高级工具示例

##### 网络搜索工具

```python
def web_search(query: str, num_results: int = 3) -> str:
    """使用搜索引擎搜索互联网"""
    try:
        # 使用 DuckDuckGo API 或其他搜索服务
        from duckduckgo_search import ddg
        
        results = ddg(query, max_results=num_results)
        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(f"{i}. {r['title']}\n   {r['body']}\n   {r['href']}")
        
        return "\n\n".join(formatted)
    except Exception as e:
        return f"搜索失败: {str(e)}"

self.register_tool(
    name="web_search",
    description="搜索互联网获取最新信息。参数: query(必需)-搜索关键词, num_results(可选)-结果数量",
    func=web_search
)
```

##### 文件操作工具

```python
def read_file(file_path: str) -> str:
    """读取文件内容"""
    try:
        # 添加安全检查
        if not file_path.startswith('/safe/directory/'):
            return "不允许访问此路径"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return content[:1000]  # 限制返回长度
    except Exception as e:
        return f"读取文件失败: {str(e)}"

self.register_tool(
    name="read_file",
    description="读取文件内容。参数: file_path(必需)-文件路径",
    func=read_file
)
```

##### 数据库查询工具

```python
def query_database(sql: str) -> str:
    """执行数据库查询（只读）"""
    try:
        # 安全检查: 只允许 SELECT
        if not sql.strip().upper().startswith('SELECT'):
            return "只允许 SELECT 查询"
        
        with db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                results = cursor.fetchall()
        
        # 格式化结果
        return str(results[:10])  # 限制返回数量
    except Exception as e:
        return f"查询失败: {str(e)}"

self.register_tool(
    name="query_database",
    description="执行数据库 SELECT 查询。参数: sql(必需)-SQL 查询语句",
    func=query_database
)
```

### 优化 Agent 性能

#### 1. 调整提示词

修改 `_build_prompt()` 方法中的提示词模板，使其更适合特定任务。

#### 2. 优化 LLM 参数

```python
response = await self.llm_service.generate(
    prompt=prompt,
    max_tokens=500,      # 增加最大 token 数
    temperature=0.1,     # 降低温度提高稳定性
    top_p=0.9           # 调整采样参数
)
```

#### 3. 增加最大迭代次数

```python
agent = AgentService(
    llm_service=llm_service,
    knowledge_base_service=kb_service,
    max_iterations=10  # 增加到 10 次
)
```

#### 4. 添加记忆功能

```python
class AgentService:
    def __init__(self, ...):
        self.conversation_history = []  # 对话历史
        self.memory_window = 5          # 保留最近 5 轮对话
    
    def run(self, user_query, session_id=None):
        # 在构建 prompt 时包含历史记录
        history_context = self._get_history_context(session_id)
        prompt = self._build_prompt(user_query, history_context)
        ...
```

### 实现多 Agent 协作

```python
class MultiAgentSystem:
    """多 Agent 协作系统"""
    
    def __init__(self):
        self.agents = {
            'researcher': AgentService(...),  # 研究型 Agent
            'writer': AgentService(...),      # 写作型 Agent
            'reviewer': AgentService(...)     # 审核型 Agent
        }
    
    async def collaborate(self, task: str):
        """协作完成任务"""
        # 1. 研究型 Agent 收集信息
        research = await self.agents['researcher'].run(
            f"研究以下主题: {task}"
        )
        
        # 2. 写作型 Agent 生成内容
        content = await self.agents['writer'].run(
            f"基于以下信息写作: {research['answer']}"
        )
        
        # 3. 审核型 Agent 检查质量
        review = await self.agents['reviewer'].run(
            f"审核以下内容: {content['answer']}"
        )
        
        return review['answer']
```

---

## 常见问题

### Q1: Agent 无法调用工具？

**原因**: LLM 输出格式不符合预期

**解决方案**:
1. 检查提示词是否清晰
2. 降低 temperature 参数
3. 使用更强大的 LLM 模型
4. 添加更多示例到提示词中

### Q2: Agent 陷入循环？

**原因**: 无法判断任务完成

**解决方案**:
1. 设置合理的 max_iterations
2. 优化工具描述
3. 在提示词中明确终止条件

### Q3: 工具执行失败？

**原因**: 参数解析错误或工具内部错误

**解决方案**:
1. 添加详细的日志记录
2. 改进错误处理
3. 验证工具函数的健壮性

### Q4: 响应速度慢？

**原因**: LLM 调用耗时或工具执行慢

**解决方案**:
1. 使用更快的 LLM 模型或服务
2. 优化工具实现
3. 添加缓存机制
4. 使用异步并发

---

## 进阶学习资源

1. **ReAct 论文**: [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

2. **LangChain Agents**: https://python.langchain.com/docs/modules/agents/

3. **OpenAI Function Calling**: https://platform.openai.com/docs/guides/function-calling

4. **AutoGPT**: https://github.com/Significant-Gravitas/AutoGPT

5. **BabyAGI**: https://github.com/yoheinakajima/babyagi

---

## 总结

本文档介绍了如何在 RAG 项目中实现一个简单但功能完整的 Agent 系统。通过 ReAct 框架，Agent 能够：

✅ 自主规划任务  
✅ 调用多种工具  
✅ 迭代优化策略  
✅ 生成综合答案  

你可以根据需求扩展工具、优化性能、实现多 Agent 协作等高级功能。

**开始使用**: 访问 http://localhost:8000/static/agent-demo.html 体验 Agent 功能！
