-- 数据库初始化脚本

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS myrag DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE myrag;

-- 知识库表
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '知识库ID',
    name VARCHAR(255) NOT NULL UNIQUE COMMENT '知识库名称',
    description TEXT COMMENT '描述',
    embedding_model VARCHAR(255) NOT NULL DEFAULT 'paraphrase-multilingual-MiniLM-L12-v2' COMMENT '嵌入模型',
    embedding_provider VARCHAR(50) NOT NULL DEFAULT 'transformers' COMMENT '嵌入提供方: transformers, ollama',
    status VARCHAR(50) NOT NULL DEFAULT 'ready' COMMENT '状态: ready, processing, error',
    file_count INT NOT NULL DEFAULT 0 COMMENT '文件数量',
    chunk_count INT NOT NULL DEFAULT 0 COMMENT '文本块数量',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_name (name),
    INDEX idx_embedding_provider (embedding_provider),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库表';

-- 文件表
CREATE TABLE IF NOT EXISTS files (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '文件ID',
    kb_id INT NOT NULL COMMENT '知识库ID',
    filename VARCHAR(255) NOT NULL COMMENT '文件名（原始文件名）',
    file_type VARCHAR(50) NOT NULL COMMENT '文件类型: txt, pdf, docx, html, md',
    file_size BIGINT NOT NULL COMMENT '文件大小（字节）',
    file_hash VARCHAR(64) NOT NULL COMMENT '文件MD5哈希',
    storage_path VARCHAR(512) NOT NULL COMMENT '存储路径',
    chunk_count INT NOT NULL DEFAULT 0 COMMENT '文本块数量',
    status VARCHAR(50) NOT NULL DEFAULT 'uploaded' COMMENT '状态: uploaded, parsing, parsed, embedding, completed, error',
    error_message TEXT COMMENT '错误信息',
    processed_at TIMESTAMP NULL DEFAULT NULL COMMENT '处理完成时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    INDEX idx_kb_id (kb_id),
    INDEX idx_file_hash (file_hash),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文件表';

-- 文本块表
CREATE TABLE IF NOT EXISTS text_chunks (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '文本块ID',
    kb_id INT NOT NULL COMMENT '知识库ID',
    file_id INT NOT NULL COMMENT '文件ID',
    chunk_index INT NOT NULL COMMENT '块索引',
    content TEXT NOT NULL COMMENT '文本内容',
    vector_id VARCHAR(255) NOT NULL COMMENT '向量数据库中的ID',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    UNIQUE KEY uk_vector_id (vector_id),
    INDEX idx_kb_id (kb_id),
    INDEX idx_file_id (file_id),
    INDEX idx_chunk_index (chunk_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文本块表';

-- 处理日志表
CREATE TABLE IF NOT EXISTS process_logs (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '日志ID',
    kb_id INT NOT NULL COMMENT '知识库ID',
    file_id INT COMMENT '文件ID（可选）',
    operation VARCHAR(100) NOT NULL COMMENT '操作类型',
    status VARCHAR(50) NOT NULL COMMENT '状态',
    message TEXT COMMENT '消息',
    details JSON COMMENT '详细信息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL,
    INDEX idx_kb_id (kb_id),
    INDEX idx_file_id (file_id),
    INDEX idx_operation (operation),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='处理日志表';

-- 智能助手表
CREATE TABLE IF NOT EXISTS assistants (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '助手ID',
    name VARCHAR(255) NOT NULL COMMENT '助手名称',
    description TEXT COMMENT '助手描述',
    kb_ids VARCHAR(1000) COMMENT '关联知识库ID列表(逗号分隔,支持多个同embedding_model的KB)',
    embedding_model VARCHAR(255) NOT NULL COMMENT '嵌入模型(从KB继承或手动选择)',
    llm_model VARCHAR(255) NOT NULL COMMENT '大语言模型',
    llm_provider VARCHAR(50) NOT NULL DEFAULT 'local' COMMENT 'LLM提供方: local, openai, azure',
    system_prompt TEXT COMMENT '系统提示词(可选)',
    color_theme VARCHAR(50) DEFAULT 'blue' COMMENT '卡片配色主题: blue, purple, orange, green, pink',
    status VARCHAR(50) DEFAULT 'active' COMMENT '状态: active, inactive',
    conversation_count INT DEFAULT 0 COMMENT '对话次数统计',
    total_messages INT DEFAULT 0 COMMENT '总消息数统计',
    last_conversation_at TIMESTAMP NULL COMMENT '最后对话时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='智能助手表';

-- 对话表
CREATE TABLE IF NOT EXISTS conversations (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '对话ID',
    assistant_id INT NOT NULL COMMENT '助手ID',
    title VARCHAR(255) DEFAULT '新对话' COMMENT '对话标题',
    message_count INT DEFAULT 0 COMMENT '消息数量',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (assistant_id) REFERENCES assistants(id) ON DELETE CASCADE,
    INDEX idx_assistant_id (assistant_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='对话表';

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '消息ID',
    conversation_id INT NOT NULL COMMENT '对话ID',
    role VARCHAR(50) NOT NULL COMMENT '角色: user, assistant',
    content TEXT NOT NULL COMMENT '消息内容',
    sources JSON COMMENT 'RAG来源文档(仅assistant消息)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='消息表';

-- 示例助手数据(幂等插入,避免重复)
INSERT INTO assistants (name, description, kb_ids, embedding_model, llm_model, system_prompt, color_theme, conversation_count, total_messages, status) VALUES
('通用对话助手', '不绑定知识库的通用对话助手,可进行日常交流', NULL, 'all-MiniLM-L6-v2', 'DeepSeek-OCR-3B', '你是一个友好、专业的AI助手。请用简洁、准确的语言回答用户问题。', 'blue', 128, 256, 'active'),
('知识库问答助手', '基于知识库的专业问答助手,提供精准答案', '4,5', 'bert-base-chinese', 'DeepSeek-OCR-3B', '你是一个专业的知识库问答助手。请基于提供的参考资料,给出准确、详细的回答。如果资料中没有相关信息,请如实告知用户。', 'purple', 256, 512, 'active'),
('研发助手', '帮助研发人员解决技术问题', NULL, 'all-MiniLM-L6-v2', 'DeepSeek-OCR-3B', '你是一个专业的技术支持助手,擅长解答编程和开发问题。', 'orange', 89, 178, 'active')
ON DUPLICATE KEY UPDATE name=name;
