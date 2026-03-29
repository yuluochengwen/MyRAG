#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试3: 服务单例模式测试"""

import sys
from pathlib import Path

# 添加Backend到路径
backend_path = Path(__file__).parent.parent / "Backend"
sys.path.insert(0, str(backend_path))


def test_services():
    """测试服务单例模式"""
    print("\n1. 测试 VectorStoreService 单例...")
    
    try:
        from app.services.vector_store_service import get_vector_store_service
        vs1 = get_vector_store_service()
        vs2 = get_vector_store_service()
        
        if vs1 is vs2:
            print(f"   ✓ VectorStoreService 单例模式正常")
        else:
            print(f"   ❌ VectorStoreService 返回了不同的实例")
            return False
        
        # 检查方法
        methods = ['add_vectors', 'search', 'delete_by_ids', 'get_collection_stats']
        for method in methods:
            if hasattr(vs1, method):
                print(f"   ✓ 方法 {method} 存在")
            else:
                print(f"   ❌ 方法 {method} 不存在")
                return False
        
        print(f"\n2. 测试 EmbeddingService 单例...")
        from app.services.embedding_service import get_embedding_service
        es1 = get_embedding_service()
        es2 = get_embedding_service()
        
        if es1 is es2:
            print(f"   ✓ EmbeddingService 单例模式正常")
        else:
            print(f"   ❌ EmbeddingService 返回了不同的实例")
            return False
        
        print(f"\n3. 测试 TransformersService 单例...")
        from app.services.transformers_service import get_transformers_service
        ts1 = get_transformers_service()
        ts2 = get_transformers_service()
        
        if ts1 is ts2:
            print(f"   ✓ TransformersService 单例模式正常")
        else:
            print(f"   ❌ TransformersService 返回了不同的实例")
            return False
        
        print(f"\n4. 测试 dependencies.py 集成...")
        from app.core.dependencies import get_vector_service, get_embedding_service as get_es
        vs3 = get_vector_service()
        es3 = get_es()
        
        if vs3 is vs1:
            print(f"   ✓ dependencies.py 返回正确的 VectorStoreService 单例")
        else:
            print(f"   ❌ dependencies.py 返回了不同的 VectorStoreService 实例")
            return False
        
        if es3 is es1:
            print(f"   ✓ dependencies.py 返回正确的 EmbeddingService 单例")
        else:
            print(f"   ❌ dependencies.py 返回了不同的 EmbeddingService 实例")
            return False
        
        print(f"\n✅ 服务单例测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 服务单例测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_services()
    exit(0 if success else 1)
