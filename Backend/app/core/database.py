"""数据库连接池管理"""
import pymysql
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from contextlib import contextmanager
from typing import Generator, Optional
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self.pool: Optional[PooledDB] = None
        self._initialize_pool()
    
    def _initialize_pool(self):
        """初始化连接池"""
        try:
            db_config = settings.database
            
            self.pool = PooledDB(
                creator=pymysql,
                maxconnections=db_config.pool_size,
                mincached=2,
                maxcached=5,
                maxshared=3,
                blocking=True,
                maxusage=None,
                setsession=[],
                ping=1,
                host=db_config.host,
                port=db_config.port,
                user=db_config.user,
                password=db_config.password,
                database=db_config.database,
                charset='utf8mb4',
                cursorclass=DictCursor,
                autocommit=False
            )
            
            logger.info(f"数据库连接池初始化成功: {db_config.host}:{db_config.port}/{db_config.database}")
            
        except Exception as e:
            logger.error(f"数据库连接池初始化失败: {str(e)}")
            raise
    
    @contextmanager
    def get_connection(self) -> Generator:
        """
        获取数据库连接的上下文管理器
        
        使用示例:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users")
        """
        conn = None
        try:
            conn = self.pool.connection()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"数据库操作失败: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
    
    @contextmanager
    def get_cursor(self) -> Generator:
        """
        获取游标的上下文管理器
        
        使用示例:
            with db_manager.get_cursor() as cursor:
                cursor.execute("SELECT * FROM users")
                results = cursor.fetchall()
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()
    
    async def execute_query(self, query: str, params: tuple = None) -> list:
        """
        执行查询语句（异步包装）
        
        Args:
            query: SQL查询语句
            params: 查询参数
            
        Returns:
            查询结果列表
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, params or ())
            return cursor.fetchall()
    
    async def execute_update(self, query: str, params: tuple = None) -> int:
        """
        执行更新语句（INSERT, UPDATE, DELETE）
        
        Args:
            query: SQL语句
            params: 参数
            
        Returns:
            影响的行数
        """
        with self.get_cursor() as cursor:
            affected_rows = cursor.execute(query, params or ())
            return affected_rows
    
    async def execute_insert(self, query: str, params: tuple = None) -> int:
        """
        执行插入语句并返回插入的ID
        
        Args:
            query: INSERT语句
            params: 参数
            
        Returns:
            插入记录的ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, params or ())
                return cursor.lastrowid
            finally:
                cursor.close()
    
    def close(self):
        """关闭连接池"""
        if self.pool:
            self.pool.close()
            logger.info("数据库连接池已关闭")


# 全局数据库管理器实例
db_manager = DatabaseManager()


def get_db():
    """FastAPI依赖注入"""
    return db_manager
