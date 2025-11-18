# RAG 知识库管理系统

基于 FastAPI + MySQL + ChromaDB 的 RAG (Retrieval-Augmented Generation) 知识库管理系统。

## 项目结构

```
MyRAG/
├── Backend/                    # 后端代码
│   ├── app/
│   │   ├── api/               # API路由
│   │   ├── core/              # 核心配置
│   │   ├── models/            # 数据模型
│   │   ├── services/          # 业务逻辑
│   │   ├── utils/             # 工具函数
│   │   └── websocket/         # WebSocket管理
│   ├── scripts/               # 脚本
│   ├── config.yaml            # 配置文件
│   ├── .env                   # 环境变量
│   ├── requirements.txt       # Python依赖
│   ├── Dockerfile             # Docker镜像
│   └── main.py               # 应用入口
├── Frontend/                  # 前端代码
│   ├── css/                   # 样式文件
│   ├── js/                    # JavaScript
│   └── *.html                 # HTML页面
├── KnowledgeBase/             # 知识库文件存储
├── Models/                    # 模型文件
│   ├── Embedding/             # 嵌入模型
│   ├── LLM/                   # 大语言模型
│   └── LoRA/                  # LoRA微调模型
├── VectorDB/                  # 向量数据库存储
├── logs/                      # 日志文件
├── docker-compose.yml         # Docker编排
└── nginx.conf                 # Nginx配置
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

## 技术栈

### 后端

- **框架**: FastAPI (Python 3.11)
- **数据库**: MySQL 8.0 + PyMySQL
- **向量数据库**: ChromaDB
- **LLM服务**:
  - Transformers（本地模型）
  - Ollama（本地/云端模型）
- **嵌入模型**:
  - Sentence Transformers
  - Ollama Embeddings
- **文档解析**: PyPDF2, python-docx, BeautifulSoup
- **异步**: asyncio, aiomysql
- **WebSocket**: FastAPI WebSocket
- **配置管理**: Pydantic, PyYAML

### 前端

- **UI框架**: Tailwind CSS
- **图标**: Font Awesome
- **JavaScript**: 原生 ES6+

### 部署

- **容器化**: Docker + docker-compose
- **Web服务器**: Nginx
- **进程管理**: Uvicorn

## 快速开始

### 方法一：Docker 部署（推荐）

#### Windows 一键启动

1. **启动脚本**

双击运行 `docker-start.bat`，或在命令行中执行：

```bash
.\docker-start.bat
```

脚本提供以下功能：
- 启动/停止所有服务
- 查看服务状态和日志
- 下载Ollama模型
- 重新构建服务
- 完全清理数据

2. **访问应用**

- 前端界面: http://localhost
- API文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health
- Ollama API: http://localhost:11434

#### 手动部署

1. **启动所有服务**

```bash
docker-compose up -d
```

这将启动以下服务：
- MySQL 数据库（端口3306）
- Ollama LLM服务（端口11434）
- FastAPI 后端（端口8000）
- Nginx 前端（端口80）

2. **下载Ollama模型**

```bash
# 下载LLM模型
docker exec myrag-ollama ollama pull qwen2.5:7b

# 下载Embedding模型
docker exec myrag-ollama ollama pull nomic-embed-text
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

**详细部署指南**: 参见 [Docker部署指南.md](docs/Docker部署指南.md)

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
- 插入示例智能助手数据

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

启动服务后访问：http://localhost:8000/docs

### 主要接口

#### 知识库管理

- `POST /api/knowledge-bases` - 创建知识库
- `GET /api/knowledge-bases` - 获取知识库列表
- `GET /api/knowledge-bases/{kb_id}` - 获取知识库详情
- `DELETE /api/knowledge-bases/{kb_id}` - 删除知识库
- `POST /api/knowledge-bases/{kb_id}/upload` - 上传文件

#### 嵌入模型

- `GET /api/embedding-models` - 获取可用模型列表
- `GET /api/embedding-models/{model_name}/info` - 获取模型信息

#### WebSocket

- `WS /ws/{client_id}` - WebSocket 连接

## 配置说明

### config.yaml

```yaml
app:
  name: "RAG系统"
  env: "development"
  debug: true
  host: "0.0.0.0"
  port: 8000

database:
  host: "localhost"
  port: 3306
  database: "rag_system"
  user: "root"

file:
  upload_dir: "../KnowledgeBase"
  max_size_mb: 100
  allowed_extensions: [".txt", ".pdf", ".docx", ".html", ".md"]

embedding:
  model_dir: "../Models/Embedding"
  default_model: "paraphrase-multilingual-MiniLM-L12-v2"

vector_db:
  type: "chroma"
  persist_dir: "../VectorDB"

text_processing:
  chunk_size: 500
  chunk_overlap: 50
```

### .env

```env
# 数据库
MYSQL_ROOT_PASSWORD=your_password
MYSQL_DATABASE=rag_system
MYSQL_USER=rag_user
MYSQL_PASSWORD=user_password

# 应用
SECRET_KEY=your_secret_key
```

## 开发指南

### 添加新的文件解析器

1. 在 `app/utils/file_parser.py` 中创建新的解析器类
2. 继承 `BaseParser` 并实现 `parse()` 方法
3. 在 `PARSER_MAP` 中注册新的文件类型

### 添加新的 API 路由

1. 在 `app/api/` 中创建新的路由文件
2. 定义 APIRouter 并添加路由处理函数
3. 在 `main.py` 中注册路由

### 添加新的服务

1. 在 `app/services/` 中创建服务类
2. 在 `app/core/dependencies.py` 中添加依赖注入函数
3. 在 API 路由中使用 `Depends()` 注入服务

## 故障排除

### 数据库连接失败

检查：
- MySQL 服务是否运行
- `.env` 中的数据库配置是否正确
- 防火墙是否允许连接

### 模型下载慢

设置 HuggingFace 镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### WebSocket 连接失败

检查：
- Nginx 配置是否正确转发 WebSocket
- 浏览器控制台是否有错误信息

## 许可证

MIT License

## 联系方式

如有问题，请提交 Issue。
