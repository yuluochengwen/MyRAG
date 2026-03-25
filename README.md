# MyRAG - 智能RAG知识库管理系统

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

基于 **FastAPI + MySQL + ChromaDB + Neo4j** 的企业级 RAG (Retrieval-Augmented Generation) 知识库管理系统，集成知识图谱、Agent智能体等高级功能。

## ✨ 核心特性

### 🎯 RAG核心功能
- ✅ **知识库管理** - 完整的CRUD操作，支持多知识库
- ✅ **文档处理** - 支持TXT/PDF/DOCX/HTML/MD/JSON多格式
- ✅ **智能分割** - 递归分割 + 语义分割（LLM驱动）
- ✅ **向量检索** - ChromaDB持久化存储，高效相似度搜索
- ✅ **混合检索** - 向量检索 + 知识图谱结合（可配置权重）

### 🤖 智能助手
- ✅ **多LLM支持** - Transformers本地模型 + Ollama（本地/云端）
- ✅ **流式对话** - 实时Markdown渲染，支持打字机效果
- ✅ **上下文记忆** - 完整对话历史管理
- ✅ **RAG增强** - 自动检索相关知识，生成高质量回答

### 🕸️ 知识图谱
- ✅ **自动构建** - 基于Neo4j的知识图谱自动提取
- ✅ **实体识别** - 支持Person/Organization/Location/Product等7类实体
- ✅ **关系推理** - 图遍历推理，发现隐含关联
- ✅ **可视化查询** - 支持图谱统计和实体搜索

### 🎭 Agent智能体
- ✅ **工具调用** - 内置calculator/current_time等工具
- ✅ **任务规划** - 自动分解复杂任务
- ✅ **记忆管理** - 对话历史持久化
- ✅ **流式响应** - 实时展示推理过程

###  工程化
- ✅ **Docker部署** - 一键启动所有服务（MySQL/Ollama/Neo4j/Nginx）
- ✅ **模型预装** - 自动下载Ollama和HuggingFace模型
- ✅ **WebSocket** - 实时进度推送，支持多客户端
- ✅ **健康监控** - 完整的健康检查和日志系统

## 🏗️ 项目结构

```plaintext
MyRAG/
├── Backend/                         # 后端服务
│   ├── main.py                     # FastAPI 应用入口
│   ├── config.yaml                 # 唯一 YAML 配置文件
│   ├── requirements.txt            # Python 依赖
│   └── app/
│       ├── api/                    # API 路由层
│       │   ├── knowledge_base.py   # 知识库管理
│       │   ├── assistant.py        # 智能助手
│       │   ├── conversation.py     # 对话管理
│       │   ├── models.py           # 模型管理
│       │   ├── agent.py            # Agent 智能体
│       │   ├── lora.py             # LoRA 微调
│       │   └── websocket.py        # WebSocket
│       ├── services/               # 业务逻辑层 (18+ 服务)
│       ├── models/                 # Pydantic 数据模型 (含 LoRA schemas)
│       ├── core/                   # 核心模块 (配置/数据库/依赖注入)
│       ├── utils/                  # 工具函数 (日志/解析/分割/验证)
│       └── websocket/              # WebSocket 管理器
│
├── Frontend/                        # 前端界面 (纯 HTML/CSS/JS)
│   ├── knowledge-base.html         # 知识库管理
│   ├── intelligent-assistant.html  # 智能助手管理
│   ├── chat.html                   # 对话界面
│   ├── agent.html                  # Agent 交互
│   ├── model-management.html       # 模型管理
│   ├── lora-training.html          # LoRA 训练
│   ├── css/                        # 样式文件
│   └── js/                         # 前端逻辑
│
├── docs/                            # 📁 统一文档中心
│   ├── agent/                      # Agent 模块文档
│   ├── lora/                       # LoRA 微调文档
│   └── 流程图/                      # 架构流程图
│
├── test/                            # 📁 统一测试套件
│
├── scripts/                         # 📁 统一脚本中心
│   ├── db/                         # 数据库脚本 (init.sql, 迁移)
│   └── ops/                        # 运维脚本 (测试/模型预加载)
│
├── data/                            # 运行时数据 (gitignored)
│   ├── knowledge_base/             # 知识库上传文件
│   ├── vector_db/                  # ChromaDB 向量数据库
│   ├── logs/                       # 应用日志
│   └── training_data/              # 训练数据
│
├── Models/                          # 模型文件
│   ├── Embedding/                  # 嵌入模型
│   └── LLM/                        # 大语言模型
│
├── deploy/                          # 部署配置
│   ├── Dockerfile                  # Docker 镜像构建
│   ├── nginx.conf                  # Nginx 反向代理
│   ├── docker-start.bat            # Docker 管理脚本
│   └── docker-daemon-config.json   # Docker 守护进程配置
│
├── docker-compose.yml              # Docker 编排 (5 服务)
├── start.bat                       # 本地启动脚本 (支持 fast 模式)
├── .env.example                    # 环境变量模板
└── README.md                       # 本文档
```

