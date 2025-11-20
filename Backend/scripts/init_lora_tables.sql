-- ============================================
-- LoRA 训练与管理功能数据库表
-- 创建时间: 2025-01-20
-- ============================================

-- 1. LoRA 模型管理表
CREATE TABLE IF NOT EXISTS lora_models (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(255) NOT NULL UNIQUE COMMENT 'LoRA模型名称',
    base_model VARCHAR(255) NOT NULL COMMENT '基座模型名称',
    model_path VARCHAR(500) NOT NULL COMMENT '模型文件路径',
    
    -- 状态管理
    status ENUM('discovered', 'deploying', 'deployed', 'failed') DEFAULT 'discovered' COMMENT '模型状态',
    is_deployed BOOLEAN DEFAULT FALSE COMMENT '是否已部署到Ollama',
    ollama_model_name VARCHAR(255) DEFAULT NULL COMMENT 'Ollama中的模型名称',
    
    -- 训练信息
    lora_rank INT DEFAULT NULL COMMENT 'LoRA rank参数',
    lora_alpha INT DEFAULT NULL COMMENT 'LoRA alpha参数',
    
    -- 元信息
    file_size_mb FLOAT DEFAULT 0 COMMENT '文件大小(MB)',
    description TEXT DEFAULT NULL COMMENT '模型描述',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    deployed_at TIMESTAMP NULL DEFAULT NULL COMMENT '部署时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 索引
    INDEX idx_status (status),
    INDEX idx_deployed (is_deployed),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LoRA模型管理表';

-- 2. LLaMA-Factory 服务管理表
CREATE TABLE IF NOT EXISTS llama_factory_service (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pid INT DEFAULT NULL COMMENT '服务进程PID',
    port INT DEFAULT 7860 COMMENT 'Web UI端口',
    status ENUM('running', 'stopped') DEFAULT 'stopped' COMMENT '服务状态',
    log_file VARCHAR(500) DEFAULT NULL COMMENT '日志文件路径',
    
    -- 时间戳
    started_at TIMESTAMP NULL DEFAULT NULL COMMENT '启动时间',
    stopped_at TIMESTAMP NULL DEFAULT NULL COMMENT '停止时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    -- 索引
    INDEX idx_status (status),
    INDEX idx_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLaMA-Factory服务管理表';

-- 3. 修改 assistants 表（添加 LoRA 模型关联）
ALTER TABLE assistants 
ADD COLUMN lora_model_id INT DEFAULT NULL COMMENT 'LoRA模型ID' AFTER llm_model,
ADD CONSTRAINT fk_assistant_lora 
    FOREIGN KEY (lora_model_id) 
    REFERENCES lora_models(id) 
    ON DELETE SET NULL;

-- 添加索引
ALTER TABLE assistants ADD INDEX idx_lora_model (lora_model_id);

-- ============================================
-- 初始化数据（可选）
-- ============================================

-- 插入初始服务状态记录
INSERT INTO llama_factory_service (status, port) 
VALUES ('stopped', 7860)
ON DUPLICATE KEY UPDATE status='stopped';

-- ============================================
-- 查询示例
-- ============================================

-- 查看所有 LoRA 模型
-- SELECT * FROM lora_models ORDER BY created_at DESC;

-- 查看已部署的 LoRA 模型
-- SELECT * FROM lora_models WHERE is_deployed = TRUE;

-- 查看服务状态
-- SELECT * FROM llama_factory_service ORDER BY started_at DESC LIMIT 1;

-- 查看助手绑定的 LoRA 模型
-- SELECT 
--     a.id,
--     a.name AS assistant_name,
--     a.llm_model,
--     l.model_name AS lora_name,
--     l.ollama_model_name,
--     l.status AS lora_status
-- FROM assistants a
-- LEFT JOIN lora_models l ON a.lora_model_id = l.id;
