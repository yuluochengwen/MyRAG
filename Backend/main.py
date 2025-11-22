"""FastAPI应用主入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from pathlib import Path
from app.core.config import settings
from app.core.database import db_manager
from app.api import kb_router, ws_router, assistant_router, conversation_router
from app.api.models import router as models_router
from app.api.lora_training import router as lora_router
from app.api.simple_lora import router as simple_lora_router
from app.utils.logger import get_logger

logger = get_logger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    logger.info("应用启动中...")
    logger.info(f"环境: {settings.app.env}")
    logger.info(f"数据库: {settings.database.host}:{settings.database.port}/{settings.database.database}")
    logger.info(f"文件上传目录: {settings.file.upload_dir}")
    logger.info(f"向量数据库: {settings.vector_db.persist_dir}")
    
    # 测试数据库连接
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                logger.info("数据库连接成功")
    except Exception as e:
        logger.error("="*50)
        logger.error("CRITICAL ERROR: Database Connection Failed")
        logger.error(f"Error Details: {str(e)}")
        logger.error("Please ensure MySQL is running and configuration is correct.")
        logger.error("="*50)
        # 不抛出异常，允许应用启动以便查看日志，但在使用相关功能时会报错
        # raise 
    
    yield
    
    # 关闭
    logger.info("应用关闭中...")


# 创建FastAPI应用
app = FastAPI(
    title="RAG知识库管理系统",
    description="基于FastAPI的RAG知识库管理后端API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(kb_router)
app.include_router(ws_router)
app.include_router(assistant_router)
app.include_router(conversation_router)
app.include_router(models_router)
app.include_router(lora_router)
app.include_router(simple_lora_router)

# 挂载静态文件
frontend_dir = BASE_DIR / "Frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
    logger.info(f"静态文件目录: {frontend_dir}")


@app.get("/")
async def root():
    """根路径 - 重定向到知识库管理页面"""
    return RedirectResponse(url="/static/knowledge-base.html")


@app.get("/model-management.html")
async def model_management_redirect():
    """模型管理页面 - 重定向到静态文件"""
    return RedirectResponse(url="/static/model-management.html")


@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        # 检查数据库连接
        with db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        log_level="info"
    )
