# LoRA 微调系统部署指南

## 概述

本文档提供 LoRA 微调训练和推理系统的完整部署流程，包括环境准备、数据库迁移、服务配置和验证步骤。

## 部署前检查清单

### 硬件要求

- [ ] CPU: 4核以上
- [ ] 内存: 16GB 以上（推荐 32GB）
- [ ] GPU: NVIDIA GPU with CUDA support
  - [ ] 显存: 最小 8GB（QLoRA），推荐 16GB+（LoRA）
- [ ] 磁盘空间: 100GB 以上可用空间
  - [ ] 系统盘: 20GB
  - [ ] 模型存储: 50GB（Models/LoRA/）
  - [ ] 训练数据: 10GB（data/training_data/）
  - [ ] 日志: 10GB（data/logs/）

### 软件要求

- [ ] 操作系统: Ubuntu 20.04+ / CentOS 8+ / Windows 10+
- [ ] Python: 3.11+
- [ ] MySQL: 8.0+
- [ ] CUDA: 11.8+ (GPU 环境)
- [ ] Node.js: 16+ (前端开发)

### 网络要求

- [ ] 端口 8000 可访问（FastAPI 服务）
- [ ] 端口 3306 可访问（MySQL，内网）
- [ ] 互联网连接（下载模型和依赖）

## 部署步骤

### 1. 环境准备

#### 1.1 安装 Python 依赖

```bash
cd Backend
pip install -r requirements.txt
```

**验证安装**：
```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import transformers; print(f'Transformers: {transformers.__version__}')"
python -c "import peft; print(f'PEFT: {peft.__version__}')"
```

#### 1.2 验证 CUDA 环境（GPU 部署）

```bash
nvidia-smi
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python -c "import torch; print(f'CUDA version: {torch.version.cuda}')"
```

#### 1.3 创建必要目录

```bash
mkdir -p Models/LoRA
mkdir -p data/training_data/temp
mkdir -p data/logs
mkdir -p data/vector_db
```

**设置权限**：
```bash
chmod 755 Models/LoRA
chmod 755 data/training_data/temp
chmod 755 data/logs
```

### 2. 数据库迁移

#### 2.1 备份现有数据库

```bash
mysqldump -u root -p myrag > backup_$(date +%Y%m%d_%H%M%S).sql
```

#### 2.2 执行迁移脚本

```bash
mysql -u root -p myrag < Backend/scripts/lora_migration.sql
```

#### 2.3 验证迁移

```sql
USE myrag;

-- 检查表是否创建
SHOW TABLES LIKE '%lora%';

-- 检查 assistants 表
DESCRIBE assistants;

-- 验证外键约束
SELECT CONSTRAINT_NAME, TABLE_NAME, REFERENCED_TABLE_NAME 
FROM information_schema.KEY_COLUMN_USAGE 
WHERE TABLE_SCHEMA = 'myrag' 
AND CONSTRAINT_NAME LIKE '%lora%';
```

**预期结果**：
- `lora_models` 表存在
- `lora_training_jobs` 表存在
- `assistants` 表包含 `lora_model_id` 字段
- 外键约束 `fk_assistants_lora_model` 存在

### 3. 配置文件设置

#### 3.1 环境变量配置

编辑 `Backend/.env`：

```bash
# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=myrag

# LoRA 配置
LORA_MODEL_DIR=Models/LoRA
LORA_TRAINING_DATA_DIR=data/training_data
LORA_LOG_DIR=data/logs

# 训练配置
MAX_TRAINING_QUEUE_SIZE=1
BASE_MODEL_CACHE_SIZE=2
LORA_MODEL_CACHE_SIZE=5

# GPU 配置
CUDA_VISIBLE_DEVICES=0
```

#### 3.2 应用配置

```bash
# 重启服务以应用配置
sudo systemctl restart myrag-backend
```

### 4. 服务启动

#### 4.1 启动后端服务

