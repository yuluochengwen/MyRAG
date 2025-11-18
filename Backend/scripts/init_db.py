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
    
    # 读取SQL文件
    sql_file = os.path.join(os.path.dirname(__file__), 'init.sql')
    
    if not os.path.exists(sql_file):
        logger.error(f"SQL文件不存在: {sql_file}")
        return False
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # 智能分割SQL语句
    sql_statements = []
    current_statement = []
    in_statement = False
    
    for line in sql_content.split('\n'):
        stripped = line.strip()
        
        # 跳过注释行
        if stripped.startswith('--') or not stripped:
            continue
        
        # 跳过USE语句
        if stripped.upper().startswith('USE '):
            continue
        
        # 开始新语句
        if stripped.upper().startswith(('CREATE', 'INSERT', 'ALTER', 'DROP')):
            in_statement = True
        
        if in_statement:
            current_statement.append(line)
            
            # 语句结束(以分号结尾且不在括号内)
            if stripped.endswith(';'):
                stmt = '\n'.join(current_statement)
                # 简单检查: 确保CREATE TABLE的括号是闭合的
                if stmt.count('(') == stmt.count(')'):
                    sql_statements.append(stmt)
                    current_statement = []
                    in_statement = False
    
    logger.info(f"解析到 {len(sql_statements)} 条SQL语句")
    
    try:
        # 使用连接池
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 执行SQL语句
            for i, statement in enumerate(sql_statements, 1):
                try:
                    # 显示前50个字符用于调试
                    preview = statement.replace('\n', ' ').strip()[:80]
                    logger.info(f"[{i}/{len(sql_statements)}] {preview}...")
                    cursor.execute(statement)
                except Exception as e:
                    # 忽略重复插入错误(示例数据已存在)
                    if 'Duplicate entry' not in str(e):
                        logger.error(f"执行SQL失败: {str(e)}")
                        logger.error(f"语句前100字符: {statement[:200]}...")
                        raise
                    else:
                        logger.debug(f"跳过重复数据: {str(e)}")
            
            cursor.close()
        
        logger.info("数据库初始化完成！")
        return True
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        return False


if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