## 功能特性

### 已实现功能

- ✅ 知识库 CRUD 操作
- ✅ 文件上传（支持 TXT, PDF, DOCX, HTML, MD）
- ✅ 文件解析和文本提取
- ✅ 文本智能分块（Recursive Text Splitter）
- ✅ 文本向量化
  - Sentence Transformers（本地模型）
  - Ollama Embeddings（本地/云端）
- ✅ 向量存储和检索（ChromaDB）
- ✅ 智能助手管理
  - Transformers 本地模型
  - Ollama 本地/云端模型
- ✅ 智能对话（RAG + 上下文记忆）
- ✅ 流式响应（实时Markdown渲染）
- ✅ WebSocket 实时进度推送
- ✅ MySQL 数据持久化
- ✅ Docker 容器化部署
- ✅ Nginx 反向代理

### 待实现功能

- ⏳ Agent 工作流
- ⏳ 高级搜索和过滤
- ⏳ 批量文件上传
- ⏳ 文件去重检测
- ⏳ 更多LLM提供商支持（OpenAI, Azure）

## 💻 技术栈

### 后端框架

| 技术 | 版本 | 用途 |
|------|------|------|
| **FastAPI** | 0.104.1 | Web框架，高性能异步API |
| **Python** | 3.11+ | 编程语言 |
| **Uvicorn** | 0.24.0 | ASGI服务器 |
| **Pydantic** | 2.5.0 | 数据验证和配置管理 |

### 数据存储

| 技术 | 版本 | 用途 |
|------|------|------|
| **MySQL** | 8.0 | 关系型数据库（知识库元数据、对话历史） |
| **ChromaDB** | 1.3.5+ | 向量数据库（嵌入向量存储和检索） |
| **Neo4j** | 5.15 | 图数据库（知识图谱存储） |

### AI/ML框架

| 技术 | 版本 | 用途 |
|------|------|------|
| **Transformers** | 4.40.0+ | HuggingFace模型加载和推理 |
| **Sentence-Transformers** | 2.7.0+ | 文本嵌入模型 |
| **Ollama** | Latest | 本地/云端LLM服务 |
| **LangChain** | 0.1.16 | LLM应用开发框架 |
| **BitsAndBytes** | 0.48.0+ | 模型量化（INT4/INT8） |

### 文档处理

| 技术 | 版本 | 用途 |
|------|------|------|
| **PyPDF2** | 3.0.1 | PDF解析 |
| **python-docx** | 1.1.2 | Word文档解析 |
| **BeautifulSoup4** | 4.12.2 | HTML解析 |
| **Markdown** | 3.5.1 | Markdown解析 |

### 前端技术

| 技术 | 用途 |
|------|------|
| **原生HTML/CSS/JS** | 轻量级前端，无需构建 |
| **Tailwind CSS** | 实用优先的CSS框架 |
| **Font Awesome** | 图标库 |
| **Marked.js** | Markdown渲染 |
| **Highlight.js** | 代码高亮 |

