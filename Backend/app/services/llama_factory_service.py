"""LLaMA-Factory 进程管理服务"""
import subprocess
import psutil
import time
import signal
from pathlib import Path
from typing import Optional, Dict, Any
from app.core.database import db_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LlamaFactoryService:
    """LLaMA-Factory Web UI 服务管理"""
    
    def __init__(self):
        self.port = 7860
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / "llama_factory.log"
        
    def start(self) -> Dict[str, Any]:
        """启动 LLaMA-Factory Web UI"""
        # 检查是否已运行
        if self._is_running():
            status = self.get_status()
            return {
                "success": False,
                "message": "服务已在运行",
                "url": f"http://localhost:{self.port}",
                "pid": status.get("pid")
            }
        
        try:
            logger.info("正在启动 LLaMA-Factory Web UI...")
            
            # 构建启动命令
            cmd = [
                "llamafactory-cli",
                "webui",
                "--port", str(self.port),
            ]
            
            # 后台启动进程
            log_file_handle = open(self.log_file, 'w', encoding='utf-8')
            
            # Windows 需要特殊处理
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0
            
            process = subprocess.Popen(
                cmd,
                stdout=log_file_handle,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags
            )
            
            # 等待服务启动
            logger.info(f"进程已启动，PID: {process.pid}，等待服务就绪...")
            time.sleep(5)
            
            # 检查进程是否还在运行
            if not psutil.pid_exists(process.pid):
                log_file_handle.close()
                return {
                    "success": False,
                    "message": "服务启动失败，进程已终止，请查看日志"
                }
            
            # 保存到数据库
            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 先将所有旧记录标记为 stopped
                    cursor.execute("""
                        UPDATE llama_factory_service 
                        SET status = 'stopped', stopped_at = NOW()
                        WHERE status = 'running'
                    """)
                    
                    # 插入新记录
                    cursor.execute("""
                        INSERT INTO llama_factory_service 
                        (pid, port, status, started_at, log_file)
                        VALUES (%s, %s, 'running', NOW(), %s)
                    """, (process.pid, self.port, str(self.log_file)))
                    conn.commit()
            
            logger.info(f"✅ LLaMA-Factory 启动成功，PID: {process.pid}")
            return {
                "success": True,
                "message": "服务启动成功",
                "url": f"http://localhost:{self.port}",
                "pid": process.pid,
                "log_file": str(self.log_file)
            }
            
        except FileNotFoundError:
            logger.error("llamafactory-cli 命令未找到，请确认已安装 LLaMA-Factory")
            return {
                "success": False,
                "message": "llamafactory-cli 命令未找到，请先安装 LLaMA-Factory"
            }
        except Exception as e:
            logger.error(f"启动失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"启动失败: {str(e)}"
            }
    
    def stop(self) -> Dict[str, Any]:
        """停止服务"""
        try:
            # 从数据库获取运行中的服务
            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT pid, port FROM llama_factory_service 
                        WHERE status = 'running' 
                        ORDER BY started_at DESC 
                        LIMIT 1
                    """)
                    result = cursor.fetchone()
            
            if not result:
                return {
                    "success": False,
                    "message": "服务未运行"
                }
            
            pid = result['pid']
            
            # 终止进程
            try:
                process = psutil.Process(pid)
                
                # Windows 使用 terminate
                if hasattr(process, 'terminate'):
                    process.terminate()
                    
                    # 等待进程结束
                    try:
                        process.wait(timeout=10)
                    except psutil.TimeoutExpired:
                        # 强制杀死
                        process.kill()
                        
                logger.info(f"进程 {pid} 已终止")
                
            except psutil.NoSuchProcess:
                logger.warning(f"进程 {pid} 不存在")
            except Exception as e:
                logger.error(f"终止进程失败: {e}")
            
            # 更新数据库
            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE llama_factory_service 
                        SET status = 'stopped', stopped_at = NOW()
                        WHERE pid = %s
                    """, (pid,))
                    conn.commit()
            
            logger.info(f"✅ LLaMA-Factory 已停止，PID: {pid}")
            return {
                "success": True,
                "message": "服务已停止",
                "pid": pid
            }
            
        except Exception as e:
            logger.error(f"停止失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}"
            }
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT * FROM llama_factory_service 
                        WHERE status = 'running' 
                        ORDER BY started_at DESC 
                        LIMIT 1
                    """)
                    result = cursor.fetchone()
            
            if not result:
                return {
                    "running": False,
                    "message": "服务未运行"
                }
            
            pid = result['pid']
            
            # 检查进程是否真的存在
            try:
                if psutil.pid_exists(pid):
                    process = psutil.Process(pid)
                    
                    # 检查进程状态
                    if process.is_running():
                        return {
                            "running": True,
                            "pid": pid,
                            "port": result['port'],
                            "url": f"http://localhost:{result['port']}",
                            "started_at": result['started_at'].isoformat() if result['started_at'] else None,
                            "log_file": result['log_file']
                        }
                
                # 进程不存在，更新数据库
                with db_manager.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            UPDATE llama_factory_service 
                            SET status = 'stopped', stopped_at = NOW()
                            WHERE pid = %s
                        """, (pid,))
                        conn.commit()
                
                return {
                    "running": False,
                    "message": "进程已终止"
                }
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return {
                    "running": False,
                    "message": "进程不存在或无权限访问"
                }
                
        except Exception as e:
            logger.error(f"获取状态失败: {str(e)}", exc_info=True)
            return {
                "running": False,
                "message": f"获取状态失败: {str(e)}"
            }
    
    def _is_running(self) -> bool:
        """检查服务是否运行"""
        status = self.get_status()
        return status.get('running', False)


# 全局单例
_llama_factory_service: Optional[LlamaFactoryService] = None


def get_llama_factory_service() -> LlamaFactoryService:
    """获取 LLaMA-Factory 服务实例"""
    global _llama_factory_service
    if _llama_factory_service is None:
        _llama_factory_service = LlamaFactoryService()
    return _llama_factory_service