**开发模式**：
```bash
cd Backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**生产模式**：
```bash
cd Backend
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

#### 4.2 验证服务启动

```bash
# 检查服务状态
curl http://localhost:8000/health

# 检查 API 文档
curl http://localhost:8000/docs
```

**预期结果**：
- 健康检查返回 200
- API 文档可访问
- 日志无错误

#### 4.3 启动前端服务

```bash
cd Frontend
# 如果使用开发服务器
python -m http.server 3000

# 或使用 Nginx 部署
sudo cp -r Frontend/* /var/www/html/
```

### 5. 功能验证

#### 5.1 验证 LoRA API

```bash
# 获取基座模型列表
curl http://localhost:8000/api/lora/base-models

# 获取 LoRA 模型列表
curl http://localhost:8000/api/lora/models
```

#### 5.2 验证数据集验证

```bash
# 创建测试数据集
cat > test_dataset.json << EOF
[
  {
    "instruction": "测试指令",
    "input": "",
    "output": "测试输出"
  }
]
EOF

# 验证数据集
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

#### 5.3 验证 WebSocket 连接

```javascript
// 在浏览器控制台测试
const ws = new WebSocket('ws://localhost:8000/ws/training/test');
ws.onopen = () => console.log('WebSocket 连接成功');
ws.onerror = (error) => console.error('WebSocket 错误:', error);
```

#### 5.4 验证助手 LoRA 集成

```bash
# 创建助手（不带 LoRA）
curl -X POST http://localhost:8000/api/assistants \
  -H "Content-Type: application/json" \
  -d '{
    "name": "测试助手",
    "llm_model": "Qwen3-8B",
    "llm_provider": "local",
    "embedding_model": "bge-large-zh-v1.5",
    "system_prompt": "你是一个测试助手"
  }'
```

### 6. 性能优化

#### 6.1 数据库优化

```sql
-- 添加索引
CREATE INDEX idx_lora_base_model ON lora_models(base_model_name);
CREATE INDEX idx_training_status ON lora_training_jobs(status);
CREATE INDEX idx_training_created ON lora_training_jobs(created_at);

-- 优化查询缓存
SET GLOBAL query_cache_size = 268435456;
SET GLOBAL query_cache_type = 1;
```

#### 6.2 应用优化

```python
# Backend/app/core/config.py
class Settings:
    # 连接池配置
    DB_POOL_SIZE = 10
    DB_MAX_OVERFLOW = 20
    
    # 缓存配置
    BASE_MODEL_CACHE_SIZE = 2
    LORA_MODEL_CACHE_SIZE = 5
    
    # 训练配置
    MAX_TRAINING_QUEUE_SIZE = 1
```

#### 6.3 Nginx 配置（生产环境）

```nginx
# /etc/nginx/sites-available/myrag
upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;
    
    # 静态文件
    location / {
        root /var/www/html;
        try_files $uri $uri/ /index.html;
    }
    
    # API 代理
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # WebSocket 代理
    location /ws/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
    
    # 文件上传大小限制
    client_max_body_size 100M;
}
```

### 7. 监控和日志

#### 7.1 配置日志

```python
# Backend/app/utils/logger.py
import logging
from logging.handlers import RotatingFileHandler

# 应用日志
app_handler = RotatingFileHandler(
    'data/logs/app.log',
    maxBytes=10485760,  # 10MB
    backupCount=10
)

# 训练日志
training_handler = RotatingFileHandler(
    'data/logs/lora_training.log',
    maxBytes=10485760,
    backupCount=10
)
```

#### 7.2 监控指标

使用 Prometheus + Grafana 监控：

```python
# Backend/app/main.py
from prometheus_client import Counter, Histogram, Gauge

# 训练任务计数
training_jobs_total = Counter('training_jobs_total', 'Total training jobs')
training_jobs_success = Counter('training_jobs_success', 'Successful training jobs')
training_jobs_failed = Counter('training_jobs_failed', 'Failed training jobs')

