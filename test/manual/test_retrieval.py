#!/usr/bin/env python3
"""
测试知识库检索功能
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录和Backend目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "Backend"))

from app.core.database import DatabaseManager
from app.services.knowledge_base.knowledge_base_service import KnowledgeBaseService
from app.services.embedding.embedding_service import get_embedding_service
from app.services.retrieval.vector_store_service import get_vector_store_service

async def test_knowledge_base_retrieval():
    """测试知识库检索功能"""
    print("=== 测试知识库检索功能 ===")
    
    try:
        # 初始化数据库管理器
        db_manager = DatabaseManager()
        await db_manager.connect()
        
        # 初始化知识库服务
        kb_service = KnowledgeBaseService(db_manager)
        
        # 获取知识库列表
        print("\n1. 获取知识库列表:")
        kbs = await kb_service.list_knowledge_bases()
        for kb in kbs:
            print(f"   ID: {kb.id}, 名称: {kb.name}, 文件数: {kb.file_count}, 文本块数: {kb.chunk_count}")
        
        if not kbs:
            print("   没有找到知识库")
            return
        
        # 选择第一个知识库进行测试
        test_kb = kbs[0]
        print(f"\n2. 测试知识库: {test_kb.name} (ID: {test_kb.id})")
        
        # 测试向量存储
        vector_store = get_vector_store_service()
        collection_name = f"kb_{test_kb.id}"
        
        try:
            stats = vector_store.get_collection_stats(collection_name)
            print(f"   向量集合状态: {stats}")
        except Exception as e:
            print(f"   向量集合不存在: {e}")
        
        # 测试检索
        test_queries = [
            "江苏风云科技",
            "公司介绍",
            "服务内容",
            "技术栈"
        ]
        
        for query in test_queries:
            print(f"\n3. 测试检索: '{query}'")
            try:
                results = await kb_service.search_knowledge_base(
                    kb_id=test_kb.id,
                    query=query,
                    top_k=3,
                    score_threshold=0.1
                )
                
                if results:
                    print(f"   找到 {len(results)} 个结果:")
                    for i, result in enumerate(results, 1):
                        similarity = result.get('similarity', 0.0)
                        content = result.get('content', '').strip()[:200] + '...' if len(result.get('content', '')) > 200 else result.get('content', '')
                        metadata = result.get('metadata', {})
                        filename = metadata.get('filename', '未知文件')
                        print(f"   {i}. 相似度: {similarity:.3f}, 文件: {filename}")
                        print(f"      内容: {content}")
                else:
                    print("   未找到相关结果")
                    
            except Exception as e:
                print(f"   检索失败: {e}")
        
        # 测试嵌入服务
        print("\n4. 测试嵌入服务:")
        embedding_service = get_embedding_service()
        try:
            test_text = "测试嵌入功能"
            embedding = embedding_service.encode_single(
                test_text,
                model_name=test_kb.embedding_model,
                provider=test_kb.embedding_provider,
                text_role='query'
            )
            print(f"   嵌入成功，向量维度: {len(embedding)}")
        except Exception as e:
            print(f"   嵌入失败: {e}")
            
    except Exception as e:
        print(f"测试失败: {e}")
    finally:
        if 'db_manager' in locals():
            await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(test_knowledge_base_retrieval())
