"""Ollama嵌入模型服务"""
import requests
from typing import List, Optional
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OllamaEmbeddingService:
    """Ollama嵌入模型服务"""
    
    def __init__(self):
        # 从配置中获取Ollama设置
        ollama_config = getattr(settings.embedding, 'ollama', None)
        if ollama_config:
            self.base_url = ollama_config.get('base_url', 'http://localhost:11434')
            self.timeout = ollama_config.get('timeout', 30)
            self.default_model = ollama_config.get('default_model', 'nomic-embed-text')
        else:
            self.base_url = 'http://localhost:11434'
            self.timeout = 30
            self.default_model = 'nomic-embed-text'
        
        logger.info(f"Ollama嵌入服务初始化: base_url={self.base_url}")
    
    def is_available(self) -> bool:
        """
        检查Ollama服务是否可用
        
        Returns:
            是否可用
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama服务不可用: {str(e)}")
            return False
    
    def encode(
        self,
        texts: List[str],
        model_name: str,
        batch_size: int = 32,
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        将文本编码为向量
        
        Args:
            texts: 文本列表
            model_name: 模型名称
            batch_size: 批次大小（Ollama不支持批处理，此参数仅为接口兼容）
            show_progress: 是否显示进度（Ollama不支持，此参数仅为接口兼容）
            
        Returns:
            向量列表
        """
        try:
            if not texts:
                return []
            
            # 检查服务可用性
            if not self.is_available():
                raise RuntimeError("Ollama服务不可用，请确保Ollama已启动")
            
            logger.info(f"使用Ollama编码文本: count={len(texts)}, model={model_name}")
            
            embeddings = []
            
            # Ollama API一次只能处理一个文本
            for i, text in enumerate(texts):
                try:
                    response = requests.post(
                        f"{self.base_url}/api/embeddings",
                        json={
                            "model": model_name,
                            "prompt": text
                        },
                        timeout=self.timeout
                    )
                    
                    if response.status_code != 200:
                        error_msg = f"Ollama API返回错误: {response.status_code} - {response.text}"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
                    
                    result = response.json()
                    embedding = result.get('embedding')
                    
                    if not embedding:
                        raise RuntimeError(f"Ollama返回的响应中没有embedding字段: {result}")
                    
                    embeddings.append(embedding)
                    
                    # 显示进度
                    if (i + 1) % 10 == 0 or (i + 1) == len(texts):
                        logger.info(f"编码进度: {i + 1}/{len(texts)}")
                
                except requests.exceptions.Timeout:
                    logger.error(f"Ollama请求超时: text_index={i}")
                    raise RuntimeError(f"Ollama请求超时，请检查服务状态或增加timeout配置")
                except requests.exceptions.RequestException as e:
                    logger.error(f"Ollama请求失败: {str(e)}")
                    raise RuntimeError(f"Ollama请求失败: {str(e)}")
            
            logger.info(f"Ollama编码完成: vectors={len(embeddings)}, "
                       f"dimension={len(embeddings[0]) if embeddings else 0}")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Ollama文本编码失败: {str(e)}")
            raise
    
    def encode_single(self, text: str, model_name: str) -> List[float]:
        """
        编码单个文本
        
        Args:
            text: 文本
            model_name: 模型名称
            
        Returns:
            向量
        """
        embeddings = self.encode([text], model_name)
        return embeddings[0] if embeddings else []
    
    def list_available_models(self) -> List[dict]:
        """
        获取可用的Ollama嵌入模型列表
        
        Returns:
            模型列表
        """
        try:
            if not self.is_available():
                logger.warning("Ollama服务不可用，返回空模型列表")
                return []
            
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            
            if response.status_code != 200:
                logger.error(f"获取Ollama模型列表失败: {response.status_code}")
                return []
            
            data = response.json()
            all_models = data.get('models', [])
            
            # 过滤出嵌入模型（名称包含embed）
            embedding_models = []
            for model in all_models:
                model_name = model.get('name', '')
                if 'embed' in model_name.lower():
                    # 获取模型大小（转换为MB）
                    size_bytes = model.get('size', 0)
                    size_mb = round(size_bytes / (1024 * 1024), 1)
                    
                    embedding_models.append({
                        'name': model_name,
                        'dimension': None,  # Ollama API不直接提供维度信息
                        'description': f'Ollama嵌入模型',
                        'size': f'~{size_mb}MB',
                        'downloaded': True,
                        'provider': 'ollama'
                    })
            
            logger.info(f"发现 {len(embedding_models)} 个Ollama嵌入模型")
            return embedding_models
            
        except Exception as e:
            logger.error(f"获取Ollama模型列表失败: {str(e)}")
            return []
    
    def get_embedding_dimension(self, model_name: str) -> Optional[int]:
        """
        获取嵌入维度（通过实际编码测试文本获取）
        
        Args:
            model_name: 模型名称
            
        Returns:
            维度，如果获取失败返回None
        """
        try:
            test_embedding = self.encode_single("test", model_name)
            return len(test_embedding) if test_embedding else None
        except Exception as e:
            logger.error(f"获取Ollama模型维度失败: {str(e)}")
            return None


# 全局单例
ollama_embedding_service = OllamaEmbeddingService()
