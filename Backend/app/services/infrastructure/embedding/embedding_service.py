"""嵌入模型服务"""
import hashlib
import os
from collections import OrderedDict
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Tuple
from app.core.config import settings
from app.utils.logger import get_logger

if TYPE_CHECKING:
    import torch
    from sentence_transformers import SentenceTransformer

logger = get_logger(__name__)

# 延迟导入避免循环依赖
_ollama_service = None

def get_ollama_service():
    """获取Ollama服务实例（延迟导入）"""
    global _ollama_service
    if _ollama_service is None:
        from app.services.infrastructure.embedding.ollama_embedding_service import get_ollama_embedding_service
        _ollama_service = get_ollama_embedding_service()
    return _ollama_service


class EmbeddingService:
    """嵌入模型服务"""
    
    def __init__(self):
        self.models = {}  # 模型缓存
        self.device = self._get_device()
        self.model_dir = settings.embedding.model_dir
        self.default_batch_size = max(1, int(getattr(settings.embedding, 'batch_size', 32) or 32))
        self.max_length = max(1, int(getattr(settings.embedding, 'max_length', 512) or 512))
        self.vector_cache_size = max(0, int(getattr(settings.embedding, 'vector_cache_size', 5000) or 5000))
        self._vector_cache: OrderedDict[str, List[float]] = OrderedDict()
        
        # 确保模型目录存在
        os.makedirs(self.model_dir, exist_ok=True)
        
        logger.info(
            f"嵌入服务初始化: device={self.device}, batch_size={self.default_batch_size}, "
            f"max_length={self.max_length}, vector_cache_size={self.vector_cache_size}"
        )

    def _build_cache_key(self, provider: str, model_name: str, text: str) -> str:
        digest = hashlib.sha1(text.encode('utf-8')).hexdigest()
        return f"{provider}::{model_name}::{digest}"

    def _needs_e5_prefix(self, model_name: str) -> bool:
        return bool(getattr(settings.embedding, 'enable_e5_prefix', True)) and 'e5' in (model_name or '').lower()

    def _prepare_texts_for_model(
        self,
        texts: List[str],
        model_name: str,
        text_role: str
    ) -> List[str]:
        if not texts:
            return []

        if not self._needs_e5_prefix(model_name):
            return texts

        if text_role == 'query':
            return [f"query: {text}" for text in texts]
        return [f"passage: {text}" for text in texts]

    def _cache_get(self, key: str) -> Optional[List[float]]:
        cached = self._vector_cache.get(key)
        if cached is None:
            return None
        self._vector_cache.move_to_end(key)
        return cached

    def _cache_set(self, key: str, embedding: List[float]) -> None:
        if self.vector_cache_size <= 0:
            return
        self._vector_cache[key] = embedding
        self._vector_cache.move_to_end(key)
        while len(self._vector_cache) > self.vector_cache_size:
            self._vector_cache.popitem(last=False)
    
    def _get_device(self) -> str:
        """获取可用设备（延迟导入torch）"""
        import torch
        
        if torch.cuda.is_available():
            return 'cuda'
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return 'mps'
        else:
            return 'cpu'
    
    def load_model(self, model_name: str) -> 'SentenceTransformer':
        """
        加载嵌入模型
        
        Args:
            model_name: 模型名称
            
        Returns:
            模型实例
        """
        from sentence_transformers import SentenceTransformer
        
        if model_name in self.models:
            logger.debug(f"使用缓存的模型: {model_name}")
            return self.models[model_name]
        
        try:
            logger.info(f"加载嵌入模型: {model_name}")
            
            # 模型路径
            model_path = os.path.join(self.model_dir, model_name)
            
            # 如果本地存在则加载本地，否则从HuggingFace下载
            if os.path.exists(model_path):
                model = SentenceTransformer(model_path, device=self.device)
                logger.info(f"从本地加载模型: {model_path}")
            else:
                model = SentenceTransformer(model_name, device=self.device)
                # 保存到本地
                model.save(model_path)
                logger.info(f"从HuggingFace下载并保存模型: {model_path}")
            
            # 缓存模型
            self.models[model_name] = model
            
            return model
            
        except Exception as e:
            logger.error(f"加载模型失败: {str(e)}")
            raise
    
    def encode(
        self,
        texts: List[str],
        model_name: str,
        provider: str = "transformers",
        batch_size: Optional[int] = None,
        show_progress: bool = False,
        text_role: str = "document"
    ) -> List[List[float]]:
        """
        将文本编码为向量（支持多provider）
        
        Args:
            texts: 文本列表
            model_name: 模型名称
            provider: 嵌入提供方，transformers或ollama，默认transformers
            batch_size: 批次大小
            show_progress: 是否显示进度
            
        Returns:
            向量列表
        """
        try:
            if not texts:
                return []
            
            effective_batch_size = max(1, int(batch_size or self.default_batch_size))

            logger.info(
                f"编码文本: count={len(texts)}, model={model_name}, provider={provider}, "
                f"batch_size={effective_batch_size}"
            )
            
            # 根据provider路由到不同的实现
            if provider == "ollama":
                ollama_service = get_ollama_service()
                return ollama_service.encode(texts, model_name, effective_batch_size, show_progress)
            else:
                # 默认使用transformers
                prepared_texts = self._prepare_texts_for_model(texts, model_name, text_role)
                return self._encode_with_transformers(prepared_texts, model_name, effective_batch_size, show_progress)
            
        except Exception as e:
            logger.error(f"文本编码失败: {str(e)}")
            raise
    
    def _encode_with_transformers(
        self,
        texts: List[str],
        model_name: str,
        batch_size: int = 32,
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        使用Transformers编码文本
        
        Args:
            texts: 文本列表
            model_name: 模型名称
            batch_size: 批次大小
            show_progress: 是否显示进度
            
        Returns:
            向量列表（已归一化）
        """
        import torch
        
        model = self.load_model(model_name)
        model.max_seq_length = self.max_length

        current_batch_size = max(1, int(batch_size or self.default_batch_size))
        last_error: Optional[Exception] = None

        while current_batch_size >= 1:
            try:
                embeddings = model.encode(
                    texts,
                    batch_size=current_batch_size,
                    show_progress_bar=show_progress,
                    convert_to_numpy=True,
                    normalize_embeddings=True
                )
                embeddings_list = embeddings.tolist()

                logger.info(
                    f"Transformers编码完成: vectors={len(embeddings_list)}, "
                    f"dimension={len(embeddings_list[0]) if embeddings_list else 0}, "
                    f"batch_size={current_batch_size}, max_seq_length={model.max_seq_length}"
                )

                return embeddings_list

            except RuntimeError as error:
                last_error = error
                error_text = str(error).lower()
                is_oom = "out of memory" in error_text and "cuda" in error_text

                if is_oom and current_batch_size > 1:
                    next_batch_size = max(1, current_batch_size // 2)
                    logger.warning(
                        "Transformers编码出现CUDA OOM，自动降级batch_size: %s -> %s",
                        current_batch_size,
                        next_batch_size
                    )
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    current_batch_size = next_batch_size
                    continue

                raise
        
        if last_error:
            raise last_error
        return []

    def encode_with_cache(
        self,
        texts: List[str],
        model_name: str,
        provider: str = "transformers",
        batch_size: Optional[int] = None,
        show_progress: bool = False,
        text_role: str = "document"
    ) -> Tuple[List[List[float]], Dict[str, Any]]:
        """编码文本并复用内存缓存，避免重复向量化。"""
        if not texts:
            return [], {
                "total": 0,
                "cache_hit": 0,
                "cache_miss": 0,
                "unique_miss": 0,
                "hit_rate": 0.0
            }

        embeddings: List[Optional[List[float]]] = [None] * len(texts)
        miss_index_by_key: Dict[str, List[int]] = {}
        miss_text_by_key: Dict[str, str] = {}
        cache_hit = 0

        for index, text in enumerate(texts):
            current_text = text or ""
            cache_key = self._build_cache_key(provider, model_name, current_text)
            cached = self._cache_get(cache_key)
            if cached is not None:
                embeddings[index] = cached
                cache_hit += 1
                continue

            miss_index_by_key.setdefault(cache_key, []).append(index)
            if cache_key not in miss_text_by_key:
                miss_text_by_key[cache_key] = current_text

        if miss_text_by_key:
            miss_keys = list(miss_text_by_key.keys())
            miss_texts = [miss_text_by_key[key] for key in miss_keys]
            miss_vectors = self.encode(
                miss_texts,
                model_name=model_name,
                provider=provider,
                batch_size=batch_size,
                show_progress=show_progress,
                text_role=text_role
            )

            for key, vector in zip(miss_keys, miss_vectors):
                self._cache_set(key, vector)
                for target_index in miss_index_by_key.get(key, []):
                    embeddings[target_index] = vector

        resolved_embeddings = [vector or [] for vector in embeddings]
        cache_miss = len(texts) - cache_hit

        return resolved_embeddings, {
            "total": len(texts),
            "cache_hit": cache_hit,
            "cache_miss": cache_miss,
            "unique_miss": len(miss_text_by_key),
            "hit_rate": round(cache_hit / len(texts), 4)
        }
    
    def encode_single(
        self,
        text: str,
        model_name: str,
        provider: str = "transformers",
        text_role: str = "query"
    ) -> List[float]:
        """
        编码单个文本
        
        Args:
            text: 文本
            model_name: 模型名称
            provider: 嵌入提供方，默认transformers
            
        Returns:
            向量
        """
        embeddings = self.encode([text], model_name, provider, show_progress=False, text_role=text_role)
        return embeddings[0] if embeddings else []
    
    def get_embedding_dimension(self, model_name: str, provider: str = "transformers") -> int:
        """
        获取嵌入维度
        
        Args:
            model_name: 模型名称
            provider: 嵌入提供方，默认transformers
            
        Returns:
            维度
        """
        try:
            if provider == "ollama":
                ollama_service = get_ollama_service()
                dimension = ollama_service.get_embedding_dimension(model_name)
                if dimension is None:
                    raise ValueError(f"无法获取Ollama模型 {model_name} 的维度")
                return dimension
            else:
                model = self.load_model(model_name)
                return model.get_sentence_embedding_dimension()
        except Exception as e:
            logger.error(f"获取嵌入维度失败: {str(e)}")
            raise
    
    def list_available_models(self, provider: Optional[str] = None) -> List[dict]:
        """
        获取可用的模型列表（支持provider过滤）
        
        Args:
            provider: 过滤特定provider的模型，None则返回所有
            
        Returns:
            模型列表
        """
        all_models = []
        
        # Transformers模型
        if provider is None or provider == "transformers":
            transformers_models = [
                {
                    'name': 'paraphrase-multilingual-MiniLM-L12-v2',
                    'dimension': 384,
                    'description': '多语言模型，支持中英文，速度快',
                    'size': '~420MB',
                    'provider': 'transformers'
                },
                {
                    'name': 'paraphrase-multilingual-mpnet-base-v2',
                    'dimension': 768,
                    'description': '多语言模型，效果更好，速度较慢',
                    'size': '~970MB',
                    'provider': 'transformers'
                },
                {
                    'name': 'distiluse-base-multilingual-cased-v2',
                    'dimension': 512,
                    'description': '多语言模型，平衡性能和速度',
                    'size': '~480MB',
                    'provider': 'transformers'
                },
            ]
            
            # 检查哪些模型已下载
            for model_info in transformers_models:
                model_path = os.path.join(self.model_dir, model_info['name'])
                model_info['downloaded'] = os.path.exists(model_path)
                model_info['cached'] = model_info['name'] in self.models
            
            all_models.extend(transformers_models)
        
        # Ollama模型
        if provider is None or provider == "ollama":
            try:
                ollama_service = get_ollama_service()
                ollama_models = ollama_service.list_available_models()
                all_models.extend(ollama_models)
            except Exception as e:
                logger.warning(f"获取Ollama模型列表失败: {str(e)}")
        
        return all_models
    
    def get_model_info(self, model_name: str) -> dict:
        """
        获取模型信息
        
        Args:
            model_name: 模型名称
            
        Returns:
            模型信息
        """
        try:
            model = self.load_model(model_name)
            
            return {
                'name': model_name,
                'dimension': model.get_sentence_embedding_dimension(),
                'max_seq_length': model.max_seq_length,
                'device': str(model.device),
                'cached': True
            }
            
        except Exception as e:
            logger.error(f"获取模型信息失败: {str(e)}")
            raise
    
    def unload_model(self, model_name: str = None):
        """
        卸载模型释放显存
        
        Args:
            model_name: 模型名称，None则卸载所有模型
        """
        import torch
        
        try:
            if model_name:
                if model_name in self.models:
                    del self.models[model_name]
                    logger.info(f"已卸载嵌入模型: {model_name}")
            else:
                self.models.clear()
                self._vector_cache.clear()
                logger.info("已卸载所有嵌入模型")
            
            # 清理GPU缓存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU缓存已清理")
                
        except Exception as e:
            logger.error(f"卸载模型失败: {str(e)}")


# 延迟加载单例（避免启动时加载torch/CUDA）
_embedding_service_instance = None

def get_embedding_service() -> EmbeddingService:
    """获取EmbeddingService单例（延迟加载）
    
    首次调用时才初始化，避免Windows多进程启动时的CUDA冲突
    """
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService()
    return _embedding_service_instance

