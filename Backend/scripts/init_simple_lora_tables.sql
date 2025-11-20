-- 简化 LoRA 训练任务表
CREATE TABLE IF NOT EXISTS simple_lora_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_name VARCHAR(255) NOT NULL COMMENT '任务名称',
    base_model VARCHAR(255) NOT NULL COMMENT '基座模型名称',
    dataset_file VARCHAR(512) NOT NULL COMMENT '数据集文件路径',
    dataset_type VARCHAR(50) NOT NULL DEFAULT 'alpaca' COMMENT '数据集类型: alpaca, sharegpt',
    output_path VARCHAR(512) NOT NULL COMMENT 'LoRA 输出路径',
    training_params JSON COMMENT '训练参数（JSON格式）',
    
    status ENUM('pending', 'running', 'completed', 'failed') NOT NULL DEFAULT 'pending' COMMENT '任务状态',
    progress DECIMAL(5,2) DEFAULT 0.00 COMMENT '训练进度 (0-100)',
    current_epoch INT DEFAULT 0 COMMENT '当前训练轮次',
    message TEXT COMMENT '状态消息',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    started_at TIMESTAMP NULL COMMENT '开始时间',
    completed_at TIMESTAMP NULL COMMENT '完成时间',
    
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='简化 LoRA 训练任务表';
