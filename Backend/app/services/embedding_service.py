"""嵌入模型服务"""
import os
from typing import List, Optional, TYPE_CHECKING
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
        from app.services.ollama_embedding_service import ollama_embedding_service
        _ollama_service = ollama_embedding_service
    return _ollama_service


class EmbeddingService:
    """嵌入模型服务"""
    
    def __init__(self):
        self.models = {}  # 模型缓存
        self.device = self._get_device()
        self.model_dir = settings.embedding.model_dir
        
        # 确保模型目录存在
        os.makedirs(self.model_dir, exist_ok=True)
        
        logger.info(f"嵌入服务初始化: device={self.device}")
    
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
        batch_size: int = 32,
        show_progress: bool = False
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
            
            logger.info(f"编码文本: count={len(texts)}, model={model_name}, provider={provider}")
            
            # 根据provider路由到不同的实现
            if provider == "ollama":
                ollama_service = get_ollama_service()
                return ollama_service.encode(texts, model_name, batch_size, show_progress)
            else:
                # 默认使用transformers
                return self._encode_with_transformers(texts, model_name, batch_size, show_progress)
            
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
            向量列表
        """
        model = self.load_model(model_name)
        
        # 编码
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True
        )
        
        # 转换为列表
        embeddings_list = embeddings.tolist()
        
        logger.info(f"Transformers编码完成: vectors={len(embeddings_list)}, "
                   f"dimension={len(embeddings_list[0]) if embeddings_list else 0}")
        
        return embeddings_list
    
    def encode_single(self, text: str, model_name: str, provider: str = "transformers") -> List[float]:
        """
        编码单个文本
        
        Args:
            text: 文本
            model_name: 模型名称
            provider: 嵌入提供方，默认transformers
            
        Returns:
            向量
        """
        embeddings = self.encode([text], model_name, provider, show_progress=False)
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
    
    def unload_model(self, model_name: str) -> bool:
        """
        卸载模型释放内存
        
        Args:
            model_name: 模型名称
            
        Returns:
            是否成功
        """
        if model_name in self.models:
            del self.models[model_name]
            
            # 清理GPU缓存
            if self.device == 'cuda':
                torch.cuda.empty_cache()
            
            logger.info(f"模型已卸载: {model_name}")
            return True
        
        return False
    
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
                logger.info("已卸载所有嵌入模型")
            
            # 清理GPU缓存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU缓存已清理")
                
        except Exception as e:
            logger.error(f"卸载模型失败: {str(e)}")


# 全局单例
embedding_service = EmbeddingService()

