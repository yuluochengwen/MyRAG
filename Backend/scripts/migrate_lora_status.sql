-- 将 LoRA 模型状态从 deployed 改为 active
-- 删除 deploying 状态,因为激活是即时的

-- 修改枚举类型
ALTER TABLE lora_models 
MODIFY COLUMN status ENUM('discovered', 'active', 'failed') DEFAULT 'discovered' COMMENT '模型状态';

-- 更新现有的 deployed 状态为 active
UPDATE lora_models SET status = 'active' WHERE status = 'deployed';

-- 更新注释
ALTER TABLE lora_models 
MODIFY COLUMN is_deployed BOOLEAN DEFAULT FALSE COMMENT '是否已激活',
MODIFY COLUMN deployed_at TIMESTAMP NULL DEFAULT NULL COMMENT '激活时间';

-- 查询验证
SELECT id, model_name, status, is_deployed, deployed_at FROM lora_models;
