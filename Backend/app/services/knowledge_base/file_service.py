"""文件服务"""
import os
import hashlib
from typing import List, Optional, BinaryIO
from datetime import datetime
from app.core.database import DatabaseManager
from app.core.config import settings
from app.models.file import File
from app.utils.logger import get_logger
from app.utils.file_parser import get_file_parser
from app.utils.validators import validate_file_size

logger = get_logger(__name__)


class FileService:
    """文件服务"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.upload_dir = settings.file.upload_dir
        
        # 确保上传目录存在
        os.makedirs(self.upload_dir, exist_ok=True)
    
    async def save_file(
        self,
        file_content: BinaryIO,
        filename: str,
        kb_id: int,
        file_type: str
    ) -> Optional[File]:
        """
        保存文件到磁盘和数据库
        
        Args:
            file_content: 文件内容
            filename: 文件名
            kb_id: 知识库ID
            file_type: 文件类型
            
        Returns:
            文件对象
        """
        try:
            # 读取文件内容
            content = file_content.read()
            file_size = len(content)
            
            # 验证文件大小
            validate_file_size(file_size)
            
            # 清理文件名，防止路径遍历攻击
            from app.utils.validators import sanitize_path
            safe_filename = sanitize_path(filename)
            
            # 计算文件哈希
            file_hash = hashlib.md5(content).hexdigest()
            
            # 检查是否已存在
            existing = await self.get_file_by_hash(kb_id, file_hash)
            if existing:
                logger.warning(f"文件已存在: {filename}, hash={file_hash}")
                return existing
            
            # 生成存储路径: kb_{kb_id}/files/{file_hash}_{filename}
            kb_dir = os.path.join(self.upload_dir, f"kb_{kb_id}", "files")
            os.makedirs(kb_dir, exist_ok=True)
            
            storage_path = os.path.join(kb_dir, f"{file_hash}_{safe_filename}")
            
            # 保存文件
            with open(storage_path, 'wb') as f:
                f.write(content)
            
            # 保存到数据库
            sql = """
                INSERT INTO files 
                (kb_id, filename, file_type, file_size, file_hash, storage_path, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            file_id = await self.db.execute_insert(
                sql,
                (kb_id, safe_filename, file_type, file_size, file_hash, storage_path, 'uploaded')
            )
            
            if file_id:
                logger.info(f"文件保存成功: id={file_id}, filename={safe_filename} (original={filename})")
                return await self.get_file(file_id)
            
            return None
            
        except Exception as e:
            logger.error(f"保存文件失败: {str(e)}")
            raise
    
    async def parse_file(self, file_id: int) -> Optional[str]:
        """
        解析文件内容
        
        Args:
            file_id: 文件ID
            
        Returns:
            解析后的文本内容
        """
        try:
            file_obj = await self.get_file(file_id)
            if not file_obj:
                raise ValueError(f"文件不存在: {file_id}")
            
            # 更新状态为解析中
            await self.update_file_status(file_id, 'parsing')
            
            # 获取解析器
            parser = get_file_parser(file_obj.file_type)
            
            # 解析文件
            content = parser.parse(file_obj.storage_path)
            
            # 更新状态为已解析
            await self.update_file_status(file_id, 'parsed')
            
            logger.info(f"文件解析成功: id={file_id}, content_length={len(content)}")
            return content
            
        except Exception as e:
            logger.error(f"文件解析失败: {str(e)}")
            await self.update_file_status(file_id, 'error', str(e))
            raise
    
    async def get_file(self, file_id: int) -> Optional[File]:
        """
        获取文件信息
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件对象
        """
        try:
            sql = "SELECT * FROM files WHERE id = %s"
            result = await self.db.execute_query(sql, (file_id,))
            
            if result:
                return File.from_dict(result[0])
            
            return None
            
        except Exception as e:
            logger.error(f"获取文件失败: {str(e)}")
            raise
    
    async def get_file_by_hash(self, kb_id: int, file_hash: str) -> Optional[File]:
        """
        根据哈希获取文件
        
        Args:
            kb_id: 知识库ID
            file_hash: 文件哈希
            
        Returns:
            文件对象
        """
        try:
            sql = "SELECT * FROM files WHERE kb_id = %s AND file_hash = %s"
            result = await self.db.execute_query(sql, (kb_id, file_hash))
            
            if result:
                return File.from_dict(result[0])
            
            return None
            
        except Exception as e:
            logger.error(f"根据哈希获取文件失败: {str(e)}")
            raise
    
    async def list_files(self, kb_id: int) -> List[File]:
        """
        获取知识库的文件列表
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            文件列表
        """
        try:
            sql = """
                SELECT * FROM files
                WHERE kb_id = %s
                ORDER BY created_at DESC
            """
            
            results = await self.db.execute_query(sql, (kb_id,))
            
            return [File.from_dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"获取文件列表失败: {str(e)}")
            raise
    
    async def update_chunk_count(
        self,
        file_id: int,
        chunk_count: int
    ) -> bool:
        """
        更新文件的分块数量
        
        Args:
            file_id: 文件ID
            chunk_count: 分块数量
            
        Returns:
            是否成功
        """
        try:
            sql = """
                UPDATE files
                SET chunk_count = %s, updated_at = NOW()
                WHERE id = %s
            """
            
            rows_affected = await self.db.execute_update(
                sql,
                (chunk_count, file_id)
            )
            
            logger.info(f"文件分块数量更新成功: id={file_id}, chunk_count={chunk_count}")
            return rows_affected > 0
            
        except Exception as e:
            logger.error(f"更新文件分块数量失败: {str(e)}")
            raise
    
    async def update_file_status(
        self,
        file_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """
        更新文件状态
        
        Args:
            file_id: 文件ID
            status: 状态
            error_message: 错误消息
            
        Returns:
            是否成功
        """
        try:
            # 如果状态为completed,同时设置processed_at
            if status == 'completed':
                sql = """
                    UPDATE files
                    SET status = %s, error_message = %s, processed_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                """
            else:
                sql = """
                    UPDATE files
                    SET status = %s, error_message = %s, updated_at = NOW()
                    WHERE id = %s
                """
            
            rows_affected = await self.db.execute_update(
                sql,
                (status, error_message, file_id)
            )
            
            logger.info(f"文件状态更新成功: id={file_id}, status={status}")
            return rows_affected > 0
            
        except Exception as e:
            logger.error(f"更新文件状态失败: {str(e)}")
            raise
    
    async def delete_file(self, file_id: int) -> bool:
        """
        删除文件
        
        Args:
            file_id: 文件ID
            
        Returns:
            是否成功
        """
        try:
            file_obj = await self.get_file(file_id)
            if not file_obj:
                return False
            
            # 删除磁盘文件
            if os.path.exists(file_obj.storage_path):
                os.remove(file_obj.storage_path)
            
            # 删除数据库记录
            rows_affected = await self.db.execute_update(
                "DELETE FROM files WHERE id = %s",
                (file_id,)
            )
            
            logger.info(f"文件删除成功: id={file_id}")
            return rows_affected > 0
            
        except Exception as e:
            logger.error(f"删除文件失败: {str(e)}")
            raise
