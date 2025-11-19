"""实体提取服务 - 基于Ollama云端大模型"""
import json
import asyncio
from typing import List, Dict, Any, Tuple, Optional
from app.services.ollama_llm_service import OllamaLLMService
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class EntityExtractionService:
    """实体提取服务 - 使用Ollama云端模型提取实体和关系"""
    
    def __init__(self, ollama_service: OllamaLLMService = None):
        """
        初始化实体提取服务
        
        Args:
            ollama_service: Ollama LLM服务实例
        """
        self.ollama = ollama_service or OllamaLLMService()
        self.config = settings.knowledge_graph.entity_extraction
        
        logger.info(f"实体提取服务初始化: model={self.config.ollama_model}, "
                   f"batch_size={self.config.batch_size}")
    
    def _build_extraction_prompt(self, text: str) -> str:
        """
        构建实体提取的Prompt
        
        Args:
            text: 输入文本
            
        Returns:
            Prompt字符串
        """
        prompt = f"""你是一个专业的知识图谱构建助手。请从以下文本中提取实体和关系。

文本内容：
{text}

提取要求：
1. 识别所有关键实体（人物、组织、地点、产品、概念、事件等）
2. 提取实体之间的语义关系
3. 确保实体名称准确完整，不要包含修饰词
4. 关系类型要具体明确（如：works_at, located_in, part_of, founded_by等）
5. 实体类型包括：Person（人物）、Organization（组织）、Location（地点）、Product（产品）、Concept（概念）、Event（事件）、Date（日期）

输出格式（必须是有效的JSON，不要有任何其他说明文字）：
{{
  "entities": [
    {{"name": "实体名称", "type": "实体类型"}},
    ...
  ],
  "relations": [
    {{"source": "源实体", "target": "目标实体", "relation": "关系类型"}},
    ...
  ]
}}

请只返回JSON，不要有任何其他说明文字。"""
        
        return prompt
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        解析Ollama返回的JSON响应
        
        Args:
            response: Ollama返回的文本
            
        Returns:
            解析后的字典
        """
        try:
            # 尝试直接解析
            data = json.loads(response)
            
            # 验证格式
            if not isinstance(data, dict):
                raise ValueError("响应不是字典格式")
            
            if 'entities' not in data or 'relations' not in data:
                logger.warning("响应缺少必要字段，返回空结果")
                return {'entities': [], 'relations': []}
            
            return data
            
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            try:
                # 查找JSON代码块
                if '```json' in response:
                    start = response.find('```json') + 7
                    end = response.find('```', start)
                    json_str = response[start:end].strip()
                elif '```' in response:
                    start = response.find('```') + 3
                    end = response.find('```', start)
                    json_str = response[start:end].strip()
                else:
                    # 查找第一个 { 和最后一个 }
                    start = response.find('{')
                    end = response.rfind('}') + 1
                    if start == -1 or end == 0:
                        raise ValueError("无法找到JSON内容")
                    json_str = response[start:end]
                
                data = json.loads(json_str)
                return data
                
            except Exception as e:
                logger.error(f"JSON解析失败: {str(e)}, response={response[:200]}...")
                return {'entities': [], 'relations': []}
    
    def _normalize_entities(self, entities: List[Dict]) -> List[Dict]:
        """
        实体标准化和去重
        
        Args:
            entities: 原始实体列表
            
        Returns:
            标准化后的实体列表
        """
        seen = set()
        normalized = []
        
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            
            name = entity.get('name', '').strip()
            entity_type = entity.get('type', 'Unknown').strip()
            
            # 过滤
            if not name or len(name) < settings.knowledge_graph.min_entity_length:
                continue
            
            # 去重
            key = (name, entity_type)
            if key in seen:
                continue
            
            seen.add(key)
            normalized.append({
                'name': name,
                'type': entity_type
            })
        
        return normalized
    
    def _normalize_relations(self, relations: List[Dict], valid_entities: set) -> List[Dict]:
        """
        关系标准化和过滤
        
        Args:
            relations: 原始关系列表
            valid_entities: 有效实体名称集合
            
        Returns:
            标准化后的关系列表
        """
        normalized = []
        seen = set()
        
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            
            source = relation.get('source', '').strip()
            target = relation.get('target', '').strip()
            rel_type = relation.get('relation', 'related_to').strip()
            
            # 过滤：确保两端实体都存在
            if not source or not target or source == target:
                continue
            
            # 只保留有效实体间的关系
            if source not in valid_entities or target not in valid_entities:
                continue
            
            # 去重
            key = (source, target, rel_type)
            if key in seen:
                continue
            
            seen.add(key)
            normalized.append({
                'source': source,
                'target': target,
                'relation': rel_type
            })
        
        return normalized
    
    async def extract_from_text(
        self,
        text: str,
        chunk_id: Optional[str] = None,
        min_length_override: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        从单个文本块提取实体和关系
        
        Args:
            text: 文本内容
            chunk_id: 文本块ID（用于溯源）
            min_length_override: 覆盖最小文本长度（用于短查询）
            
        Returns:
            提取结果 {'entities': [...], 'relations': [...], 'chunk_id': '...'}
        """
        try:
            # 检查文本长度
            min_length = min_length_override if min_length_override is not None else self.config.min_text_length
            if len(text) < min_length:
                logger.warning(f"文本过短，跳过提取: length={len(text)}, min={min_length}")
                return {'entities': [], 'relations': [], 'chunk_id': chunk_id}
            
            # 构建Prompt
            prompt = self._build_extraction_prompt(text)
            logger.debug(f"实体提取prompt: {prompt[:200]}...")
            
            # 调用Ollama
            messages = [{"role": "user", "content": prompt}]
            
            response = await self.ollama.chat(
                model=self.config.ollama_model,
                messages=messages,
                temperature=self.config.temperature
            )
            
            logger.debug(f"Ollama原始响应: {response[:500]}...")
            
            # 解析结果
            data = self._parse_json_response(response)
            
            logger.info(f"解析结果: entities={len(data.get('entities', []))}, relations={len(data.get('relations', []))}")
            
            # 标准化实体
            entities = self._normalize_entities(data.get('entities', []))
            
            # 标准化关系
            valid_entity_names = {e['name'] for e in entities}
            relations = self._normalize_relations(
                data.get('relations', []),
                valid_entity_names
            )
            
            result = {
                'entities': entities,
                'relations': relations,
                'chunk_id': chunk_id
            }
            
            logger.debug(f"提取完成: entities={len(entities)}, relations={len(relations)}")
            return result
            
        except Exception as e:
            logger.error(f"实体提取失败: {str(e)}")
            return {'entities': [], 'relations': [], 'chunk_id': chunk_id}
    
    async def batch_extract(
        self,
        texts: List[Tuple[str, Optional[str]]],
        concurrency: int = None
    ) -> List[Dict[str, Any]]:
        """
        批量并发提取实体和关系
        
        Args:
            texts: 文本列表 [(text, chunk_id), ...]
            concurrency: 并发数量
            
        Returns:
            提取结果列表
        """
        if not texts:
            return []
        
        concurrency = concurrency or self.config.batch_size
        
        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(concurrency)
        
        async def extract_with_limit(text: str, chunk_id: Optional[str]):
            async with semaphore:
                return await self.extract_from_text(text, chunk_id)
        
        # 创建任务
        tasks = [extract_with_limit(text, chunk_id) for text, chunk_id in texts]
        
        # 执行并收集结果
        logger.info(f"开始批量提取: total={len(texts)}, concurrency={concurrency}")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤错误结果
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"任务{i}失败: {str(result)}")
                valid_results.append({'entities': [], 'relations': [], 'chunk_id': texts[i][1]})
            else:
                valid_results.append(result)
        
        total_entities = sum(len(r['entities']) for r in valid_results)
        total_relations = sum(len(r['relations']) for r in valid_results)
        
        logger.info(f"批量提取完成: entities={total_entities}, relations={total_relations}")
        
        return valid_results
    
    def merge_extraction_results(
        self,
        results: List[Dict[str, Any]]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        合并多个提取结果，去重
        
        Args:
            results: 提取结果列表
            
        Returns:
            (合并后的实体列表, 合并后的关系列表)
        """
        all_entities = []
        all_relations = []
        
        for result in results:
            all_entities.extend(result.get('entities', []))
            all_relations.extend(result.get('relations', []))
        
        # 实体去重
        entity_dict = {}
        for entity in all_entities:
            key = (entity['name'], entity['type'])
            if key not in entity_dict:
                entity_dict[key] = entity
        
        unique_entities = list(entity_dict.values())
        
        # 关系去重
        relation_set = set()
        unique_relations = []
        for relation in all_relations:
            key = (relation['source'], relation['target'], relation['relation'])
            if key not in relation_set:
                relation_set.add(key)
                unique_relations.append(relation)
        
        logger.info(f"结果合并完成: entities={len(unique_entities)}, relations={len(unique_relations)}")
        
        return unique_entities, unique_relations


# 全局单例
_entity_extraction_service_instance = None


def get_entity_extraction_service() -> EntityExtractionService:
    """获取实体提取服务单例"""
    global _entity_extraction_service_instance
    if _entity_extraction_service_instance is None:
        _entity_extraction_service_instance = EntityExtractionService()
    return _entity_extraction_service_instance
