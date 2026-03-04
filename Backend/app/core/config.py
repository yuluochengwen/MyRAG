"""应用配置模块"""
import os
import yaml
from pathlib import Path
from typing import List, Dict
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 项目根目录 (MyRAG/)
# 本地开发: config.py 上4层 → MyRAG/
# Docker 容器: 通过 PROJECT_ROOT 环境变量指定
BASE_DIR = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))


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
    allowed_extensions: List[str] = [".txt", ".md", ".pdf", ".docx", ".html", ".json"]
    upload_dir: str = str(BASE_DIR / "data" / "knowledge_base")


class SemanticSplitConfig(BaseModel):
    """语义分割配置"""
    enabled: bool = True
    max_chunk_size: int = 800
    min_chunk_size: int = 200
    ollama_model: str = "qwen2.5:7b"
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
    persist_dir: str = str(BASE_DIR / "data" / "vector_db")
    collection_name_prefix: str = "kb_"


class EmbeddingConfig(BaseModel):
    """嵌入模型配置"""
    provider: str = "transformers"  # 默认嵌入提供方
    default_model: str = "BERT-Base"
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
    file: str = str(BASE_DIR / "data" / "logs" / "app.log")
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
    default_model: str = "Qwen2.5-3B-Instruct"  # 默认模型（与config.yaml同步）
    local_models_dir: str = str(BASE_DIR / "Models")  # 本地模型目录
    transformers_quantization: str = "int4"  # 量化方式: int4, int8, fp16
    transformers_max_memory: float = 5.5  # 最大显存使用(GB), RTX 3060 6GB建议5.5
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = "https://api.openai.com/v1"
    temperature: float = 0.5
    max_tokens: int = 256  # 与config.yaml同步
    ollama: Dict[str, str | int] = {
        "base_url": "http://localhost:11434",
        "timeout": 120,
        "default_model": "deepseek-v3.1:671b-cloud"
    }


class Neo4jConfig(BaseModel):
    """Neo4j配置"""
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "myrag123"
    database: str = "neo4j"
    max_connection_lifetime: int = 3600
    max_connection_pool_size: int = 50
    connection_timeout: int = 30


class EntityExtractionConfig(BaseModel):
    """实体提取配置"""
    provider: str = "ollama"
    ollama_model: str = "qwen2.5:7b"
    temperature: float = 0.1
    timeout: int = 300
    max_tokens: int = 1024
    max_retries: int = 3
    batch_size: int = 5
    min_text_length: int = 50
    schema_version: str = "v2"
    enable_multilabel: bool = True
    keep_legacy_type_field: bool = True
    enable_unknown_bucket: bool = True
    unknown_entity_type: str = "Unclassified"
    unknown_relation_type: str = "related_to"
    llm_normalization_priority: bool = True
    alias_map: Dict[str, str] = {}
    valid_entity_types: List[str] = [
        "Person", "Organization", "Location", "Product", "Concept", "Event", "Date",
        "主体", "动作/行为", "属性/特征", "关联对象", "约束/规则", "Unclassified"
    ]
    valid_relation_types: List[str] = [
        "隶属/组成", "执行/触发", "描述/修饰", "约束/限制", "时空/因果",
        "works_at", "located_in", "part_of", "founded_by", "related_to"
    ]


class KnowledgeGraphConfig(BaseModel):
    """知识图谱配置"""
    enabled: bool = True
    provider: str = "neo4j"
    entity_extraction: EntityExtractionConfig = EntityExtractionConfig()
    max_hops: int = 2
    min_entity_length: int = 2
    enable_by_default: bool = False
    enable_fact_nodes: bool = False
    cleanup_fact_nodes_on_build: bool = True
    entity_types: List[str] = [
        "Person", "Organization", "Location", 
        "Product", "Concept", "Event", "Date"
    ]


class HybridRetrievalConfig(BaseModel):
    """混合检索配置"""
    vector_weight: float = 0.6
    graph_weight: float = 0.4
    enable_by_default: bool = False
    enable_query_normalization: bool = True
    enable_compound_entity_split: bool = True
    graph_min_results: int = 1
    diagnostics_enabled: bool = True
    max_fallback_candidates: int = 8
    enable_keyword_search: bool = True
    keyword_weight: float = 0.5
    enable_rrf_fusion: bool = True
    rrf_k: int = 60
    rrf_window_size: int = 50
    enable_light_rerank: bool = True
    rerank_alpha: float = 0.7
    query_stopwords: List[str] = [
        "的", "了", "和", "与", "及", "由", "是", "是什么", "怎么", "如何", "哪些", "哪几", "吗", "呢", "啊", "呀"
    ]
    compound_split_tokens: List[str] = [
        "的", "与", "和", "及", "由", "、", "/", "-", "_"
    ]


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
    neo4j: Neo4jConfig = Neo4jConfig()
    knowledge_graph: KnowledgeGraphConfig = KnowledgeGraphConfig()
    hybrid_retrieval: HybridRetrievalConfig = HybridRetrievalConfig()

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # 忽略额外字段而不是禁止


def load_config() -> Settings:
    """
    加载配置
    
    从 YAML 配置文件合并配置项到默认设置
    本地开发: MyRAG/Backend/config.yaml
    Docker: /app/config.yaml (Backend内容直接在WORKDIR)
    """
    config_file = BASE_DIR / "Backend" / "config.yaml"
    if not config_file.exists():
        # Docker 环境: Backend 内容直接在工作目录
        config_file = Path(__file__).resolve().parent.parent.parent / "config.yaml"
    
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
                    
                    # 兼容旧键名：vector_db.persist_directory -> vector_db.persist_dir
                    target_key = k
                    if key == 'vector_db' and k == 'persist_directory':
                        target_key = 'persist_dir'

                    # 处理路径配置:将相对路径转换为绝对路径
                    # 支持两种格式: "Models" 或 "../Models" (都相对于BASE_DIR)
                    if target_key in ['local_models_dir', 'upload_dir', 'persist_dir', 'model_dir', 'file', 'log_dir']:
                        if isinstance(v, str) and not Path(v).is_absolute():
                            # 移除可能的"../"前缀,统一处理为相对于BASE_DIR
                            clean_path = v.replace('../', '')
                            v = str((BASE_DIR / clean_path).resolve())
                    if hasattr(config_obj, target_key):
                        setattr(config_obj, target_key, v)
    
    return settings


# 全局配置实例
settings = load_config()
