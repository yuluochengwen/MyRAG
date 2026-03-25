-- LoRA 微调训练和推理系统 - 数据库迁移脚本
-- 创建日期: 2024-01-15

USE myrag;

-- LoRA 模型表
CREATE TABLE IF NOT EXISTS lora_models (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'LoRA 模型ID',
    name VARCHAR(255) NOT NULL UNIQUE COMMENT 'LoRA 模型名称',
    base_model_id INT COMMENT '基座模型 ID（预留字段，可关联 models 表）',
    base_model_name VARCHAR(255) NOT NULL COMMENT '基座模型名称',
    file_path VARCHAR(500) NOT NULL COMMENT 'LoRA 权重文件路径',
    file_size BIGINT NOT NULL COMMENT '文件大小（字节）',
    training_job_id INT COMMENT '关联的训练任务 ID',
    status VARCHAR(50) DEFAULT 'active' COMMENT '状态: active, deleted',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_base_model (base_model_name),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='LoRA 模型表';

-- LoRA 训练任务表
CREATE TABLE IF NOT EXISTS lora_training_jobs (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '训练任务ID',
    lora_model_id INT COMMENT '训练完成后的 LoRA 模型 ID',
    base_model_id INT COMMENT '基座模型 ID（预留字段）',
    base_model_name VARCHAR(255) NOT NULL COMMENT '基座模型名称',
    dataset_path VARCHAR(500) NOT NULL COMMENT '训练数据集路径',
    dataset_format VARCHAR(50) NOT NULL COMMENT '数据格式: alpaca, conversation',
    training_mode VARCHAR(50) NOT NULL COMMENT '训练模式: lora, qlora',
    parameters JSON NOT NULL COMMENT '训练参数配置',
    status VARCHAR(50) NOT NULL COMMENT '状态: pending, training, completed, failed, cancelled',
    progress FLOAT DEFAULT 0 COMMENT '训练进度 0-100',
    current_epoch INT DEFAULT 0 COMMENT '当前 epoch',
    total_epochs INT NOT NULL COMMENT '总 epochs',
    loss_history JSON COMMENT 'Loss 值历史记录',
    log_file_path VARCHAR(500) COMMENT '日志文件路径',
    error_message TEXT COMMENT '错误信息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    started_at TIMESTAMP NULL COMMENT '开始训练时间',
    completed_at TIMESTAMP NULL COMMENT '完成时间',
    
    INDEX idx_status (status),
    INDEX idx_base_model (base_model_name),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (lora_model_id) REFERENCES lora_models(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='LoRA 训练任务表';

-- 修改 assistants 表添加 LoRA 支持
ALTER TABLE assistants 
ADD COLUMN IF NOT EXISTS lora_model_id INT NULL COMMENT 'LoRA 模型 ID' AFTER llm_provider;

-- 添加外键约束（如果不存在）
SET @constraint_exists = (
    SELECT COUNT(*) 
    FROM information_schema.TABLE_CONSTRAINTS 
    WHERE CONSTRAINT_SCHEMA = 'myrag' 
    AND TABLE_NAME = 'assistants' 
    AND CONSTRAINT_NAME = 'fk_assistants_lora'
);

SET @sql = IF(@constraint_exists = 0,
    'ALTER TABLE assistants ADD CONSTRAINT fk_assistants_lora FOREIGN KEY (lora_model_id) REFERENCES lora_models(id) ON DELETE SET NULL',
    'SELECT "外键约束已存在" AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 创建索引（如果不存在）
SET @index_exists = (
    SELECT COUNT(*) 
    FROM information_schema.STATISTICS 
    WHERE TABLE_SCHEMA = 'myrag' 
    AND TABLE_NAME = 'assistants' 
    AND INDEX_NAME = 'idx_lora_model'
);

SET @sql = IF(@index_exists = 0,
    'CREATE INDEX idx_lora_model ON assistants(lora_model_id)',
    'SELECT "索引已存在" AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 完成提示
SELECT 'LoRA 数据库迁移完成！' AS message;
