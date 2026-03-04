# MyRAG 项目结构重构计划

## 一、现有问题诊断

### 1.1 根目录混乱 (11 个松散文件 + 9 个顶级目录)
```
MyRAG/
├── docker-compose.yml          # Docker
├── docker-daemon-config.json   # Docker (空文件 {})
├── docker-start.bat            # Docker
├── nginx.conf                  # Docker/Nginx
├── start.bat                   # 启动脚本
├── start-fast.bat              # 启动脚本 (重复)
├── run-tests.bat               # 测试脚本
├── tempCodeRunnerFile.bat      # ❌ VS Code 临时垃圾文件
├── README.md
├── Backend/                    # 后端代码
├── Frontend/                   # 前端代码
├── KnowledgeBase/              # 运行时数据
├── VectorDB/                   # 运行时数据
├── Models/                     # 模型文件
├── logs/                       # 日志文件
├── TrainingData/               # 训练数据
├── LLaMA-Factory/              # 第三方工具
├── LLaMA-Training/             # 训练工作区
├── llamaboard_cache/           # 训练缓存
├── scripts/                    # 工具脚本
├── test/                       # 测试
└── docs/                       # 文档
```

### 1.2 数据目录重复
- `Backend/KnowledgeBase/` (空) ↔ `KnowledgeBase/` (有数据)
- `Backend/VectorDB/` (空) ↔ `VectorDB/` (有数据)
- `Backend/Models/` (空) ↔ `Models/` (有数据)
- `Backend/logs/` (空) ↔ `logs/` (有数据)

### 1.3 配置分散
- `Backend/config.yaml` — YAML 主配置
- `Backend/.env` — 环境变量
- `Backend/app/core/config.py` — Python 默认值 (与 YAML 不一致!)
- `docker-compose.yml` — Docker 环境变量 (又一套凭据)

### 1.4 启动命令不一致
| 脚本 | uvicorn 命令 | host | reload |
|------|-------------|------|--------|
| start.bat | `python -m uvicorn Backend.main:app` | 0.0.0.0 | ❌ |
| start-fast.bat | `uvicorn main:app --app-dir Backend` | 127.0.0.1 | ✅ |
| Dockerfile | `uvicorn main:app` | 0.0.0.0 | ✅ |

### 1.5 前端 4 个 JS 文件硬编码 localhost
- `chat.js` → `http://localhost:8000`
- `agent.js` → `http://localhost:8000/api/agent`
- `model-management.js` → `http://localhost:8000`
- `simple-lora-training.js` → `http://localhost:8000`

### 1.6 死代码
- `Backend/app/models/assistant.py` — SQLAlchemy 模型, 导入不存在的 `Base`, 全项目无使用
- `tempCodeRunnerFile.bat` — 仅含 "root", VS Code 临时文件
- `docker-daemon-config.json` — 空 `{}`

### 1.7 日志不一致
- `agent.py` 和 `agent_service.py` 使用 `logging.getLogger(__name__)` 而非项目的 `get_logger()`

### 1.8 config.py 默认值与 config.yaml 不一致
| 配置项 | Python 默认 | YAML 值 |
|--------|-----------|---------|
| llm.default_model | DeepSeek-OCR-3B | Qwen2.5-3B-Instruct |
| embedding.default_model | paraphrase-multilingual-MiniLM-L12-v2 | BERT-Base |
| entity_extraction.max_tokens | 512 | 1024 |
| llm.temperature | 0.7 | 0.5 |
| llm.max_tokens | 512 | 256 |

---

## 二、目标结构

