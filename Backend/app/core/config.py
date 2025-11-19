"""应用配置模块"""
import os
import yaml
from pathlib import Path
from typing import List
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 项目根目录 (MyRAG/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


class DatabaseConfig(BaseModel):
    """数据库配置"""
    host: str = os.getenv("MYSQL_HOST", "localhost")
    port: int = int(os.getenv("MYSQL_PORT", "3306"))
    user: str = os.getenv("MYSQL_USER", "root")
    password: str = os.getenv("MYSQL_PASSWORD", "123456")
    database: str = os.getenv("MYSQL_DATABASE", "myrag")
    pool_size: int = 10
    max_overflow: int = 20
    pool_recycle: int = 3600
    echo: bool = False


class AppConfig(BaseModel):
    """应用配置"""
    name: str = "MyRAG"
    version: str = "1.0.0"
    env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = ["*"]


class FileConfig(BaseModel):
    """文件配置"""
    max_size_mb: int = 100
    total_max_size_mb: int = 500
    allowed_extensions: List[str] = [".txt", ".md", ".pdf", ".docx", ".html"]
    upload_dir: str = str(BASE_DIR / "KnowledgeBase")


class SemanticSplitConfig(BaseModel):
    """语义分割配置"""
    enabled: bool = True
    max_chunk_size: int = 800
    min_chunk_size: int = 200
    ollama_model: str = "deepseek-v3.1:671b-cloud"
    use_for_short_text: bool = True
    short_text_threshold: int = 5000


class TextProcessingConfig(BaseModel):
    """文本处理配置"""
    chunk_size: int = 800
    chunk_overlap: int = 100
    separators: List[str] = ["\n\n", "\n", "。", "！", "？"]
    semantic_split: SemanticSplitConfig = SemanticSplitConfig()


class VectorDBConfig(BaseModel):
    """向量数据库配置"""
    type: str = "chroma"
    persist_dir: str = str(BASE_DIR / "VectorDB")
    collection_name_prefix: str = "kb_"


class EmbeddingConfig(BaseModel):
    """嵌入模型配置"""
    provider: str = "transformers"  # 默认嵌入提供方
    default_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    model_dir: str = str(BASE_DIR / "Models" / "Embedding")
    batch_size: int = 32
    max_length: int = 512
    ollama: dict = {
        "base_url": "http://localhost:11434",
        "timeout": 30,
        "default_model": "nomic-embed-text"
    }
    
    class Config:
        protected_namespaces = ()  # 允许 model_ 开头的字段


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    file: str = str(BASE_DIR / "logs" / "app.log")
    max_bytes: int = 10485760
    backup_count: int = 5
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class WebSocketConfig(BaseModel):
    """WebSocket配置"""
    heartbeat_interval: int = 30
    max_connections: int = 100


class LLMConfig(BaseModel):
    """LLM配置"""
    default_provider: str = "transformers"  # transformers, openai, azure
    default_model: str = "DeepSeek-OCR-3B"  # 本地模型名称(3B更适合6GB显存)
    local_models_dir: str = str(BASE_DIR / "Models")  # 本地模型目录
    transformers_quantization: str = "int4"  # 量化方式: int4, int8, fp16
    transformers_max_memory: float = 5.5  # 最大显存使用(GB), RTX 3060 6GB建议5.5
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = "https://api.openai.com/v1"
    temperature: float = 0.7
    max_tokens: int = 512  # 降低默认值，CPU offload时生成速度慢


class Settings(BaseSettings):
    """全局配置"""
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    file: FileConfig = FileConfig()
    text_processing: TextProcessingConfig = TextProcessingConfig()
    vector_db: VectorDBConfig = VectorDBConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    logging: LoggingConfig = LoggingConfig()
    websocket: WebSocketConfig = WebSocketConfig()
    llm: LLMConfig = LLMConfig()

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # 忽略额外字段而不是禁止


def load_config() -> Settings:
    """
    加载配置
    
    从 YAML 配置文件合并配置项到默认设置
    配置文件路径: MyRAG/Backend/config.yaml
    """
    config_file = BASE_DIR / "Backend" / "config.yaml"
    
    if not config_file.exists():
        return Settings()
    
    with open(config_file, 'r', encoding='utf-8') as f:
        yaml_config = yaml.safe_load(f)
    
    if not yaml_config:
        return Settings()
    
    # 创建配置对象
    settings = Settings()
    
    # 合并 YAML 配置
    for key, value in yaml_config.items():
        if hasattr(settings, key) and isinstance(value, dict):
            config_obj = getattr(settings, key)
            for k, v in value.items():
                if hasattr(config_obj, k):
                    # 处理嵌套配置对象（如 semantic_split）
                    if isinstance(v, dict) and hasattr(config_obj, k):
                        nested_obj = getattr(config_obj, k)
                        if hasattr(nested_obj, '__dict__'):  # 确保是配置对象
                            for nested_k, nested_v in v.items():
                                if hasattr(nested_obj, nested_k):
                                    setattr(nested_obj, nested_k, nested_v)
                            continue
                    
                    # 处理路径配置:将相对路径转换为绝对路径
                    # 支持两种格式: "Models" 或 "../Models" (都相对于BASE_DIR)
                    if k in ['local_models_dir', 'upload_dir', 'persist_directory', 'model_dir', 'file']:
                        if isinstance(v, str) and not Path(v).is_absolute():
                            # 移除可能的"../"前缀,统一处理为相对于BASE_DIR
                            clean_path = v.replace('../', '')
                            v = str((BASE_DIR / clean_path).resolve())
                    setattr(config_obj, k, v)
    
    return settings


# 全局配置实例
settings = load_config()