### 部署运维

| 技术 | 版本 | 用途 |
|------|------|------|
| **Docker** | Latest | 容器化 |
| **docker-compose** | 3.8 | 多容器编排 |
| **Nginx** | Alpine | 反向代理和静态文件服务 |

## 快速开始

### 方法一：Docker 部署（推荐）⭐

#### Windows 一键启动

1. **启动所有服务**

双击运行 `deploy/docker-start.bat`，或在命令行中执行：

```bash
.\deploy\docker-start.bat
```

选择 `1. Start all services` 启动所有服务。

2. **预装模型（首次部署必须！）**

服务启动后，再次运行 `deploy/docker-start.bat`，选择 `6. Preload models (Ollama + HuggingFace)`。

这将自动下载：
- **qwen2.5:1.5b** - 轻量级LLM模型（~1GB）
- **nomic-embed-text** - Ollama嵌入模型（~274MB）
- **paraphrase-multilingual-MiniLM-L12-v2** - HuggingFace嵌入模型（~471MB）

下载时间约10-30分钟，取决于网速。

3. **访问应用**

- 前端界面: <http://localhost>
- API文档: <http://localhost:8000/docs>
- 健康检查: <http://localhost:8000/health>
- Neo4j浏览器: <http://localhost:7474>
- Ollama API: <http://localhost:11434>

#### Linux/Mac 部署

1. **启动所有服务**

```bash
docker-compose up -d
```

2. **预装模型**

```bash
# Ollama模型
docker exec myrag-ollama ollama pull qwen2.5:1.5b
docker exec myrag-ollama ollama pull nomic-embed-text

# HuggingFace模型
docker exec myrag-backend python /app/../scripts/preload-huggingface-models.py
```

3. **查看服务状态**

```bash
docker-compose ps
```

4. **查看日志**

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务
docker-compose logs -f backend
```

**📖 完整部署指南**: [Docker快速部署指南.md](docs/Docker快速部署指南.md)

### 方法二：本地开发

#### 1. 环境准备

确保安装以下依赖:
- Python 3.11+
- MySQL 8.0+
- Conda (可选,推荐)

#### 2. 配置环境变量

```bash
cd Backend
cp .env.example .env
```

编辑 `.env` 文件,设置数据库密码:

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password_here  # 修改为你的MySQL密码
MYSQL_DATABASE=myrag
```

#### 3. 安装 Python 依赖

使用 Conda (推荐):
```bash
conda create -n MyRAG python=3.11
conda activate MyRAG
pip install -r requirements.txt
```

或使用 pip:
```bash
pip install -r requirements.txt
```

#### 4. 初始化数据库

**一键初始化(推荐)**:
```bash
python scripts/init_db.py
```

此脚本会自动:
- 创建 `myrag` 数据库
- 创建所有必需的表(knowledge_bases, files, text_chunks, process_logs, assistants)

**手动初始化**:
```bash
mysql -u root -p < scripts/init.sql
```

#### 5. 启动服务

**Windows (推荐使用启动脚本)**:
```bash
# 项目根目录执行
.\start.bat
```

**手动启动**:
```bash
cd Backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 6. 访问应用

- 知识库管理: http://localhost:8000/knowledge-base.html
- 智能助手: http://localhost:8000/intelligent-assistant.html
- API文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

## API 文档

## 📖 API文档

### 核心API接口

#### 1️⃣ 知识库管理 (`/api/knowledge-bases`)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/knowledge-bases` | 创建知识库 |
| GET | `/api/knowledge-bases` | 获取知识库列表 |
| GET | `/api/knowledge-bases/{kb_id}` | 获取知识库详情 |
| PUT | `/api/knowledge-bases/{kb_id}` | 更新知识库 |
| DELETE | `/api/knowledge-bases/{kb_id}` | 删除知识库 |
| POST | `/api/knowledge-bases/{kb_id}/upload` | 上传文件到知识库 |
| GET | `/api/knowledge-bases/{kb_id}/files` | 获取知识库文件列表 |
| DELETE | `/api/files/{file_id}` | 删除文件 |
| POST | `/api/knowledge-bases/{kb_id}/rebuild-vector` | 重建向量索引 |
| POST | `/api/knowledge-bases/{kb_id}/build-graph` | 构建知识图谱 |

