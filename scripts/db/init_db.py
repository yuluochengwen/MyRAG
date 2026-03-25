"""数据库初始化脚本"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import db_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)


def init_database():
    """初始化数据库"""
    logger.info("开始初始化数据库...")

    def _parse_sql_statements(sql_content: str):
        """按分号切分 SQL 语句，跳过注释和 USE 语句。"""
        statements = []
        current = []

        for raw_line in sql_content.split('\n'):
            stripped = raw_line.strip()

            if not stripped or stripped.startswith('--'):
                continue

            if stripped.upper().startswith('USE '):
                continue

            current.append(raw_line)

            if stripped.endswith(';'):
                stmt = '\n'.join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []

        tail = '\n'.join(current).strip()
        if tail:
            statements.append(tail)

        return statements

    def _is_idempotent_ddl_error(error_text: str) -> bool:
        markers = [
            'Duplicate entry',
            'Duplicate column name',
            'Duplicate key name',
            'Duplicate foreign key constraint name',
            'already exists',
            'Can\'t create table',
            'ERROR 1050',
            'ERROR 1060',
            'ERROR 1061',
            'ERROR 1826'
        ]
        return any(m.lower() in error_text.lower() for m in markers)

    def _execute_sql_file(cursor, sql_path: str):
        if not os.path.exists(sql_path):
            logger.warning(f"SQL文件不存在，跳过: {sql_path}")
            return

        with open(sql_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        statements = _parse_sql_statements(sql_content)
        logger.info(f"文件 {os.path.basename(sql_path)} 解析到 {len(statements)} 条SQL语句")

        for i, statement in enumerate(statements, 1):
            try:
                preview = statement.replace('\n', ' ').strip()[:80]
                logger.info(f"[{i}/{len(statements)}] {preview}...")
                cursor.execute(statement)
            except Exception as e:
                if _is_idempotent_ddl_error(str(e)):
                    logger.debug(f"跳过幂等DDL错误: {str(e)}")
                    continue
                logger.error(f"执行SQL失败: {str(e)}")
                logger.error(f"语句前200字符: {statement[:200]}...")
                raise

    def _column_exists(cursor, table_name: str, column_name: str) -> bool:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            LIMIT 1
            """,
            (table_name, column_name)
        )
        return cursor.fetchone() is not None

    def _index_exists(cursor, table_name: str, index_name: str) -> bool:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            LIMIT 1
            """,
            (table_name, index_name)
        )
        return cursor.fetchone() is not None

    def _fk_exists(cursor, table_name: str, fk_name: str) -> bool:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND CONSTRAINT_NAME = %s
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
            LIMIT 1
            """,
            (table_name, fk_name)
        )
        return cursor.fetchone() is not None

    def _ensure_lora_schema(cursor):
        """将旧版 LoRA 字段升级到当前代码使用的新字段。"""
        if _column_exists(cursor, 'lora_models', 'model_name') and not _column_exists(cursor, 'lora_models', 'name'):
            cursor.execute("ALTER TABLE lora_models CHANGE COLUMN model_name name VARCHAR(255) NOT NULL COMMENT 'LoRA 模型名称'")

        if _column_exists(cursor, 'lora_models', 'base_model') and not _column_exists(cursor, 'lora_models', 'base_model_name'):
            cursor.execute("ALTER TABLE lora_models CHANGE COLUMN base_model base_model_name VARCHAR(255) NOT NULL COMMENT '基座模型名称'")

        if _column_exists(cursor, 'lora_models', 'model_path') and not _column_exists(cursor, 'lora_models', 'file_path'):
            cursor.execute("ALTER TABLE lora_models CHANGE COLUMN model_path file_path VARCHAR(500) NOT NULL COMMENT 'LoRA 权重文件路径'")

        if _column_exists(cursor, 'lora_models', 'file_size_mb') and not _column_exists(cursor, 'lora_models', 'file_size'):
            cursor.execute("ALTER TABLE lora_models ADD COLUMN file_size BIGINT NOT NULL DEFAULT 0 COMMENT '文件大小（字节）' AFTER file_path")
            cursor.execute("UPDATE lora_models SET file_size = CAST(IFNULL(file_size_mb, 0) * 1024 * 1024 AS UNSIGNED) WHERE file_size = 0")

        if not _column_exists(cursor, 'lora_models', 'training_job_id'):
            cursor.execute("ALTER TABLE lora_models ADD COLUMN training_job_id INT NULL COMMENT '关联的训练任务 ID' AFTER file_size")

        if not _column_exists(cursor, 'assistants', 'lora_model_id'):
            cursor.execute("ALTER TABLE assistants ADD COLUMN lora_model_id INT NULL COMMENT 'LoRA 模型 ID' AFTER llm_provider")

        if not _index_exists(cursor, 'assistants', 'idx_lora_model'):
            cursor.execute("CREATE INDEX idx_lora_model ON assistants(lora_model_id)")

        if not _fk_exists(cursor, 'assistants', 'fk_assistants_lora'):
            cursor.execute(
                "ALTER TABLE assistants ADD CONSTRAINT fk_assistants_lora "
                "FOREIGN KEY (lora_model_id) REFERENCES lora_models(id) ON DELETE SET NULL"
            )
    
    try:
        # 使用连接池
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # 先执行主初始化脚本
            init_sql = os.path.join(os.path.dirname(__file__), 'init.sql')
            _execute_sql_file(cursor, init_sql)

            # 执行 Python 级兜底迁移，防止旧字段残留
            _ensure_lora_schema(cursor)
            
            cursor.close()
        
        logger.info("数据库初始化完成！")
        return True
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        return False


if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
