"""数据库迁移脚本：添加embedding_provider字段"""
import pymysql
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 数据库连接配置
DB_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'port': int(os.getenv('MYSQL_PORT', '3306')),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', '123456'),
    'database': os.getenv('MYSQL_DATABASE', 'myrag'),
    'charset': 'utf8mb4'
}

def run_migration():
    """执行数据库迁移"""
    try:
        # 连接数据库
        connection = pymysql.connect(**DB_CONFIG)
        cursor = connection.cursor()
        
        print("=" * 60)
        print("开始执行数据库迁移：添加embedding_provider字段")
        print("=" * 60)
        
        # 1. 检查字段是否已存在
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'myrag'
            AND TABLE_NAME = 'knowledge_bases'
            AND COLUMN_NAME = 'embedding_provider'
        """)
        
        col_exists = cursor.fetchone()[0]
        
        if col_exists > 0:
            print("✓ 字段 embedding_provider 已存在，跳过添加")
        else:
            print("→ 正在添加字段 embedding_provider...")
            cursor.execute("""
                ALTER TABLE knowledge_bases 
                ADD COLUMN embedding_provider VARCHAR(50) NOT NULL DEFAULT 'transformers' 
                COMMENT '嵌入提供方: transformers, ollama' 
                AFTER embedding_model
            """)
            connection.commit()
            print("✓ 字段 embedding_provider 添加成功")
        
        # 2. 添加索引
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = 'myrag'
            AND TABLE_NAME = 'knowledge_bases'
            AND INDEX_NAME = 'idx_embedding_provider'
        """)
        
        idx_exists = cursor.fetchone()[0]
        
        if idx_exists > 0:
            print("✓ 索引 idx_embedding_provider 已存在，跳过添加")
        else:
            print("→ 正在添加索引 idx_embedding_provider...")
            cursor.execute("""
                ALTER TABLE knowledge_bases 
                ADD INDEX idx_embedding_provider (embedding_provider)
            """)
            connection.commit()
            print("✓ 索引 idx_embedding_provider 添加成功")
        
        # 3. 更新现有记录
        print("→ 正在更新现有记录...")
        cursor.execute("""
            UPDATE knowledge_bases 
            SET embedding_provider = 'transformers' 
            WHERE embedding_provider IS NULL OR embedding_provider = ''
        """)
        connection.commit()
        affected_rows = cursor.rowcount
        print(f"✓ 已更新 {affected_rows} 条记录")
        
        # 4. 验证迁移结果
        print("\n" + "=" * 60)
        print("迁移结果验证")
        print("=" * 60)
        
        cursor.execute("""
            SELECT 
                COLUMN_NAME, 
                COLUMN_TYPE, 
                IS_NULLABLE, 
                COLUMN_DEFAULT, 
                COLUMN_COMMENT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'myrag'
            AND TABLE_NAME = 'knowledge_bases'
            AND COLUMN_NAME IN ('embedding_model', 'embedding_provider')
        """)
        
        columns = cursor.fetchall()
        for col in columns:
            print(f"\n字段: {col[0]}")
            print(f"  类型: {col[1]}")
            print(f"  允许NULL: {col[2]}")
            print(f"  默认值: {col[3]}")
            print(f"  注释: {col[4]}")
        
        cursor.execute("""
            SELECT 
                COUNT(*) AS total_kb,
                SUM(CASE WHEN embedding_provider = 'transformers' THEN 1 ELSE 0 END) AS transformers_count,
                SUM(CASE WHEN embedding_provider = 'ollama' THEN 1 ELSE 0 END) AS ollama_count
            FROM knowledge_bases
        """)
        
        stats = cursor.fetchone()
        print(f"\n知识库统计:")
        print(f"  总数: {stats[0]}")
        print(f"  Transformers: {stats[1]}")
        print(f"  Ollama: {stats[2]}")
        
        print("\n" + "=" * 60)
        print("✅ 数据库迁移完成！")
        print("=" * 60)
        
        cursor.close()
        connection.close()
        
        return True
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {str(e)}")
        return False

if __name__ == '__main__':
    success = run_migration()
    exit(0 if success else 1)
