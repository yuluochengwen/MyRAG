"""Ollama LLM服务"""
import requests
from typing import List, Dict, Optional, AsyncGenerator
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OllamaLLMService:
    """Ollama LLM服务"""
    
    def __init__(self):
        # 从配置中获取Ollama设置（复用embedding的ollama配置）
        ollama_config = getattr(settings.embedding, 'ollama', None)
        if ollama_config:
            self.base_url = ollama_config.get('base_url', 'http://localhost:11434')
            self.timeout = ollama_config.get('timeout', 30)
        else:
            self.base_url = 'http://localhost:11434'
            self.timeout = 30
        
        logger.info(f"Ollama LLM服务初始化: base_url={self.base_url}")
    
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
    
    def list_available_models(self) -> List[Dict]:
        """
        获取Ollama可用的LLM模型列表
        
        Returns:
            模型信息列表 [{"name": "qwen2.5:7b", "size": 4.7, "type": "Qwen", ...}, ...]
        """
        try:
            if not self.is_available():
                logger.warning("Ollama服务不可用")
                return []
            
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"获取Ollama模型列表失败: {response.status_code}")
                return []
            
            data = response.json()
            models = data.get('models', [])
            
            # 过滤掉embedding模型，只保留LLM模型
            llm_models = []
            for model in models:
                model_name = model.get('name', '')
                # 跳过embedding模型（名称中包含embed/embedding）
                if 'embed' in model_name.lower():
                    continue
                
                # 获取模型大小
                size_bytes = model.get('size', 0)
                size_gb = size_bytes / (1024 ** 3) if size_bytes else 0
                
                # 推测模型类型
                model_type = self._infer_model_type(model_name)
                
                llm_models.append({
                    "name": model_name,
                    "type": model_type,
                    "size": round(size_gb, 2),
                    "modified_at": model.get('modified_at', ''),
                    "provider": "ollama"
                })
            
            logger.info(f"发现Ollama LLM模型: {len(llm_models)}个")
            return llm_models
            
        except Exception as e:
            logger.error(f"获取Ollama模型列表失败: {str(e)}")
            return []
    
    def _infer_model_type(self, model_name: str) -> str:
        """
        根据模型名称推测模型类型
        
        Args:
            model_name: 模型名称
            
        Returns:
            模型类型
        """
        name_lower = model_name.lower()
        
        if 'qwen' in name_lower:
            return 'Qwen'
        elif 'llama' in name_lower:
            return 'LLaMA'
        elif 'deepseek' in name_lower:
            return 'DeepSeek'
        elif 'mistral' in name_lower:
            return 'Mistral'
        elif 'gemma' in name_lower:
            return 'Gemma'
        elif 'phi' in name_lower:
            return 'Phi'
        elif 'codellama' in name_lower:
            return 'CodeLLaMA'
        else:
            return 'Unknown'
    
    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        使用Ollama进行对话
        
        Args:
            model: 模型名称
            messages: 消息列表 [{"role": "system/user/assistant", "content": "..."}, ...]
            temperature: 生成温度
            max_tokens: 最大生成token数
            
        Returns:
            生成的回答
        """
        try:
            if not self.is_available():
                raise RuntimeError("Ollama服务不可用，请确保Ollama已启动")
            
            logger.info(f"Ollama对话开始: model={model}, messages={len(messages)}条, temperature={temperature}")
            
            # 构建Ollama API请求
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature
                }
            }
            
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens
            
            # 调用Ollama Chat API
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_msg = f"Ollama API返回错误: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            result = response.json()
            message = result.get('message', {})
            answer = message.get('content', '')
            
            if not answer:
                raise RuntimeError(f"Ollama返回的响应中没有content: {result}")
            
            logger.info(f"Ollama对话完成: 生成了{len(answer)}个字符")
            return answer
            
        except Exception as e:
            logger.error(f"Ollama对话失败: {str(e)}")
            raise
    
    async def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        使用Ollama进行流式对话
        
        Args:
            model: 模型名称
            messages: 消息列表
            temperature: 生成温度
            max_tokens: 最大生成token数
            
        Yields:
            生成的文本片段
        """
        try:
            if not self.is_available():
                raise RuntimeError("Ollama服务不可用，请确保Ollama已启动")
            
            logger.info(f"Ollama流式对话开始: model={model}, messages={len(messages)}条")
            
            # 构建Ollama API请求
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": temperature
                }
            }
            
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens
            
            # 调用Ollama Chat API (流式)
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_msg = f"Ollama API返回错误: {response.status_code}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # 逐行解析流式响应
            for line in response.iter_lines():
                if line:
                    try:
                        import json
                        data = json.loads(line)
                        message = data.get('message', {})
                        content = message.get('content', '')
                        
                        if content:
                            yield content
                        
                        # 检查是否完成
                        if data.get('done', False):
                            break
                            
                    except json.JSONDecodeError as e:
                        logger.warning(f"解析Ollama流式响应失败: {e}")
                        continue
            
            logger.info("Ollama流式对话完成")
            
        except Exception as e:
            logger.error(f"Ollama流式对话失败: {str(e)}")
            raise


# 全局实例（懒加载）
_ollama_llm_service = None


def get_ollama_llm_service() -> OllamaLLMService:
    """
    获取Ollama LLM服务实例（懒加载）
    
    Returns:
        OllamaLLMService实例
    """
    global _ollama_llm_service
    if _ollama_llm_service is None:
        _ollama_llm_service = OllamaLLMService()
    return _ollama_llm_service