```
MyRAG/
├── README.md                       # 项目说明
├── .gitignore                      # Git 忽略规则
├── .env.example                    # 环境变量模板 (新增)
├── docker-compose.yml              # Docker 编排 (保持根目录,标准做法)
├── start.bat                       # 统一本地启动脚本 (合并原两个)
│
├── Backend/                        # ===== 后端代码 =====
│   ├── main.py                     # FastAPI 入口
│   ├── config.yaml                 # 唯一 YAML 配置
│   ├── requirements.txt            # Python 依赖
│   ├── app/
│   │   ├── __init__.py             # (新增)
│   │   ├── api/                    # API 路由层
│   │   │   ├── __init__.py
│   │   │   ├── knowledge_base.py
│   │   │   ├── assistant.py
│   │   │   ├── conversation.py
│   │   │   ├── models.py
│   │   │   ├── agent.py
│   │   │   ├── lora_training.py
│   │   │   ├── simple_lora.py
│   │   │   └── websocket.py
│   │   ├── core/                   # 核心模块
│   │   │   ├── __init__.py
│   │   │   ├── config.py           # 配置 (默认值与YAML同步)
│   │   │   ├── database.py
│   │   │   └── dependencies.py
│   │   ├── models/                 # 数据模型
│   │   │   ├── __init__.py
│   │   │   ├── schemas.py
│   │   │   ├── knowledge_base.py
│   │   │   └── file.py
│   │   │   (删除 assistant.py 死代码)
│   │   ├── services/               # 业务逻辑层
│   │   │   └── (保持现有 18 个文件不动)
│   │   ├── utils/                  # 工具函数
│   │   │   └── (保持现有 6 个文件不动)
│   │   └── websocket/              # WebSocket
│   │       └── (保持现有文件不动)
│   └── scripts/                    # 数据库脚本 (保持)
│       ├── init_db.py
│       ├── init.sql
│       ├── init_lora_tables.sql
│       ├── init_simple_lora_tables.sql
│       └── migrate_lora_status.sql
│
├── Frontend/                       # ===== 前端文件 =====
│   ├── css/
│   ├── js/                         # (修复硬编码URL)
│   └── *.html
│
├── data/                           # ===== 运行时数据 (统一) =====
│   ├── knowledge_base/             # 知识库文件 (原 KnowledgeBase/)
│   ├── vector_db/                  # 向量数据库 (原 VectorDB/)
│   ├── logs/                       # 所有日志 (原 logs/)
│   └── training_data/              # 训练数据 (原 TrainingData/)
│
├── Models/                         # ===== 模型文件 (独立,体积大) =====
│   ├── Embedding/
│   ├── LLM/
│   └── LoRA/
│
├── deploy/                         # ===== 部署配置 =====
│   ├── Dockerfile                  # (原 Backend/Dockerfile)
│   ├── nginx.conf                  # (原根目录)
│   ├── docker-start.bat            # (原根目录)
│   └── docker-daemon-config.json   # (原根目录,空文件保留待配置)
│
├── scripts/                        # ===== 工具脚本 =====
│   ├── run-tests.bat               # (原根目录)
│   ├── manage_transformers.py
│   ├── preload-huggingface-models.py
│   └── preload-ollama-models.sh
│
├── test/                           # ===== 测试 (保持) =====
│
├── docs/                           # ===== 文档 (保持) =====
│
├── LLaMA-Factory/                  # 第三方工具 (不动)
├── LLaMA-Training/                 # 训练工作区 (不动)
└── llamaboard_cache/               # 训练缓存 (不动)
```

---

## 三、重构步骤 (严格执行顺序)

### Step 1: 清理垃圾文件
- [x] 删除 `tempCodeRunnerFile.bat`
- [x] 删除 `Backend/app/models/assistant.py` (死代码)
- [x] 更新 `Backend/app/models/__init__.py` 移除 assistant 相关引用

### Step 2: 合并数据目录到 data/
- [x] 创建 `data/` 目录
- [x] 移动 `KnowledgeBase/` → `data/knowledge_base/`
- [x] 移动 `VectorDB/` → `data/vector_db/`
- [x] 移动 `logs/` → `data/logs/`
- [x] 移动 `TrainingData/` → `data/training_data/`
- [x] 删除 Backend 下的空目录: `Backend/KnowledgeBase/`, `Backend/VectorDB/`, `Backend/Models/`, `Backend/logs/`

### Step 3: 合并部署文件到 deploy/
- [x] 创建 `deploy/` 目录
- [x] 移动 `Backend/Dockerfile` → `deploy/Dockerfile`
- [x] 移动 `nginx.conf` → `deploy/nginx.conf`
- [x] 移动 `docker-start.bat` → `deploy/docker-start.bat`
- [x] 移动 `docker-daemon-config.json` → `deploy/docker-daemon-config.json`

### Step 4: 整理脚本
- [x] 移动 `run-tests.bat` → `scripts/run-tests.bat`
- [x] 删除 `start-fast.bat` (合并功能到 start.bat)
- [x] 重写 `start.bat` 合并两种启动模式

### Step 5: 更新配置路径
- [x] 更新 `Backend/config.yaml` 中的所有路径 (KnowledgeBase→data/knowledge_base 等)
- [x] 更新 `Backend/app/core/config.py` 默认值与 yaml 保持一致, 更新路径
- [x] 更新 `Backend/app/utils/logger.py` 日志路径

### Step 6: 更新 Docker 配置
- [x] 更新 `docker-compose.yml` — build context, volume mounts, Dockerfile 路径
- [x] 更新 `deploy/Dockerfile` — 目录创建命令
- [x] 更新 `deploy/docker-start.bat` — 路径引用

