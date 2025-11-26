#!/usr/bin/env python3
"""
预下载HuggingFace模型脚本
下载小型嵌入模型用于MyRAG系统
"""

import os
import sys
from pathlib import Path

def download_models():
    """下载HuggingFace模型"""
    
    print("=" * 50)
    print("MyRAG - Preloading HuggingFace Models")
    print("=" * 50)
    print()
    
    try:
        from sentence_transformers import SentenceTransformer
        import torch
        
        # 检查CUDA是否可用
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[INFO] Device: {device}")
        print()
        
        # 设置模型保存目录
        models_dir = Path("/app/Models/Embedding")
        models_dir.mkdir(parents=True, exist_ok=True)
        
        # 模型列表（小型、高质量嵌入模型）
        models = [
            {
                "name": "paraphrase-multilingual-MiniLM-L12-v2",
                "description": "Multilingual embedding model (471MB)",
                "size": "471MB"
            }
        ]
        
        print(f"[INFO] Models will be saved to: {models_dir}")
        print(f"[INFO] Downloading {len(models)} model(s)...")
        print()
        
        for idx, model_info in enumerate(models, 1):
            model_name = model_info["name"]
            print(f"[{idx}/{len(models)}] Downloading {model_name}")
            print(f"  Description: {model_info['description']}")
            print(f"  Size: {model_info['size']}")
            print()
            
            try:
                # 下载模型
                model_path = models_dir / model_name.replace("/", "_")
                
                print(f"  → Loading model from HuggingFace Hub...")
                model = SentenceTransformer(model_name, device=device)
                
                # 保存模型到本地
                print(f"  → Saving to {model_path}...")
                model.save(str(model_path))
                
                # 验证模型
                print(f"  → Testing model...")
                test_embedding = model.encode(["Hello world"], convert_to_numpy=True)
                print(f"  → Test embedding shape: {test_embedding.shape}")
                
                print(f"[SUCCESS] {model_name} downloaded and verified")
                print()
                
            except Exception as e:
                print(f"[WARNING] Failed to download {model_name}: {e}")
                print()
                continue
        
        # 显示已下载的模型
        print("=" * 50)
        print("Downloaded Models:")
        print("=" * 50)
        
        if models_dir.exists():
            downloaded = list(models_dir.iterdir())
            if downloaded:
                for model_dir in downloaded:
                    if model_dir.is_dir():
                        size = sum(f.stat().st_size for f in model_dir.rglob('*') if f.is_file())
                        size_mb = size / (1024 * 1024)
                        print(f"  ✓ {model_dir.name} ({size_mb:.1f} MB)")
            else:
                print("  No models downloaded")
        
        print()
        print("[INFO] Model preloading completed!")
        print()
        print("Usage in config.yaml:")
        print("  embedding:")
        print("    provider: 'transformers'")
        print("    default_model: 'paraphrase-multilingual-MiniLM-L12-v2'")
        print()
        
    except ImportError as e:
        print(f"[ERROR] Required packages not installed: {e}")
        print("Please ensure sentence-transformers is installed:")
        print("  pip install sentence-transformers")
        sys.exit(1)
    
    except Exception as e:
        print(f"[ERROR] Failed to download models: {e}")
        sys.exit(1)


if __name__ == "__main__":
    download_models()
