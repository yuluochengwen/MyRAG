# MyRAG Docker 快速部署指南

## 📋 前置要求

- Docker Desktop 已安装并运行
- 至少 8GB RAM
- 至少 10GB 可用磁盘空间
- Windows/Linux/macOS 系统

## 🚀 快速启动

### 方法一：使用启动脚本（推荐 - Windows）

```bash
# 运行启动脚本
docker-start.bat

# 选择选项 1: 启动所有服务
# 等待服务启动完成（首次启动需要拉取镜像，大约5-10分钟）
```

### 方法二：使用 docker-compose 命令

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

## 📦 预装模型（重要！）

首次部署后，**必须**下载模型才能使用RAG功能：

### 使用启动脚本预装（推荐）

```bash
# 运行 docker-start.bat
# 选择选项 6: Preload models (Ollama + HuggingFace)
```

这将自动下载：
- **qwen2.5:1.5b** - 轻量级LLM（~1GB）
- **nomic-embed-text** - Ollama嵌入模型（~274MB）
- **paraphrase-multilingual-MiniLM-L12-v2** - HuggingFace嵌入模型（~471MB）

### 手动预装

#### Ollama 模型

```bash
# 下载LLM模型
docker exec myrag-ollama ollama pull qwen2.5:1.5b

# 下载嵌入模型
docker exec myrag-ollama ollama pull nomic-embed-text

# 查看已安装模型
docker exec myrag-ollama ollama list
```

#### HuggingFace 模型

```bash
# 在容器内运行预装脚本
docker exec myrag-backend python /app/../scripts/preload-huggingface-models.py
```

## 🌐 访问服务

服务启动后，访问以下地址：

- **前端界面**: http://localhost
- **API文档**: http://localhost:8000/docs
- **Neo4j浏览器**: http://localhost:7474 (用户: neo4j, 密码: myrag123)
- **Ollama API**: http://localhost:11434

## 🔧 服务配置

### 默认端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Nginx | 80 | 前端服务 |
| Backend | 8000 | FastAPI后端 |
| MySQL | 3306 | 数据库 |
| Ollama | 11434 | LLM服务 |
| Neo4j HTTP | 7474 | 图数据库UI |
| Neo4j Bolt | 7687 | 图数据库连接 |

### 默认账号

**MySQL:**
- 用户: `myrag`
- 密码: `myrag123`
- 数据库: `myrag`

**Neo4j:**
- 用户: `neo4j`
- 密码: `myrag123`

**⚠️ 生产环境请务必修改密码！**

## 📁 数据持久化

所有数据都保存在以下Docker卷中：

```
mysql_data        -> MySQL数据库数据
ollama_data       -> Ollama模型和数据
neo4j_data        -> Neo4j图数据库数据
neo4j_logs        -> Neo4j日志
```

项目目录挂载：
```
./KnowledgeBase   -> 上传的文档
./Models          -> 本地模型文件
./VectorDB        -> ChromaDB向量数据
./logs            -> 应用日志
```

## 🛠️ 常用命令

### 查看服务状态

```bash
docker-compose ps
```

### 查看日志

```bash
# 所有服务
docker-compose logs -f

# 特定服务
docker-compose logs -f backend
docker-compose logs -f mysql
docker-compose logs -f ollama
```

### 重启服务

```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart backend
```

### 停止服务

```bash
docker-compose down
```

### 重新构建

```bash
# 重新构建并启动
docker-compose up -d --build
```

### 清理所有数据（危险！）

```bash
# 删除所有容器、网络和数据卷
docker-compose down -v
```

## 🔍 故障排查

### 1. Backend容器启动失败

```bash
# 查看后端日志
docker-compose logs backend

# 常见原因：
# - MySQL未就绪：等待30秒后重试
# - 端口占用：检查8000端口是否被占用
# - 依赖包缺失：重新构建 docker-compose up -d --build backend
```

### 2. Ollama模型未下载

```bash
# 检查Ollama服务状态
docker exec myrag-ollama ollama list

# 如果为空，手动下载模型
docker exec myrag-ollama ollama pull qwen2.5:1.5b
```

### 3. 无法访问前端

```bash
# 检查Nginx状态
docker-compose logs nginx

# 检查Backend是否正常
curl http://localhost:8000/health
```

### 4. MySQL连接失败

```bash
# 进入MySQL容器检查
docker exec -it myrag-mysql mysql -u myrag -pmyrag123 myrag

# 验证数据库和用户
SHOW DATABASES;
SELECT user, host FROM mysql.user WHERE user='myrag';
```

### 5. 容器内存不足

```bash
# 检查Docker资源限制
docker stats

# 在Docker Desktop中增加内存分配（推荐至少8GB）
```

## 📊 健康检查

```bash
# Backend健康检查
curl http://localhost:8000/health

# 预期输出：
{
  "status": "healthy",
  "database": "connected"
}
```

## 🔄 更新部署

```bash
# 1. 拉取最新代码
git pull

# 2. 停止服务
docker-compose down

# 3. 重新构建
docker-compose up -d --build

# 4. 验证服务
docker-compose ps
```

## 📝 配置文件说明

### docker-compose.yml
- 定义所有服务的配置
- 配置网络和数据卷
- 设置环境变量

### Backend/Dockerfile
- Backend服务的构建配置
- Python依赖安装
- 目录权限设置

### nginx.conf
- Nginx反向代理配置
- API路由配置
- WebSocket支持

### Backend/.env
- 本地开发环境变量
- Docker环境已通过docker-compose.yml配置，无需修改.env

## 🎯 推荐模型配置

### 轻量级配置（6GB显存）

```yaml
# Backend/config.yaml
llm:
  default_provider: "transformers"
  default_model: "qwen2.5:1.5b"  # Ollama模型
  
embedding:
  provider: "ollama"
  ollama:
    default_model: "nomic-embed-text"
```

### 标准配置（8GB+显存）

```yaml
llm:
  default_provider: "transformers"
  default_model: "qwen2.5:7b"
  
embedding:
  provider: "transformers"
  default_model: "paraphrase-multilingual-MiniLM-L12-v2"
```

## 🚨 注意事项

1. **首次启动较慢**: 需要拉取镜像和安装依赖，请耐心等待
2. **模型必须预装**: 否则RAG功能无法使用
3. **内存要求**: 建议Docker分配至少8GB内存
4. **磁盘空间**: 模型和数据至少需要10GB空间
5. **生产部署**: 请修改所有默认密码
6. **GPU支持**: 如需GPU加速，请取消docker-compose.yml中Ollama的GPU配置注释

## 📞 获取帮助

- 查看日志: `docker-compose logs -f`
- 检查服务: `docker-compose ps`
- 重启服务: `docker-compose restart`
- 项目文档: `docs/` 目录

## 🎉 验证部署成功

1. ✅ 所有容器状态为 `Up`
2. ✅ 访问 http://localhost 看到前端界面
3. ✅ 访问 http://localhost:8000/docs 看到API文档
4. ✅ `docker exec myrag-ollama ollama list` 显示已安装模型
5. ✅ 可以创建知识库并上传文档

**部署成功！开始使用MyRAG吧！** 🚀