# 推理延迟
inference_latency = Histogram('inference_latency_seconds', 'Inference latency')

# 模型缓存
model_cache_size = Gauge('model_cache_size', 'Number of cached models')
```

#### 7.3 日志查看

```bash
# 查看应用日志
tail -f data/logs/app.log

# 查看训练日志
tail -f data/logs/lora_training_*.log

# 查看错误日志
grep ERROR data/logs/app.log

# 查看 OOM 错误
grep "out of memory" data/logs/lora_training_*.log
```

### 8. 备份和恢复

#### 8.1 数据备份

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backup/myrag"
DATE=$(date +%Y%m%d_%H%M%S)

# 备份数据库
mysqldump -u root -p myrag > $BACKUP_DIR/db_$DATE.sql

# 备份 LoRA 模型
tar -czf $BACKUP_DIR/lora_models_$DATE.tar.gz Models/LoRA/

# 备份配置文件
tar -czf $BACKUP_DIR/config_$DATE.tar.gz Backend/.env Backend/config.yaml

# 清理旧备份（保留 30 天）
find $BACKUP_DIR -name "*.sql" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
```

#### 8.2 定时备份

```bash
# 添加到 crontab
crontab -e

# 每天凌晨 2 点备份
0 2 * * * /path/to/backup.sh
```

#### 8.3 恢复数据

```bash
# 恢复数据库
mysql -u root -p myrag < backup_20240115_020000.sql

# 恢复 LoRA 模型
tar -xzf lora_models_20240115_020000.tar.gz -C /

# 恢复配置
tar -xzf config_20240115_020000.tar.gz -C /
```

### 9. 安全配置

#### 9.1 数据库安全

```sql
-- 创建专用数据库用户
CREATE USER 'myrag_lora'@'localhost' IDENTIFIED BY 'strong_password';

-- 授予必要权限
GRANT SELECT, INSERT, UPDATE, DELETE ON myrag.lora_models TO 'myrag_lora'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON myrag.lora_training_jobs TO 'myrag_lora'@'localhost';
GRANT SELECT, UPDATE ON myrag.assistants TO 'myrag_lora'@'localhost';

FLUSH PRIVILEGES;
```

#### 9.2 文件权限

```bash
# 限制敏感文件权限
chmod 600 Backend/.env
chmod 600 Backend/config.yaml

# 限制模型目录权限
chmod 750 Models/LoRA
chown -R myrag:myrag Models/LoRA
```

#### 9.3 API 安全

```python
# Backend/app/core/security.py
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    if api_key != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
```

### 10. 故障排除

#### 问题 1：训练任务卡住

**症状**：训练进度不更新，WebSocket 无消息

**排查步骤**：
```bash
# 检查进程
ps aux | grep python

# 检查 GPU 使用
nvidia-smi

# 检查日志
tail -f data/logs/lora_training_*.log
```

**解决方案**：
- 重启训练服务
- 检查 GPU 显存
- 清理僵尸进程

#### 问题 2：LoRA 加载失败

**症状**：推理时报错 "LoRA model not found"

**排查步骤**：
```bash
# 检查文件是否存在
ls -la Models/LoRA/

# 检查数据库记录
mysql -u root -p -e "SELECT * FROM myrag.lora_models;"

# 检查文件权限
ls -la Models/LoRA/your-lora-model/
```

**解决方案**：
- 验证文件路径
- 检查文件权限
- 重新训练模型

#### 问题 3：WebSocket 连接失败

**症状**：前端无法连接 WebSocket

**排查步骤**：
```bash
# 检查端口
netstat -tulpn | grep 8000

# 检查防火墙
sudo ufw status

# 测试连接
wscat -c ws://localhost:8000/ws/training/test
```

**解决方案**：
- 开放端口
- 检查 Nginx 配置
- 验证 WebSocket 路由

### 11. 升级和维护

#### 11.1 版本升级

