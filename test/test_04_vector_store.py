#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试4: 向量存储测试"""

import sys
from pathlib import Path

# 添加Backend到路径
backend_path = Path(__file__).parent.parent / "Backend"
sys.path.insert(0, str(backend_path))


def test_vector_store():
    """测试向量存储功能"""
    print("\n1. 测试向量存储初始化...")
    
    try:
        from app.services.vector_store_service import get_vector_store_service
        vector_store = get_vector_store_service()
        print(f"   ✓ 向量存储服务初始化成功")
        
        # 测试创建集合
        print(f"\n2. 测试创建测试集合...")
        test_collection = "test_collection_temp"
        collection = vector_store.get_or_create_collection(test_collection)
        print(f"   ✓ 集合创建成功: {test_collection}")
        
        # 测试添加向量
        print(f"\n3. 测试添加向量...")
        test_embeddings = [[0.1, 0.2, 0.3, 0.4, 0.5]]
        test_ids = ["test_id_1"]
        test_documents = ["测试文本"]
        test_metadatas = [{"source": "test"}]
        
        vector_store.add_vectors(
            collection_name=test_collection,
            ids=test_ids,
            embeddings=test_embeddings,
            documents=test_documents,
            metadatas=test_metadatas
        )
        print(f"   ✓ 向量添加成功")
        
        # 测试搜索
        print(f"\n4. 测试向量搜索...")
        results = vector_store.search(
            collection_name=test_collection,
            query_embeddings=[[0.1, 0.2, 0.3, 0.4, 0.5]],
            n_results=1
        )
        
        if results and 'ids' in results and len(results['ids']) > 0:
            print(f"   ✓ 搜索成功，找到 {len(results['ids'][0])} 个结果")
        else:
            print(f"   ⚠️  搜索结果为空")
        
        # 测试获取统计
        print(f"\n5. 测试获取集合统计...")
        stats = vector_store.get_collection_stats(test_collection)
        print(f"   ✓ 集合统计: count={stats['count']}")
        
        # 测试删除向量
        print(f"\n6. 测试删除向量...")
        vector_store.delete_by_ids(test_collection, test_ids)
        print(f"   ✓ 向量删除成功")
        
        # 测试删除集合
        print(f"\n7. 测试删除集合...")
        vector_store.delete_collection(test_collection)
        print(f"   ✓ 集合删除成功")
        
        print(f"\n✅ 向量存储测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 向量存储测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_vector_store()
    exit(0 if success else 1)
