# Docker部署指南

## 快速开始

### 1. 启动所有服务

```bash
docker-compose up -d
```

这将启动：
- MySQL数据库（端口3306）
- Ollama服务（端口11434）
- FastAPI后端（端口8000）
- Nginx前端（端口80）

### 2. 查看服务状态

```bash
docker-compose ps
```

### 3. 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend
docker-compose logs -f ollama
```

### 4. 停止服务

```bash
docker-compose down
```

### 5. 完全清理（包括数据卷）

```bash
docker-compose down -v
```

## Ollama模型管理

### 下载模型

在Ollama容器中下载模型：

```bash
# 进入Ollama容器
docker exec -it myrag-ollama bash

# 下载LLM模型
ollama pull qwen2.5:7b
ollama pull deepseek-r1:8b
ollama pull deepseek-r1:1.5b

# 下载Embedding模型
ollama pull nomic-embed-text

# 查看已安装模型
ollama list

# 退出容器
exit
```

或者直接执行：

```bash
docker exec myrag-ollama ollama pull qwen2.5:7b
docker exec myrag-ollama ollama pull nomic-embed-text
```

### 测试Ollama服务

```bash
curl http://localhost:11434/api/tags
```

## 环境变量配置

在`docker-compose.yml`中可配置的环境变量：

### MySQL配置
- `MYSQL_ROOT_PASSWORD`: root用户密码（默认：123456）
- `MYSQL_DATABASE`: 数据库名称（默认：myrag）
- `MYSQL_USER`: 应用用户名（默认：myrag）
- `MYSQL_PASSWORD`: 应用用户密码（默认：myrag123）

### 后端配置
- `MYSQL_HOST`: MySQL主机名（默认：mysql）
- `MYSQL_PORT`: MySQL端口（默认：3306）
- `OLLAMA_BASE_URL`: Ollama服务地址（默认：http://ollama:11434）

## GPU支持

如果需要使用GPU加速Ollama，取消注释`docker-compose.yml`中的以下内容：

```yaml
ollama:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

**前置条件：**
1. 安装NVIDIA Docker支持：
   ```bash
   # 安装nvidia-container-toolkit
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
   curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
   
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   sudo systemctl restart docker
   ```

2. 验证GPU可用：
   ```bash
   docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
   ```

## 数据持久化

Docker使用以下volume持久化数据：

- `mysql_data`: MySQL数据库数据
- `ollama_data`: Ollama模型数据
- `./KnowledgeBase`: 知识库文件
- `./Models`: Transformers模型
- `./VectorDB`: ChromaDB向量数据库
- `./logs`: 应用日志

## 健康检查

后端服务包含健康检查端点：

```bash
curl http://localhost:8000/health
```

## 常见问题

### 1. MySQL连接失败

确保MySQL服务已完全启动：
```bash
docker-compose logs mysql
```

等待看到"ready for connections"消息。

### 2. Ollama服务不可用

检查Ollama服务状态：
```bash
docker-compose logs ollama
curl http://localhost:11434/api/tags
```

### 3. 后端启动失败

查看后端日志：
```bash
docker-compose logs backend
```

常见原因：
- MySQL未就绪
- 依赖包安装失败
- 端口被占用

### 4. 端口冲突

如果端口已被占用，修改`docker-compose.yml`中的端口映射：

```yaml
ports:
  - "8001:8000"  # 将8000改为8001
```

## 更新和维护

### 更新代码

```bash
# 停止服务
docker-compose down

# 拉取最新代码
git pull

# 重新构建并启动
docker-compose up -d --build
```

### 备份数据

```bash
# 备份MySQL
docker exec myrag-mysql mysqldump -u root -p123456 myrag > backup.sql

# 备份向量数据库
tar -czf vectordb_backup.tar.gz VectorDB/

# 备份知识库文件
tar -czf knowledgebase_backup.tar.gz KnowledgeBase/
```

### 恢复数据

```bash
# 恢复MySQL
docker exec -i myrag-mysql mysql -u root -p123456 myrag < backup.sql

# 恢复向量数据库
tar -xzf vectordb_backup.tar.gz

# 恢复知识库文件
tar -xzf knowledgebase_backup.tar.gz
```

## 生产环境建议

1. **修改默认密码**：更改MySQL的root密码和应用密码
2. **使用环境变量文件**：创建`.env`文件管理敏感信息
3. **配置日志轮转**：防止日志文件过大
4. **设置资源限制**：在`docker-compose.yml`中添加CPU和内存限制
5. **启用HTTPS**：配置Nginx SSL证书
6. **监控和告警**：集成Prometheus/Grafana等监控工具

## 访问应用

- **前端界面**: http://localhost
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **Ollama API**: http://localhost:11434

## 技术栈

- **数据库**: MySQL 8.0
- **向量数据库**: ChromaDB
- **后端框架**: FastAPI + Python 3.11
- **LLM服务**: Ollama
- **前端服务器**: Nginx
- **容器编排**: Docker Compose