```bash
# 1. 备份数据
./backup.sh

# 2. 停止服务
sudo systemctl stop myrag-backend

# 3. 更新代码
git pull origin main

# 4. 更新依赖
pip install -r Backend/requirements.txt --upgrade

# 5. 执行迁移（如果有）
mysql -u root -p myrag < Backend/scripts/migration_v2.sql

# 6. 启动服务
sudo systemctl start myrag-backend

# 7. 验证功能
curl http://localhost:8000/health
```

#### 11.2 定期维护

```bash
# 每周任务
- 检查磁盘空间
- 清理临时文件
- 检查日志大小
- 验证备份

# 每月任务
- 更新依赖包
- 优化数据库
- 审查安全日志
- 性能测试
```

## 部署验证清单

### 基础功能

- [ ] 服务启动成功
- [ ] 数据库连接正常
- [ ] API 文档可访问
- [ ] 健康检查通过

### LoRA 功能

- [ ] 获取基座模型列表
- [ ] 获取 LoRA 模型列表
- [ ] 数据集验证功能
- [ ] 训练任务提交
- [ ] WebSocket 连接
- [ ] 训练进度推送
- [ ] LoRA 推理功能

### 集成功能

- [ ] 创建带 LoRA 的助手
- [ ] 对话使用 LoRA 推理
- [ ] LoRA 加载失败回退

### 性能指标

- [ ] LoRA 推理速度 ≥ 80%
- [ ] WebSocket 延迟 < 1s
- [ ] LoRA 加载时间 < 5s
- [ ] 缓存命中率 > 80%

### 安全配置

- [ ] 数据库用户权限
- [ ] 文件权限设置
- [ ] API 密钥配置
- [ ] 防火墙规则

### 监控和日志

- [ ] 应用日志正常
- [ ] 训练日志正常
- [ ] 监控指标收集
- [ ] 告警配置

### 备份和恢复

- [ ] 数据库备份
- [ ] 模型文件备份
- [ ] 配置文件备份
- [ ] 恢复流程测试

## 联系支持

如果在部署过程中遇到问题：

1. 查看日志：`data/logs/app.log`
2. 查看文档：`Backend/docs/`
3. 提交 Issue：[GitHub Issues]
4. 联系团队：[support@example.com]

## 附录

### A. 系统要求详细说明

#### GPU 显存需求

| 模型大小 | LoRA 模式 | QLoRA 模式 |
|---------|----------|-----------|
| 7B | 16GB | 8GB |
| 13B | 24GB | 12GB |
| 70B | 80GB | 40GB |

#### 磁盘空间需求

| 组件 | 空间需求 |
|------|---------|
| 基座模型 | 15-30GB/模型 |
| LoRA 权重 | 100-500MB/模型 |
| 训练数据 | 取决于数据集大小 |
| 日志文件 | 1-5GB |
| 临时文件 | 5-10GB |

### B. 常用命令速查

```bash
# 服务管理
sudo systemctl start myrag-backend
sudo systemctl stop myrag-backend
sudo systemctl restart myrag-backend
sudo systemctl status myrag-backend

# 日志查看
tail -f data/logs/app.log
tail -f data/logs/lora_training_*.log

# 数据库操作
mysql -u root -p myrag
mysqldump -u root -p myrag > backup.sql

# GPU 监控
nvidia-smi
watch -n 1 nvidia-smi

# 磁盘空间
df -h
du -sh Models/LoRA/*
```

### C. 性能调优建议

1. **数据库优化**
   - 增加连接池大小
   - 启用查询缓存
   - 定期优化表

2. **应用优化**
   - 增加模型缓存大小
   - 使用异步 I/O
   - 启用 gzip 压缩

3. **GPU 优化**
   - 使用混合精度训练
   - 启用梯度检查点
   - 优化 batch size

4. **网络优化**
   - 启用 HTTP/2
   - 配置 CDN
   - 压缩静态资源
