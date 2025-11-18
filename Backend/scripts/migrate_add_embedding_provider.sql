-- 数据库迁移脚本：添加embedding_provider字段支持
-- 执行日期：2025-01-18
-- 用途：为knowledge_bases表添加embedding_provider字段，支持Ollama嵌入模型

USE myrag;

-- 检查字段是否已存在，如果不存在则添加
SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'myrag'
    AND TABLE_NAME = 'knowledge_bases'
    AND COLUMN_NAME = 'embedding_provider'
);

-- 如果字段不存在，则添加
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE knowledge_bases ADD COLUMN embedding_provider VARCHAR(50) NOT NULL DEFAULT ''transformers'' COMMENT ''嵌入提供方: transformers, ollama'' AFTER embedding_model',
    'SELECT ''字段embedding_provider已存在，跳过添加'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 添加索引（如果不存在）
SET @idx_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = 'myrag'
    AND TABLE_NAME = 'knowledge_bases'
    AND INDEX_NAME = 'idx_embedding_provider'
);

SET @sql = IF(
    @idx_exists = 0,
    'ALTER TABLE knowledge_bases ADD INDEX idx_embedding_provider (embedding_provider)',
    'SELECT ''索引idx_embedding_provider已存在，跳过添加'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 更新现有记录，将NULL值设置为默认值
UPDATE knowledge_bases 
SET embedding_provider = 'transformers' 
WHERE embedding_provider IS NULL OR embedding_provider = '';

-- 验证迁移结果
SELECT 
    COLUMN_NAME, 
    COLUMN_TYPE, 
    IS_NULLABLE, 
    COLUMN_DEFAULT, 
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'myrag'
AND TABLE_NAME = 'knowledge_bases'
AND COLUMN_NAME IN ('embedding_model', 'embedding_provider');

SELECT 
    '迁移完成！' AS status,
    COUNT(*) AS total_kb,
    SUM(CASE WHEN embedding_provider = 'transformers' THEN 1 ELSE 0 END) AS transformers_count,
    SUM(CASE WHEN embedding_provider = 'ollama' THEN 1 ELSE 0 END) AS ollama_count
FROM knowledge_bases;
