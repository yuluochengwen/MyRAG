#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试1: 配置加载测试"""

import sys
from pathlib import Path

# 添加Backend到路径
backend_path = Path(__file__).parent.parent / "Backend"
sys.path.insert(0, str(backend_path))


def test_config():
    """测试配置加载"""
    print("\n1. 测试配置文件加载...")
    
    try:
        from app.core.config import settings, load_config
        print(f"   ✓ 配置模块导入成功")
        
        # 检查基本配置
        print(f"\n2. 检查应用配置...")
        print(f"   - 应用名称: {settings.app.name}")
        print(f"   - 版本: {settings.app.version}")
        print(f"   - Debug模式: {settings.app.debug}")
        print(f"   - 主机: {settings.app.host}")
        print(f"   - 端口: {settings.app.port}")
        
        # 检查数据库配置
        print(f"\n3. 检查数据库配置...")
        print(f"   - 数据库主机: {settings.database.host}")
        print(f"   - 数据库端口: {settings.database.port}")
        print(f"   - 数据库名称: {settings.database.database}")
        print(f"   ✓ 数据库配置正常")
        
        # 检查向量数据库配置
        print(f"\n4. 检查向量数据库配置...")
        print(f"   - 向量数据库类型: {settings.vector_db.type}")
        print(f"   - 持久化目录: {settings.vector_db.persist_dir}")
        print(f"   ✓ 向量数据库配置正常")
        
        # 检查嵌入模型配置
        print(f"\n5. 检查嵌入模型配置...")
        print(f"   - 默认提供商: {settings.embedding.provider}")
        print(f"   - 默认模型: {settings.embedding.default_model}")
        print(f"   - 模型目录: {settings.embedding.model_dir}")
        if hasattr(settings.embedding, 'ollama'):
            print(f"   - Ollama配置: {settings.embedding.ollama}")
        print(f"   ✓ 嵌入模型配置正常")
        
        # 检查文本处理配置
        print(f"\n6. 检查文本处理配置...")
        print(f"   - 分块大小: {settings.text_processing.chunk_size}")
        print(f"   - 分块重叠: {settings.text_processing.chunk_overlap}")
        print(f"   ✓ 文本处理配置正常")
        
        # 检查语义分割配置
        if hasattr(settings.text_processing, 'semantic_split'):
            print(f"\n7. 检查语义分割配置...")
            semantic_cfg = settings.text_processing.semantic_split
            print(f"   - Ollama模型: {semantic_cfg.ollama_model}")
            print(f"   - 最大块大小: {semantic_cfg.max_chunk_size}")
            print(f"   - 最小块大小: {semantic_cfg.min_chunk_size}")
            print(f"   - 启用状态: {semantic_cfg.enabled}")
            print(f"   ✓ 语义分割配置正常")
        
        print(f"\n✅ 配置加载测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 配置加载测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_config()
    exit(0 if success else 1)
