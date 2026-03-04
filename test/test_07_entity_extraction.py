#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试7: 通用实体抽取增强逻辑测试（本地无外部依赖）"""

import sys
import json
from pathlib import Path

# 添加Backend到路径
backend_path = Path(__file__).parent.parent / "Backend"
sys.path.insert(0, str(backend_path))


class MockOllamaService:
    """Mock Ollama 服务，返回固定JSON。"""

    async def chat(self, model, messages, temperature=0.1, timeout=60, **kwargs):
        _ = (model, messages, temperature, timeout, kwargs)
        payload = {
            "text_types": ["设备说明书", "产品手册"],
            "entities": [
                {
                    "name": "电源键",
                    "canonical_name": "电源键",
                    "type": "关联对象",
                    "labels": ["关联对象", "按钮"],
                    "confidence": 0.96
                },
                {
                    "name": " 开机 ",
                    "canonical_name": "开机",
                    "type": "动作/行为",
                    "labels": ["动作/行为"],
                    "confidence": 0.91
                },
                {
                    "name": "不可识别要素",
                    "type": "未知类别",
                    "labels": ["未知类别"],
                    "confidence": 0.55
                }
            ],
            "relations": [
                {
                    "source": "电源键",
                    "target": "开机",
                    "relation": "执行/触发",
                    "confidence": 0.92
                }
            ],
            "unclassified": {
                "entities": [],
                "relations": []
            }
        }
        return json.dumps(payload, ensure_ascii=False)


def test_entity_extraction_enhanced():
    """测试抽取增强能力。"""
    print("\n1. 测试实体提取服务导入...")
    try:
        from app.services.entity_extraction_service import EntityExtractionService
        print("   ✓ EntityExtractionService 导入成功")
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        return False

    print("\n2. 测试extract_from_text增强输出...")
    try:
        import asyncio

        service = EntityExtractionService(ollama_service=MockOllamaService())
        result = asyncio.run(service.extract_from_text("点击电源键可开机", chunk_id="c1", min_length_override=1))

        entities = result.get("entities", [])
        relations = result.get("relations", [])

        if len(entities) < 2:
            print(f"   ❌ 实体数量异常: {len(entities)}")
            return False

        if not any("labels" in item and isinstance(item["labels"], list) for item in entities):
            print("   ❌ 未发现labels多标签字段")
            return False

        if not any(item.get("type") == "Unclassified" for item in entities):
            print("   ❌ 未分类桶映射未生效")
            return False

        if len(relations) != 1 or relations[0].get("relation") not in ["执行/触发", "related_to"]:
            print(f"   ❌ 关系解析异常: {relations}")
            return False

        print("   ✓ extract_from_text 输出符合预期")
    except Exception as e:
        print(f"   ❌ extract_from_text测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n3. 测试merge_extraction_results归一与聚合...")
    try:
        service = EntityExtractionService(ollama_service=MockOllamaService())
        merged_entities, merged_relations = service.merge_extraction_results([
            {
                "entities": [
                    {
                        "name": "电源键",
                        "canonical_name": "电源键",
                        "type": "关联对象",
                        "labels": ["关联对象"],
                        "confidence": 0.9,
                        "attributes": {"mention_count": 1},
                        "mention_count": 1,
                        "chunk_ids": ["c1"],
                        "aliases": ["开机键"]
                    },
                    {
                        "name": "开机键",
                        "canonical_name": "电源键",
                        "type": "关联对象",
                        "labels": ["关联对象"],
                        "confidence": 0.8,
                        "attributes": {"mention_count": 1},
                        "mention_count": 1,
                        "chunk_ids": ["c2"],
                        "aliases": ["电源键"]
                    }
                ],
                "relations": [
                    {
                        "source": "开机键",
                        "target": "电源键",
                        "relation": "执行/触发",
                        "confidence": 0.6,
                        "evidence_count": 1,
                        "chunk_ids": ["c2"],
                        "attributes": {}
                    }
                ]
            }
        ])

        if len(merged_entities) != 1:
            print(f"   ❌ 归一聚合失败，实体数={len(merged_entities)}")
            return False

        mention_count = merged_entities[0].get("attributes", {}).get("mention_count", 0)
        if mention_count < 2:
            print(f"   ❌ mention_count聚合异常: {mention_count}")
            return False

        if len(merged_relations) != 0:
            print("   ❌ 自环关系未被过滤")
            return False

        print("   ✓ merge_extraction_results 归一聚合正常")
    except Exception as e:
        print(f"   ❌ merge_extraction_results测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n✅ 实体抽取增强测试通过")
    return True


if __name__ == "__main__":
    success = test_entity_extraction_enhanced()
    exit(0 if success else 1)
