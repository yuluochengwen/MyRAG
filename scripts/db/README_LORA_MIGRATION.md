# LoRA 微调系统数据库迁移指南

## 概述

本文档说明如何将 LoRA 微调训练和推理功能的数据库架构应用到现有的 MyRAG 系统。

## 迁移文件

- `lora_migration.sql` - 创建 LoRA 相关表和修改现有表的 SQL 脚本

## 迁移步骤

### 1. 备份数据库

在执行迁移前，请务必备份现有数据库：

```bash
mysqldump -u root -p myrag > myrag_backup_$(date +%Y%m%d_%H%M%S).sql
```

### 2. 执行迁移脚本

```bash
mysql -u root -p myrag < scripts/db/lora_migration.sql
```

或者在 MySQL 客户端中：

```sql
USE myrag;
SOURCE scripts/db/lora_migration.sql;
```

### 3. 验证迁移

检查表是否创建成功：

```sql
-- 检查 lora_models 表
DESCRIBE lora_models;

-- 检查 lora_training_jobs 表
DESCRIBE lora_training_jobs;

-- 检查 assistants 表是否添加了 lora_model_id 字段
DESCRIBE assistants;
```

## 新增表结构

### lora_models 表

存储 LoRA 微调模型的元数据。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| name | VARCHAR(255) | LoRA 模型名称 |
| base_model_id | INT | 基座模型 ID（可选） |
| base_model_name | VARCHAR(255) | 基座模型名称 |
| file_path | VARCHAR(500) | 权重文件路径 |
| file_size | BIGINT | 文件大小（字节） |
| training_job_id | INT | 关联的训练任务 ID |
| status | VARCHAR(50) | 状态：active, deleted |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### lora_training_jobs 表

存储 LoRA 训练任务的详细信息和进度。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| lora_model_id | INT | 关联的 LoRA 模型 ID |
| base_model_id | INT | 基座模型 ID（可选） |
| base_model_name | VARCHAR(255) | 基座模型名称 |
| dataset_path | VARCHAR(500) | 训练数据集路径 |
| dataset_format | VARCHAR(50) | 数据集格式：alpaca, conversation |
| training_mode | VARCHAR(50) | 训练模式：lora, qlora |
| parameters | JSON | 训练参数（rank, alpha, lr 等） |
| status | VARCHAR(50) | 状态：pending, training, completed, failed, cancelled |
| progress | FLOAT | 训练进度（0-100） |
| current_epoch | INT | 当前 epoch |
| total_epochs | INT | 总 epoch 数 |
| loss_history | JSON | Loss 历史记录 |
| log_file_path | VARCHAR(500) | 日志文件路径 |
| error_message | TEXT | 错误信息 |
| created_at | TIMESTAMP | 创建时间 |
| started_at | TIMESTAMP | 开始时间 |
| completed_at | TIMESTAMP | 完成时间 |

### assistants 表修改

添加 `lora_model_id` 字段以支持助手使用 LoRA 权重。

| 新增字段 | 类型 | 说明 |
|---------|------|------|
| lora_model_id | INT | 关联的 LoRA 模型 ID（可选） |

## 回滚迁移

如果需要回滚迁移，执行以下 SQL：

```sql
-- 删除外键约束
ALTER TABLE assistants DROP FOREIGN KEY IF EXISTS fk_assistants_lora_model;

-- 删除 assistants 表的 lora_model_id 字段
ALTER TABLE assistants DROP COLUMN IF EXISTS lora_model_id;

-- 删除索引
DROP INDEX IF EXISTS idx_lora_model ON assistants;

-- 删除 LoRA 相关表
DROP TABLE IF EXISTS lora_training_jobs;
DROP TABLE IF EXISTS lora_models;
```

## 注意事项

1. **外键约束**：`assistants.lora_model_id` 引用 `lora_models.id`，删除 LoRA 模型前需要先解除助手的关联
2. **级联删除**：删除 LoRA 模型时，相关的训练任务记录会保留（用于审计）
3. **索引优化**：已为常用查询字段添加索引，提升查询性能
4. **字符集**：所有表使用 UTF-8MB4 字符集，支持 emoji 和特殊字符

## 数据迁移后的验证

运行以下查询验证迁移成功：

```sql
-- 检查表是否存在
SELECT COUNT(*) FROM information_schema.tables 
WHERE table_schema = 'myrag' 
AND table_name IN ('lora_models', 'lora_training_jobs');

-- 检查外键约束
SELECT CONSTRAINT_NAME, TABLE_NAME, REFERENCED_TABLE_NAME 
FROM information_schema.KEY_COLUMN_USAGE 
WHERE TABLE_SCHEMA = 'myrag' 
AND CONSTRAINT_NAME LIKE '%lora%';

-- 检查索引
SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME 
FROM information_schema.STATISTICS 
WHERE TABLE_SCHEMA = 'myrag' 
AND TABLE_NAME IN ('lora_models', 'lora_training_jobs', 'assistants')
AND INDEX_NAME LIKE '%lora%';
```

## 故障排除

### 问题：外键约束创建失败

**原因**：可能是因为 `assistants` 表中已存在无效的 `lora_model_id` 值。

**解决方案**：
```sql
-- 将所有无效的 lora_model_id 设置为 NULL
UPDATE assistants SET lora_model_id = NULL 
WHERE lora_model_id NOT IN (SELECT id FROM lora_models);

-- 然后重新创建外键约束
ALTER TABLE assistants 
ADD CONSTRAINT fk_assistants_lora_model 
FOREIGN KEY (lora_model_id) REFERENCES lora_models(id) ON DELETE SET NULL;
```

### 问题：表已存在

**原因**：之前已经执行过迁移脚本。

**解决方案**：
```sql
-- 检查表结构是否正确
DESCRIBE lora_models;
DESCRIBE lora_training_jobs;

-- 如果需要重新创建，先删除表
DROP TABLE IF EXISTS lora_training_jobs;
DROP TABLE IF EXISTS lora_models;

-- 然后重新执行迁移脚本
```

## 联系支持

如果在迁移过程中遇到问题，请查看：
- 数据库日志：检查 MySQL 错误日志
- 应用日志：`data/logs/app.log`
- 训练日志：`data/logs/lora_training_*.log`