#### 2️⃣ 智能助手 (`/api/assistants`)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/assistants` | 创建助手 |
| GET | `/api/assistants` | 获取助手列表 |
| GET | `/api/assistants/{assistant_id}` | 获取助手详情 |
| PUT | `/api/assistants/{assistant_id}` | 更新助手 |
| DELETE | `/api/assistants/{assistant_id}` | 删除助手 |

#### 3️⃣ 对话管理 (`/api/conversations`)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/conversations` | 创建对话 |
| GET | `/api/conversations/assistant/{assistant_id}` | 获取助手的对话列表 |
| GET | `/api/conversations/{conversation_id}/messages` | 获取对话消息 |
| POST | `/api/conversations/{conversation_id}/chat` | 发送消息（流式响应） |
| DELETE | `/api/conversations/{conversation_id}` | 删除对话 |

#### 4️⃣ 模型管理 (`/api/models`)

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/models/embedding` | 获取可用嵌入模型 |
| GET | `/api/models/llm` | 获取可用LLM模型 |
| GET | `/api/models/ollama/list` | 获取Ollama模型列表 |
| POST | `/api/models/ollama/pull` | 拉取Ollama模型 |

#### 5️⃣ Agent智能体 (`/api/agent`)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/agent/chat` | Agent对话（流式） |
| GET | `/api/agent/tools` | 获取可用工具列表 |
| GET | `/api/agent/history/{session_id}` | 获取对话历史 |

#### 6️⃣ WebSocket (`/ws`)

| 端点 | 说明 |
|------|------|
| `WS /ws/{client_id}` | WebSocket连接（实时进度推送） |

### 完整API文档

启动服务后访问: <http://localhost:8000/docs> (Swagger UI)

或访问: <http://localhost:8000/redoc> (ReDoc)

## ⚙️ 配置说明

### config.yaml 核心配置

```yaml
# 应用配置
app:
  name: "MyRAG"
  version: "1.0.0"
  port: 8000

# 文件配置
file:
  max_size_mb: 100              # 单文件最大100MB
  allowed_extensions: [".txt", ".pdf", ".docx", ".html", ".md", ".json"]

# 文本处理
text_processing:
  chunk_size: 800               # 分块大小
  chunk_overlap: 100            # 重叠大小
  semantic_split:
    enabled: true               # 启用语义分割
    ollama_model: "deepseek-v3.1:671b-cloud"

# 嵌入模型
embedding:
  provider: "transformers"      # transformers | ollama
  default_model: "BERT-Base"
  ollama:
    base_url: "http://localhost:11434"
    default_model: "nomic-embed-text"

# LLM配置
llm:
  default_provider: "transformers"  # transformers | ollama
  default_model: "Qwen2.5-3B-Instruct"
  transformers_quantization: "int4"  # int4 | int8 | fp16
  temperature: 0.5
  max_tokens: 256

# Neo4j知识图谱
neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "myrag123"

# 知识图谱配置
knowledge_graph:
  enabled: true
  entity_extraction:
    provider: "ollama"
    ollama_model: "deepseek-v3.1:671b-cloud"
  entity_types: [Person, Organization, Location, Product, Concept, Event, Date]

# 混合检索
hybrid_retrieval:
  vector_weight: 0.6            # 向量检索权重
  graph_weight: 0.4             # 图谱检索权重
```

### 环境变量 (.env)

```env
# 数据库配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=myrag

# Ollama配置（可选）
OLLAMA_BASE_URL=http://localhost:11434

# Neo4j配置（可选）
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=myrag123
```

## 🛠️ 开发指南

### 添加新的API路由

