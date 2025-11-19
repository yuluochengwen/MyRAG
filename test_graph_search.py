"""测试图谱检索功能"""
import asyncio
import sys
sys.path.append('Backend')

from app.services.hybrid_retrieval_service import get_hybrid_retrieval_service
from app.services.entity_extraction_service import get_entity_extraction_service
from app.services.neo4j_graph_service import get_neo4j_graph_service
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def test_entity_extraction(query: str):
    """测试实体提取"""
    print(f"\n{'='*60}")
    print(f"1. 测试实体提取")
    print(f"{'='*60}")
    print(f"查询: {query}")
    
    entity_service = get_entity_extraction_service()
    result = await entity_service.extract_from_text(query)
    
    entities = result.get('entities', [])
    print(f"提取到的实体数量: {len(entities)}")
    for e in entities:
        print(f"  - {e['name']} ({e['type']})")
    
    return entities


def test_neo4j_entities(kb_id: int):
    """测试Neo4j中的实体"""
    print(f"\n{'='*60}")
    print(f"2. 检查Neo4j中的实体")
    print(f"{'='*60}")
    
    graph_service = get_neo4j_graph_service()
    
    # 获取图谱统计
    stats = graph_service.get_graph_stats(kb_id)
    print(f"图谱统计: {stats}")
    
    # 尝试查询一些实体
    query = """
    MATCH (e:Entity {kb_id: $kb_id})
    RETURN e.name as name, e.type as type
    LIMIT 10
    """
    
    try:
        with graph_service.driver.session() as session:
            result = session.run(query, kb_id=kb_id)
            entities = [dict(record) for record in result]
            
        print(f"\n前10个实体:")
        for e in entities:
            print(f"  - {e['name']} ({e['type']})")
            
        return entities
    except Exception as e:
        print(f"查询失败: {e}")
        return []


async def test_entity_lookup(kb_id: int, entity_name: str):
    """测试实体查找"""
    print(f"\n{'='*60}")
    print(f"3. 测试实体查找")
    print(f"{'='*60}")
    print(f"查找实体: {entity_name}")
    
    graph_service = get_neo4j_graph_service()
    
    # 测试直接查询
    entity_info = graph_service.get_entity_info(kb_id, entity_name)
    if entity_info:
        print(f"✓ 找到实体: {entity_info['name']} ({entity_info['type']})")
        print(f"  出边关系: {len(entity_info.get('out_relations', []))}")
        print(f"  入边关系: {len(entity_info.get('in_relations', []))}")
    else:
        print(f"✗ 未找到实体: {entity_name}")
    
    # 测试相关实体查询
    related = graph_service.find_related_entities(kb_id, entity_name, max_hops=2, max_results=5)
    print(f"\n相关实体: {len(related)}")
    for r in related[:3]:
        print(f"  - {r['entity']} (跳数: {r['hop']}, 关系: {r['relations']})")


async def test_hybrid_search(kb_id: int, query: str):
    """测试混合检索"""
    print(f"\n{'='*60}")
    print(f"4. 测试混合检索")
    print(f"{'='*60}")
    print(f"查询: {query}")
    
    hybrid_service = get_hybrid_retrieval_service()
    
    results = await hybrid_service.hybrid_search(
        kb_id=kb_id,
        query=query,
        top_k=5,
        enable_graph=True
    )
    
    print(f"\n检索结果数量: {len(results)}")
    for i, r in enumerate(results, 1):
        print(f"\n结果 {i}:")
        print(f"  来源: {r.get('source', 'unknown')}")
        print(f"  分数: {r.get('final_score', r.get('score', 0)):.3f}")
        print(f"  内容: {r['content'][:100]}...")


async def main():
    """主测试流程"""
    kb_id = 47  # 你的知识库ID
    test_query = "蟹堡的配方是什么"  # 测试查询（使用知识库中存在的实体）
    
    print("="*60)
    print("图谱检索诊断工具")
    print("="*60)
    
    # 1. 测试实体提取
    extracted_entities = await test_entity_extraction(test_query)
    
    # 2. 检查Neo4j中的实体
    neo4j_entities = test_neo4j_entities(kb_id)
    
    # 3. 如果有实体，测试查找
    if neo4j_entities:
        test_entity = neo4j_entities[0]['name']
        await test_entity_lookup(kb_id, test_entity)
    
    # 4. 测试完整的混合检索
    await test_hybrid_search(kb_id, test_query)
    
    print(f"\n{'='*60}")
    print("诊断完成")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