### Step 7: 更新后端代码引用
- [x] 更新所有引用旧数据路径的 service 文件
- [x] 更新 Backend/scripts/init_db.py (如有路径引用)

### Step 8: 修复前端硬编码 URL
- [x] `Frontend/js/chat.js` — 改用相对路径
- [x] `Frontend/js/agent.js` — 改用相对路径
- [x] `Frontend/js/model-management.js` — 改用相对路径
- [x] `Frontend/js/simple-lora-training.js` — 改用相对路径

### Step 9: 修复日志不一致
- [x] `Backend/app/api/agent.py` — 改用 `get_logger()`
- [x] `Backend/app/services/agent_service.py` — 改用 `get_logger()`

### Step 10: 同步配置默认值
- [x] config.py 中 Python 默认值与 config.yaml 保持一致

### Step 11: 更新 .gitignore
- [x] 更新路径匹配新的 data/ 结构

### Step 12: 创建 .env.example
- [x] 创建环境变量模板文件

### Step 13: 创建 Backend/app/__init__.py
- [x] 添加缺失的包初始化文件

### Step 14: 更新 README.md
- [x] 更新项目结构说明和启动命令

---

## 四、风险评估与回退策略

### 最高风险操作
1. **移动数据目录** — VectorDB 的 ChromaDB sqlite 使用相对路径存储,移动后需确保配置路径正确指向新位置
2. **Docker 构建上下文变更** — Dockerfile 移到 deploy/ 后 build context 需调整

### 回退策略
- 所有移动操作通过 `move` 命令执行(非删除+重建)
- 修改前记录原始路径映射
- 如出现问题,可按相反顺序恢复

### 不动的部分 (降低风险)
- `LLaMA-Factory/` — 完整第三方项目,不动
- `LLaMA-Training/` — 训练工作区,不动
- `llamaboard_cache/` — 训练缓存,不动
- `Models/` — 保持根目录位置,用户常直接操作
- `Backend/app/services/` — 18 个服务文件内部逻辑不动
- `Backend/app/api/` — 路由文件内部逻辑不动(仅修 URL 和日志)
- `test/` — 保持位置不动

---

## 五、需要修改的文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| tempCodeRunnerFile.bat | 删除 | 垃圾文件 |
| Backend/app/models/assistant.py | 删除 | SQLAlchemy 死代码 |
| Backend/app/models/__init__.py | 修改 | 移除 assistant 引用 |
| KnowledgeBase/ | 移动→data/knowledge_base/ | 数据合并 |
| VectorDB/ | 移动→data/vector_db/ | 数据合并 |
| logs/ | 移动→data/logs/ | 数据合并 |
| TrainingData/ | 移动→data/training_data/ | 数据合并 |
| Backend/KnowledgeBase/ | 删除 | 空目录 |
| Backend/VectorDB/ | 删除 | 空目录 |
| Backend/Models/ | 删除 | 空目录 |
| Backend/logs/ | 删除 | 空目录 |
| Backend/Dockerfile | 移动→deploy/ | 部署文件合并 |
| nginx.conf | 移动→deploy/ | 部署文件合并 |
| docker-start.bat | 移动→deploy/ | 部署文件合并 |
| docker-daemon-config.json | 移动→deploy/ | 部署文件合并 |
| run-tests.bat | 移动→scripts/ | 脚本合并 |
| start-fast.bat | 删除 | 合并到 start.bat |
| start.bat | 重写 | 合并两种启动模式 |
| Backend/config.yaml | 修改 | 更新路径 |
| Backend/app/core/config.py | 修改 | 同步默认值+更新路径 |
| Backend/app/utils/logger.py | 修改 | 日志路径 |
| docker-compose.yml | 修改 | 更新挂载和构建路径 |
| deploy/Dockerfile | 修改 | 更新目录命令 |
| deploy/docker-start.bat | 修改 | 更新路径引用 |
| Frontend/js/chat.js | 修改 | 修复硬编码 URL |
| Frontend/js/agent.js | 修改 | 修复硬编码 URL |
| Frontend/js/model-management.js | 修改 | 修复硬编码 URL |
| Frontend/js/simple-lora-training.js | 修改 | 修复硬编码 URL |
| Backend/app/api/agent.py | 修改 | 修复日志 |
| Backend/app/services/agent_service.py | 修改 | 修复日志 |
| .gitignore | 修改 | 更新路径 |
| .env.example | 新建 | 环境变量模板 |
| Backend/app/__init__.py | 新建 | 包初始化 |
