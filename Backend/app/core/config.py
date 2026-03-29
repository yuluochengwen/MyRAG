"""应用配置模块"""
import os
import yaml
from pathlib import Path
from typing import List, Dict
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 项目根目录 (MyRAG/)
# 本地开发: config.py 上4层 → MyRAG/
# Docker 容器: 通过 PROJECT_ROOT 环境变量指定
BASE_DIR = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))
BACKEND_ENV_FILE = BASE_DIR / "Backend" / ".env"

# 加载环境变量（优先使用 Backend/.env，兼容 Docker 场景）
if BACKEND_ENV_FILE.exists():
    load_dotenv(dotenv_path=str(BACKEND_ENV_FILE), override=False)
else:
    # Docker 或特殊目录下兜底
    load_dotenv(dotenv_path=str(BASE_DIR / ".env"), override=False)


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
    enabled: bool = False
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
    split_profiles: Dict[str, Dict[str, int]] = {
        "text": {"chunk_size": 750, "chunk_overlap": 120},
        "code": {"chunk_size": 600, "chunk_overlap": 100},
        "html": {"chunk_size": 700, "chunk_overlap": 120},
        "json": {"chunk_size": 650, "chunk_overlap": 100},
        "markdown": {"chunk_size": 700, "chunk_overlap": 120}
    }
    hard_sentence_split_enabled: bool = True
    hard_sentence_max_length: int = 280
    split_quality_monitoring_enabled: bool = True
    split_quality_metrics_file: str = str(BASE_DIR / "data" / "logs" / "split_metrics.jsonl")
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
    vector_cache_size: int = 5000
    enable_e5_prefix: bool = True
    ollama: dict = {
        "base_url": "http://localhost:11434",
        "timeout": 30,
        "default_model": "nomic-embed-text",
        "max_workers": 4
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
    transformers_generation_timeout_seconds: int = 480
    transformers_assumed_tokens_per_second: float = 5.0
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
    provider: str = "deepseek"
    ollama_model: str = "qwen2.5:7b"
    deepseek_model: str = "deepseek-chat"
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    zai_model: str = "glm-4.7-flash"
    zai_api_key: str = os.getenv("ZAI_API_KEY", os.getenv("ZHIPU_API_KEY", ""))
    zai_base_url: str = os.getenv("ZAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    temperature: float = 0.1
    timeout: int = 300
    max_tokens: int = 2048
    max_retries: int = 3
    max_entities_per_chunk: int = 40
    max_triples_per_chunk: int = 60
    enable_json_repair: bool = True
    json_repair_max_tokens: int = 1200
    batch_size: int = 5
    min_concurrency: int = 2
    max_concurrency: int = 10
    adaptive_concurrency_enabled: bool = True
    target_latency_ms: int = 2500
    timeout_step_seconds: int = 30
    queue_batch_size: int = 24
    min_text_length: int = 50
    max_text_length: int = 9000
    layered_extraction_enabled: bool = True
    layer_window_chars: int = 3200
    layer_overlap_chars: int = 300
    schema_version: str = "v2"
    prompt_version: str = "glm47-er-v1"
    enable_multilabel: bool = True
    keep_legacy_type_field: bool = True
    enable_unknown_bucket: bool = True
    enable_second_pass_reclassify: bool = True
    reclassify_batch_limit: int = 80
    extraction_cache_enabled: bool = True
    extraction_cache_file: str = str(BASE_DIR / "data" / "logs" / "graph_extraction_cache.jsonl")
    extraction_cache_ttl_hours: int = 168
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
    idempotent_ingest_enabled: bool = True
    rollback_on_failure: bool = True
    run_metrics_file: str = str(BASE_DIR / "data" / "logs" / "graph_build_metrics.jsonl")
    entity_types: List[str] = [
        "Person", "Organization", "Location", 
        "Product", "Concept", "Event", "Date"
    ]


class HybridRetrievalConfig(BaseModel):
    """混合检索配置"""
    vector_weight: float = 0.6
    graph_weight: float = 0.4
    keyword_weight: float = 0.5
    enable_by_default: bool = False
    enable_query_normalization: bool = True
    enable_compound_entity_split: bool = True
    graph_min_results: int = 1
    graph_min_quality_score: float = 0.12
    diagnostics_enabled: bool = True
    max_fallback_candidates: int = 8
    enable_keyword_search: bool = True
    keyword_candidate_factor: int = 8
    keyword_min_candidates: int = 60
    keyword_use_fulltext_first: bool = True
    keyword_score_power: float = 1.0

    enable_vector_query_rewrite: bool = True
    vector_query_max_variants: int = 3
    vector_fusion_method: str = "rrf"  # rrf|max

    adaptive_recall_enabled: bool = True
    adaptive_recall_min_factor: float = 1.0
    adaptive_recall_max_factor: float = 1.8

    enable_rrf_fusion: bool = True
    rrf_k: int = 60
    rrf_window_size: int = 50

    normalize_fusion_scores: bool = True
    enable_light_rerank: bool = True
    rerank_alpha: float = 0.7

    graph_direct_base_score: float = 0.82
    graph_hop_base_score: float = 0.62
    graph_confidence_weight: float = 0.22
    graph_evidence_weight: float = 0.16
    graph_mention_weight: float = 0.08
    graph_hop_decay: float = 0.25
    graph_match_stage_weights: Dict[str, float] = {
        "exact": 1.0,
        "normalized": 0.97,
        "split": 0.92,
        "code_contains": 0.84
    }

    chat_top_k: int = 10
    chat_context_max_results: int = 10
    chat_min_similarity: float = 0.12
    chat_graph_min_similarity: float = 0.1
    chat_graph_min_confidence: float = 0.35

    multi_kb_dedup_enabled: bool = True
    multi_kb_max_per_kb: int = 4
    multi_kb_max_same_source_ratio: float = 0.8

    monitoring_enabled: bool = True
    hybrid_metrics_log_file: str = str(BASE_DIR / "data" / "logs" / "hybrid_retrieval_metrics.jsonl")

    query_stopwords: List[str] = [
        "的", "了", "和", "与", "及", "由", "是", "是什么", "怎么", "如何", "哪些", "哪几", "吗", "呢", "啊", "呀"
    ]
    compound_split_tokens: List[str] = [
        "的", "与", "和", "及", "由", "、", "/", "-", "_"
    ]


class VectorRetrievalConfig(BaseModel):
    """传统向量RAG检索优化配置"""
    enable_two_stage: bool = True
    recall_factor: int = 8
    min_recall_k: int = 30
    max_recall_k: int = 120

    enable_dynamic_threshold: bool = True
    base_score_threshold: float = 0.2
    relative_margin: float = 0.08
    min_keep_results: int = 3

    enable_light_rerank: bool = True
    rerank_alpha: float = 0.75

    enable_mmr: bool = True
    mmr_lambda: float = 0.7

    enable_cluster_dedup: bool = True
    cluster_adjacent_window: int = 1
    max_chunks_per_cluster: int = 3
    max_clusters_per_file: int = 2

    enable_query_rewrite: bool = True
    query_rewrite_max_variants: int = 3
    query_stopwords: List[str] = [
        "的", "了", "和", "与", "及", "由", "是", "是什么", "怎么", "如何", "哪些", "哪几", "吗", "呢"
    ]

    enable_multi_query_fusion: bool = True
    fusion_method: str = "rrf"  # rrf|max
    rrf_k: int = 60

    enable_cross_encoder_rerank: bool = False
    cross_encoder_model: str = "BAAI/bge-reranker-base"
    cross_encoder_top_n: int = 20
    cross_encoder_alpha: float = 0.7

    monitoring_enabled: bool = True
    metrics_log_file: str = str(BASE_DIR / "data" / "logs" / "retrieval_metrics.jsonl")


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
    vector_retrieval: VectorRetrievalConfig = VectorRetrievalConfig()

    class Config:
        env_file = str(BACKEND_ENV_FILE)
        case_sensitive = False
        extra = "ignore"  # 忽略额外字段而不是禁止


def load_config() -> Settings:
    """
    加载配置
    
    从 YAML 配置文件合并配置项到默认设置
    支持多环境配置:
    - base.yaml: 基础配置
    - development.yaml / production.yaml: 环境特定配置
    - retrieval.yaml: 检索配置
    
    本地开发: MyRAG/Backend/config/
    Docker: /app/config/ (Backend内容直接在WORKDIR)
    """
    # 确定配置目录
    config_dir = BASE_DIR / "Backend" / "config"
    if not config_dir.exists():
        # Docker 环境: Backend 内容直接在工作目录
        config_dir = Path(__file__).resolve().parent.parent.parent / "config"
    
    # 确定环境
    env = os.getenv("APP_ENV", "development")
    
    # 配置文件列表（按优先级顺序）
    config_files = [
        config_dir / "base.yaml",
        config_dir / "retrieval.yaml",
        config_dir / f"{env}.yaml"
    ]
    
    # 合并所有配置文件
    merged_config = {}
    for config_file in config_files:
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    # 深度合并配置
                    for key, value in file_config.items():
                        if key in merged_config and isinstance(merged_config[key], dict) and isinstance(value, dict):
                            merged_config[key].update(value)
                        else:
                            merged_config[key] = value
    
    # 如果没有找到任何配置文件，尝试使用旧的config.yaml
    if not merged_config:
        config_file = BASE_DIR / "Backend" / "config.yaml"
        if not config_file.exists():
            config_file = Path(__file__).resolve().parent.parent.parent / "config.yaml"
        
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                merged_config = yaml.safe_load(f) or {}
    
    # 创建配置对象
    settings = Settings()
    
    # 合并配置
    for key, value in merged_config.items():
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
                    if target_key in ['local_models_dir', 'upload_dir', 'persist_dir', 'model_dir', 'file', 'log_dir', 'metrics_log_file', 'split_quality_metrics_file', 'extraction_cache_file', 'run_metrics_file', 'hybrid_metrics_log_file']:
                        if isinstance(v, str) and not Path(v).is_absolute():
                            clean_path = v.replace('../', '')
                            v = str((BASE_DIR / clean_path).resolve())
                    if hasattr(config_obj, target_key):
                        setattr(config_obj, target_key, v)
    
    # 设置环境
    settings.app.env = env
    
    return settings


# 全局配置实例
settings = load_config()