```python
# 1. 在 app/api/ 创建新路由文件
from fastapi import APIRouter, Depends
from app.models.schemas import YourModel
from app.services.your_service import YourService

router = APIRouter(prefix="/api/your-module", tags=["Your Module"])

@router.post("/")
async def create_item(data: YourModel, service: YourService = Depends()):
    return await service.create(data)

# 2. 在 main.py 中注册路由
from app.api.your_module import router as your_router
app.include_router(your_router)
```

### 添加新的服务层

```python
# app/services/your_service.py
from app.core.database import db_manager

class YourService:
    async def create(self, data):
        with db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO ...", data)
                conn.commit()
                return cursor.lastrowid
```

### 添加新的文件解析器

```python
# app/utils/file_parser.py
class YourParser(BaseParser):
    """自定义文件解析器"""
    
    def parse(self, file_path: str) -> str:
        # 实现解析逻辑
        with open(file_path, 'r') as f:
            return f.read()

# 注册解析器
PARSER_MAP = {
    '.txt': TextParser(),
    '.your_ext': YourParser(),  # 添加新类型
}
```

### 添加Agent工具

```python
# app/services/agent_service.py
def your_custom_tool(param: str) -> str:
    """
    工具描述：这里描述工具的功能
    参数说明：param - 参数说明
    """
    # 实现工具逻辑
    return f"Result: {param}"

# 注册工具
TOOLS = {
    "your_tool": your_custom_tool,
    # ... 其他工具
}
```

### WebSocket消息推送

```python
from app.websocket.manager import manager

# 发送进度消息
await manager.send_message(
    client_id="your_client_id",
    message={
        "type": "progress",
        "stage": "processing",
        "progress": 50,
        "message": "处理中..."
    }
)
```

## 📚 项目文档

完整文档位于 `docs/` 目录：

| 文档 | 说明 |
|------|------|
| [MyRAG概要设计.md](docs/MyRAG概要设计.md) | 系统架构设计（2900+行） |
| [Docker快速部署指南.md](docs/Docker快速部署指南.md) | Docker部署完整教程 |
| [Agent功能说明.md](docs/Agent功能说明.md) | Agent智能体使用指南 |
| [知识图谱自动构建功能.md](docs/知识图谱自动构建功能.md) | Neo4j知识图谱构建 |
| [文本分割功能改进实施指南.md](docs/文本分割功能改进实施指南.md) | 文本分割优化 |
| [Backend服务层重构方案.md](docs/Backend服务层重构方案.md) | 架构重构说明 |

## 🎯 使用场景

### 企业知识库

- 内部文档管理和智能问答
- 技术文档检索和学习
- 客服知识库自动回答

### 教育培训

- 课程资料智能检索
- 作业批改辅助
- 学习路径推荐

### 研究分析

- 论文文献管理和检索
- 研究资料整理和分析
- 知识图谱构建和挖掘

### 个人助手

- 个人笔记管理
- 知识积累和检索
- 学习计划制定

## 🚧 路线图

### v1.1 (计划中)

- [ ] 支持更多LLM提供商（OpenAI、Azure、Claude）
- [ ] 批量文件上传和处理
- [ ] 文件去重检测
- [ ] 向量数据库迁移工具
- [ ] 完善的权限管理系统

### v1.2 (规划中)

- [ ] 多租户支持
- [ ] 分布式部署方案
- [ ] 高级检索策略（混合检索优化）
- [ ] 模型性能监控和分析
- [ ] API速率限制和配额管理

### v2.0 (远期规划)

- [ ] 前端重构（React/Vue）
- [ ] 插件系统
- [ ] 工作流编排器
- [ ] 移动端支持
- [ ] 多语言国际化

## ❓ 故障排除

### 数据库连接失败

**问题**: `pymysql.err.OperationalError: (2003, "Can't connect to MySQL server")`

**解决方案**:

1. 检查MySQL服务是否运行

   ```bash
   # Windows
   net start MySQL80
   
   # Linux
   systemctl status mysql
   ```

