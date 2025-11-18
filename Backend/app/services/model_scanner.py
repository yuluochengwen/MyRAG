"""模型扫描服务 - 扫描本地LLM和Embedding模型"""
import os
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from app.core.config import settings, BASE_DIR


class ModelScanner:
    """模型扫描器"""
    
    def __init__(self):
        self.llm_dir = BASE_DIR / "Models" / "LLM"
        self.embedding_dir = Path(settings.embedding.model_dir)
        self.lora_dir = BASE_DIR / "Models" / "LoRA"
    
    def _get_folder_size(self, folder_path: Path) -> int:
        """
        计算文件夹大小（字节）
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            文件夹总大小（字节）
        """
        total_size = 0
        try:
            for item in folder_path.rglob('*'):
                if item.is_file():
                    total_size += item.stat().st_size
        except Exception as e:
            print(f"Warning: Failed to calculate size for {folder_path}: {e}")
        return total_size
    
    def _format_size(self, size_bytes: int) -> str:
        """
        格式化文件大小
        
        Args:
            size_bytes: 字节数
            
        Returns:
            格式化后的大小字符串
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f}PB"
    
    def _get_model_type(self, config: dict) -> str:
        """
        智能识别模型类型
        
        Args:
            config: 模型配置字典
            
        Returns:
            模型类型字符串
        """
        model_type = config.get("model_type", "").lower()
        architectures = config.get("architectures", [])
        arch_str = " ".join(architectures).lower() if architectures else ""
        
        # BERT 系列
        if "bert" in model_type or "bert" in arch_str:
            if "roberta" in model_type or "roberta" in arch_str:
                return "RoBERTa"
            elif "albert" in model_type or "albert" in arch_str:
                return "ALBERT"
            elif "distilbert" in model_type or "distilbert" in arch_str:
                return "DistilBERT"
            else:
                return "BERT"
        
        # GPT 系列
        if "gpt" in model_type or "gpt" in arch_str:
            return "GPT"
        
        # Qwen 系列
        if "qwen" in model_type or "qwen" in arch_str:
            return "Qwen"
        
        # LLaMA 系列
        if "llama" in model_type or "llama" in arch_str:
            return "LLaMA"
        
        # DeepSeek 系列
        if "deepseek" in model_type or "deepseek" in arch_str:
            return "DeepSeek"
        
        # T5 系列
        if "t5" in model_type or "t5" in arch_str:
            return "T5"
        
        # Sentence Transformers
        if "sentence" in arch_str or "mpnet" in arch_str:
            return "Sentence-BERT"
        
        # 默认返回架构名称
        if architectures:
            return architectures[0].replace("ForCausalLM", "").replace("ForMaskedLM", "").replace("Model", "")
        
        return "Unknown"
    
    
    def scan_llm_models(self) -> List[Dict[str, any]]:
        """
        扫描本地LLM模型（增强版）
        
        Returns:
            模型信息列表: [{"name": "DeepSeek-OCR-3B", "path": "...", "provider": "local", ...}]
        """
        models = []
        
        if not self.llm_dir.exists():
            return models
        
        for model_path in self.llm_dir.iterdir():
            if not model_path.is_dir():
                continue
            
            # 检查是否存在 config.json (Hugging Face 模型标志)
            config_file = model_path / "config.json"
            if config_file.exists():
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    
                    # 获取模型大小
                    size_bytes = self._get_folder_size(model_path)
                    
                    # 获取创建时间
                    created_at = datetime.fromtimestamp(model_path.stat().st_ctime)
                    modified_at = datetime.fromtimestamp(model_path.stat().st_mtime)
                    
                    # 获取模型参数量（如果有）
                    params = None
                    if "num_parameters" in config:
                        params = config["num_parameters"]
                    else:
                        # 尝试从模型名称推断（如 Qwen3-8B）
                        name_lower = model_path.name.lower()
                        if "8b" in name_lower:
                            params = "8B"
                        elif "7b" in name_lower:
                            params = "7B"
                        elif "4b" in name_lower:
                            params = "4B"
                        elif "3b" in name_lower:
                            params = "3B"
                        elif "1.5b" in name_lower:
                            params = "1.5B"
                    
                    models.append({
                        "name": model_path.name,
                        "path": str(model_path),
                        "provider": "local",
                        "type": self._get_model_type(config),
                        "architecture": config.get("architectures", ["unknown"])[0] if config.get("architectures") else "unknown",
                        "model_type": config.get("model_type", "unknown"),
                        "size": self._format_size(size_bytes),
                        "size_bytes": size_bytes,
                        "parameters": params,
                        "hidden_size": config.get("hidden_size"),
                        "created_at": created_at.isoformat(),
                        "modified_at": modified_at.isoformat(),
                        "is_downloaded": True,
                        "status": "deployed"
                    })
                except Exception as e:
                    print(f"Warning: Failed to read {config_file}: {e}")
        
        return models
    
    def scan_embedding_models(self) -> List[Dict[str, any]]:
        """
        扫描本地Embedding模型（增强版）
        
        Returns:
            模型信息列表: [{"name": "bert-base-chinese", "path": "...", "dimension": 768, ...}]
        """
        models = []
        
        if not self.embedding_dir.exists():
            return models
        
        for model_path in self.embedding_dir.iterdir():
            if not model_path.is_dir():
                continue
            
            # 检查是否存在 config.json
            config_file = model_path / "config.json"
            if config_file.exists():
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    
                    # 尝试获取向量维度
                    dimension = config.get("hidden_size") or config.get("dim") or config.get("d_model")
                    
                    # 获取模型大小
                    size_bytes = self._get_folder_size(model_path)
                    
                    # 获取创建时间
                    created_at = datetime.fromtimestamp(model_path.stat().st_ctime)
                    modified_at = datetime.fromtimestamp(model_path.stat().st_mtime)
                    
                    models.append({
                        "name": model_path.name,
                        "path": str(model_path),
                        "provider": "local",
                        "type": self._get_model_type(config),
                        "architecture": config.get("architectures", ["unknown"])[0] if config.get("architectures") else "unknown",
                        "model_type": config.get("model_type", "unknown"),
                        "dimension": dimension,
                        "size": self._format_size(size_bytes),
                        "size_bytes": size_bytes,
                        "created_at": created_at.isoformat(),
                        "modified_at": modified_at.isoformat(),
                        "is_downloaded": True,
                        "status": "deployed"
                    })
                except Exception as e:
                    print(f"Warning: Failed to read {config_file}: {e}")
        
        return models
    
    def scan_lora_models(self) -> List[Dict[str, any]]:
        """
        扫描本地LoRA模型
        
        Returns:
            LoRA模型信息列表
        """
        models = []
        
        if not self.lora_dir.exists():
            return models
        
        for model_path in self.lora_dir.iterdir():
            if not model_path.is_dir():
                continue
            
            # LoRA 模型可能有 adapter_config.json
            config_file = model_path / "adapter_config.json"
            if config_file.exists():
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    
                    # 获取模型大小
                    size_bytes = self._get_folder_size(model_path)
                    
                    # 获取创建时间
                    created_at = datetime.fromtimestamp(model_path.stat().st_ctime)
                    
                    models.append({
                        "name": model_path.name,
                        "path": str(model_path),
                        "base_model": config.get("base_model_name_or_path", "Unknown"),
                        "rank": config.get("r", "Unknown"),
                        "lora_alpha": config.get("lora_alpha", "Unknown"),
                        "target_modules": config.get("target_modules", []),
                        "size": self._format_size(size_bytes),
                        "size_bytes": size_bytes,
                        "created_at": created_at.isoformat(),
                        "status": "deployed"
                    })
                except Exception as e:
                    print(f"Warning: Failed to read {config_file}: {e}")
        
        return models
    
    def get_remote_llm_models(self) -> List[Dict[str, str]]:
        """
        获取可用的远程LLM模型列表(预设)
        
        Returns:
            远程模型列表
        """
        return [
            {"name": "gpt-4", "provider": "openai", "type": "llm"},
            {"name": "gpt-3.5-turbo", "provider": "openai", "type": "llm"},
            {"name": "gpt-4-turbo-preview", "provider": "openai", "type": "llm"},
        ]
    
    def get_all_llm_models(self) -> Dict[str, List[Dict]]:
        """
        获取所有LLM模型(本地+远程+ollama)
        
        Returns:
            {"local": [...], "remote": [...], "ollama": [...]}
        """
        result = {
            "local": self.scan_llm_models(),
            "remote": self.get_remote_llm_models()
        }
        
        # 获取Ollama LLM模型
        try:
            from app.services.ollama_llm_service import get_ollama_llm_service
            ollama_service = get_ollama_llm_service()
            result["ollama"] = ollama_service.list_available_models()
        except Exception as e:
            print(f"Warning: Failed to get Ollama LLM models: {e}")
            result["ollama"] = []
        
        return result
    
    def get_all_embedding_models(self) -> List[Dict]:
        """
        获取所有Embedding模型(目前只有本地)
        
        Returns:
            模型列表
        """
        return self.scan_embedding_models()


# 全局实例
model_scanner = ModelScanner()
