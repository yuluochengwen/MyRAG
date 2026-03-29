# 环境变量文件说明

## 文件列表

项目中存在两个环境变量示例文件，用于不同的部署场景：

### 1. `.env.example` (根目录)
- **用途**: 本地开发环境
- **使用场景**: 直接运行Python应用，不使用Docker
- **配置特点**: 
  - 连接本地服务 (localhost)
  - 适用于开发调试
  - 路径指向本地安装的服务

### 2. `deploy/.env.docker.example` (deploy目录)
- **用途**: Docker部署环境
- **使用场景**: 使用Docker Compose部署
- **配置特点**:
  - 连接Docker容器服务 (mysql, ollama等)
  - 适用于生产部署
  - 路径指向Docker容器内的服务

## 使用方法

### 本地开发

```bash
# 1. 复制环境变量文件
cp .env.example Backend/.env

# 2. 修改配置（如果需要）
vim Backend/.env  # Linux/Mac
notepad Backend\.env  # Windows

# 3. 启动本地服务
# 确保MySQL、Neo4j、Ollama等服务已在本地运行
cd Backend
python main.py
```

### Docker部署

```bash
# 1. 复制环境变量文件
cp deploy/.env.docker.example deploy/.env

# 2. 修改配置（如果需要）
vim deploy/.env  # Linux/Mac
notepad deploy\.env  # Windows

# 3. 使用管理脚本启动
# Windows
deploy\docker-manage.bat start

# Linux/Mac
./deploy/docker-manage.sh start
```

## 主要区别

| 配置项 | 本地开发 (.env.example) | Docker部署 (.env.docker.example) |
|--------|------------------------|----------------------------------|
| MYSQL_HOST | localhost | mysql |
| MYSQL_USER | root | myrag |
| MYSQL_PASSWORD | 123456 | myrag123 |
| OLLAMA_BASE_URL | http://localhost:11434 | http://ollama:11434 |
| NEO4J_URI | bolt://localhost:7687 | bolt://neo4j:7687 |
| PROJECT_ROOT | 未设置 | /app |

## 注意事项

1. **不要混用**: 本地开发使用根目录的`.env.example`，Docker部署使用`deploy/.env.docker.example`
2. **文件位置**: 
   - 本地开发：复制到 `Backend/.env`
   - Docker部署：复制到 `deploy/.env`
3. **安全性**: 
   - 不要将 `.env` 文件提交到Git
   - 生产环境请修改默认密码
4. **配置优先级**: 
   - 环境变量 > .env文件 > 默认值

## 快速切换

### 从本地开发切换到Docker部署

```bash
# 1. 停止本地服务
# 2. 启动Docker服务
cp deploy/.env.docker.example deploy/.env
deploy\docker-manage.bat start  # Windows
./deploy/docker-manage.sh start  # Linux/Mac
```

### 从Docker部署切换到本地开发

```bash
# 1. 停止Docker服务
deploy\docker-manage.bat stop  # Windows
./deploy/docker-manage.sh stop  # Linux/Mac

# 2. 启动本地服务
cp .env.example Backend/.env
cd Backend
python main.py
```

## 故障排除

### 问题1: 连接失败
- **原因**: 使用了错误的环境变量文件
- **解决**: 确认当前运行模式，使用对应的配置文件

### 问题2: 服务找不到
- **原因**: HOST配置错误
- **解决**: 
  - 本地开发: 使用 `localhost`
  - Docker部署: 使用容器名 (mysql, ollama, neo4j)

### 问题3: 权限错误
- **原因**: MySQL用户配置错误
- **解决**:
  - 本地开发: 使用 root 用户
  - Docker部署: 使用 myrag 用户

## 总结

两个环境变量文件分别对应不同的使用场景，请根据实际情况选择正确的文件：
- **本地开发** → `.env.example`
- **Docker部署** → `deploy/.env.docker.example`