2. 验证`.env`配置是否正确
3. 检查防火墙设置

### 模型下载慢或失败

**问题**: HuggingFace模型下载缓慢

**解决方案**:

```bash
# 设置HuggingFace镜像
export HF_ENDPOINT=https://hf-mirror.com

# Windows PowerShell
$env:HF_ENDPOINT="https://hf-mirror.com"
```

**问题**: Ollama模型拉取失败

**解决方案**:

```bash
# 检查Ollama服务状态
curl http://localhost:11434/api/tags

# 重启Ollama服务
docker restart myrag-ollama  # Docker部署
# 或
ollama serve  # 本地部署
```

### WebSocket连接失败

**问题**: 前端WebSocket连接超时

**解决方案**:

1. 检查Nginx配置是否支持WebSocket

   ```nginx
   location /ws/ {
       proxy_pass http://backend:8000;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
   }
   ```

2. 检查防火墙是否允许WebSocket连接
3. 验证Backend服务是否正常运行

### 向量检索结果为空

**问题**: 查询返回空结果

**解决方案**:

1. 确认文件已成功上传并处理

   ```bash
   # 检查向量数据库
   ls VectorDB/
   ```

2. 重建向量索引

   ```bash
   POST /api/knowledge-bases/{kb_id}/rebuild-vector
   ```

3. 检查嵌入模型是否一致

### Neo4j连接失败

**问题**: `ServiceUnavailable: Unable to retrieve routing information`

**解决方案**:

1. 检查Neo4j服务状态

   ```bash
   docker logs myrag-neo4j  # Docker部署
   ```

2. 验证连接配置

   ```yaml
   neo4j:
     uri: "bolt://localhost:7687"  # 或 bolt://neo4j:7687
     username: "neo4j"
     password: "myrag123"
   ```

3. 确认端口未被占用

### 内存不足错误

**问题**: `CUDA out of memory` 或系统内存耗尽

**解决方案**:

1. 使用INT4量化减少显存占用

   ```yaml
   llm:
     transformers_quantization: "int4"
     transformers_max_memory: 5.5  # 调整最大内存
   ```

2. 使用更小的模型

   ```yaml
   llm:
     default_model: "qwen2.5:1.5b"  # 替代7b模型
   ```

3. 使用Ollama云端模型（零本地资源消耗）

### Docker容器启动失败

**问题**: Backend容器反复重启

**解决方案**:

```bash
# 查看容器日志
docker logs myrag-backend

# 常见原因：
# 1. MySQL未就绪 - 等待30秒后重试
# 2. 端口占用 - 修改docker-compose.yml端口映射
# 3. 依赖包缺失 - 重新构建镜像
docker-compose up -d --build backend
```

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 提交Issue

- 使用清晰的标题描述问题
- 提供复现步骤
- 附上相关日志和错误信息
- 说明环境信息（OS、Python版本、Docker版本等）

### Pull Request

1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

### 代码规范

- 遵循PEP 8代码风格
- 添加必要的注释和文档字符串
- 编写单元测试
- 保持代码简洁和可维护

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 👥 团队

- **项目维护者**: [@yuluochengwen](https://github.com/yuluochengwen)

## 🙏 致谢

感谢以下开源项目：

- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的Web框架
- [LangChain](https://www.langchain.com/) - LLM应用开发框架
- [ChromaDB](https://www.trychroma.com/) - 向量数据库
- [Neo4j](https://neo4j.com/) - 图数据库
- [Ollama](https://ollama.ai/) - 本地LLM运行时
- [HuggingFace](https://huggingface.co/) - 模型和数据集平台

## 📞 联系方式

- **GitHub**: <https://github.com/yuluochengwen/MyRAG>
- **Issues**: <https://github.com/yuluochengwen/MyRAG/issues>
- **Discussions**: <https://github.com/yuluochengwen/MyRAG/discussions>

---

⭐ 如果这个项目对你有帮助，请给一个Star支持一下！

**文档版本**: v1.0.0  
**最后更新**: 2025-11-26