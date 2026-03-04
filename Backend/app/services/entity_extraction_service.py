"""实体提取服务 - 基于Ollama模型的通用实体关系抽取"""
import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.config import settings
from app.services.ollama_llm_service import OllamaLLMService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class EntityExtractionService:
    """实体提取服务 - 通用实体/关系抽取与归一化"""

    def __init__(self, ollama_service: OllamaLLMService = None):
        self.ollama = ollama_service or OllamaLLMService()
        self.config = settings.knowledge_graph.entity_extraction
        self.min_entity_length = settings.knowledge_graph.min_entity_length

        logger.info(
            "实体提取服务初始化: model=%s, batch_size=%s, schema=%s",
            self.config.ollama_model,
            self.config.batch_size,
            self.config.schema_version
        )

    def _build_extraction_prompt(self, text: str) -> str:
        """构建全场景通用抽取提示词。"""
        return f"""你是一个通用知识图谱抽取助手。请对任意文本提取实体与关系，并严格输出JSON。

任务要求：
1) 先识别文本类型（可多标签）;
2) 抽取实体和关系;
3) 输出必须是合法JSON，不要输出额外说明。

通用实体语义类型（优先使用以下标签，可多标签）：
- 主体
- 动作/行为
- 属性/特征
- 关联对象
- 约束/规则

通用关系语义类型（优先使用以下标签）：
- 隶属/组成
- 执行/触发
- 描述/修饰
- 约束/限制
- 时空/因果

补充要求：
- 每个实体必须包含：name, canonical_name, type, labels, confidence。
- 每条关系必须包含：source, target, relation, confidence。
- 若无法明确分类，type或relation填入 Unclassified/related_to。
- confidence取值0到1。

输出JSON结构（字段不可缺失，无内容用空数组）：
{{
  "text_types": ["文本类型1", "文本类型2"],
  "entities": [
    {{
      "name": "原始实体名",
      "canonical_name": "归一化实体名",
      "type": "主标签",
      "labels": ["标签1", "标签2"],
      "confidence": 0.0,
      "attributes": {{}}
    }}
  ],
  "relations": [
    {{
      "source": "实体A",
      "target": "实体B",
      "relation": "关系类型",
      "confidence": 0.0,
      "attributes": {{}}
    }}
  ],
  "unclassified": {{
    "entities": [],
    "relations": []
  }}
}}

待处理文本：
{text}
"""

    def _normalize_name(self, name: str) -> str:
        normalized_name = re.sub(r"\s+", " ", (name or "").strip())
        normalized_name = normalized_name.replace("（", "(").replace("）", ")")
        return normalized_name

    def _clamp_confidence(self, value: Any, default_value: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default_value
        return max(0.0, min(1.0, parsed))

    def _extract_json_block(self, raw_response: str) -> str:
        if "```json" in raw_response:
            start = raw_response.find("```json") + 7
            end = raw_response.find("```", start)
            return raw_response[start:end].strip()

        if "```" in raw_response:
            start = raw_response.find("```") + 3
            end = raw_response.find("```", start)
            return raw_response[start:end].strip()

        start = raw_response.find("{")
        end = raw_response.rfind("}") + 1
        if start == -1 or end <= 0:
            raise ValueError("响应中未找到JSON")
        return raw_response[start:end]

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        default_payload = {
            "text_types": [],
            "entities": [],
            "relations": [],
            "unclassified": {"entities": [], "relations": []}
        }

        try:
            payload = json.loads(response)
        except json.JSONDecodeError:
            try:
                payload = json.loads(self._extract_json_block(response))
            except Exception as error:
                logger.error("JSON解析失败: %s", str(error))
                return default_payload

        if not isinstance(payload, dict):
            return default_payload

        entities = payload.get("entities") or payload.get("实体列表") or []
        relations = payload.get("relations") or payload.get("关系列表") or []

        unclassified = payload.get("unclassified")
        if not isinstance(unclassified, dict):
            unclassified = {"entities": [], "relations": []}

        text_types = payload.get("text_types") or payload.get("文本类型") or []
        if isinstance(text_types, str):
            text_types = [text_types]

        return {
            "text_types": text_types,
            "entities": entities if isinstance(entities, list) else [],
            "relations": relations if isinstance(relations, list) else [],
            "unclassified": {
                "entities": unclassified.get("entities", []) if isinstance(unclassified.get("entities", []), list) else [],
                "relations": unclassified.get("relations", []) if isinstance(unclassified.get("relations", []), list) else []
            }
        }

    def _normalize_entity_labels(self, raw_type: str, raw_labels: Any) -> List[str]:
        labels: List[str] = []

        if isinstance(raw_labels, list):
            labels.extend(str(item).strip() for item in raw_labels if str(item).strip())
        elif isinstance(raw_labels, str) and raw_labels.strip():
            labels.append(raw_labels.strip())

        if raw_type:
            labels.append(raw_type)

        deduplicated_labels: List[str] = []
        for label in labels:
            if label and label not in deduplicated_labels:
                deduplicated_labels.append(label)

        if not self.config.enable_multilabel and deduplicated_labels:
            return [deduplicated_labels[0]]

        return deduplicated_labels

    def _resolve_entity_type(self, labels: List[str]) -> Tuple[str, List[str]]:
        valid_types = set(self.config.valid_entity_types or [])
        unknown_type = self.config.unknown_entity_type

        if not labels:
            return unknown_type, [unknown_type]

        if not valid_types:
            return labels[0], labels

        valid_labels = [item for item in labels if item in valid_types]

        if valid_labels:
            return valid_labels[0], valid_labels

        if self.config.enable_unknown_bucket:
            return unknown_type, [unknown_type]

        return labels[0], labels

    def _apply_alias_map(self, value: str) -> str:
        alias_map = getattr(self.config, "alias_map", {}) or {}
        return alias_map.get(value, value)

    def _normalize_entity_item(self, item: Dict[str, Any], chunk_id: Optional[str]) -> Optional[Dict[str, Any]]:
        raw_name = item.get("name") or item.get("名称")
        raw_type = (item.get("type") or item.get("类型") or "").strip()

        if not raw_name:
            return None

        entity_name = self._normalize_name(str(raw_name))
        if len(entity_name) < self.min_entity_length:
            return None

        raw_canonical_name = item.get("canonical_name") or item.get("规范名") or ""
        canonical_name = self._normalize_name(str(raw_canonical_name)) if raw_canonical_name else ""

        if self.config.llm_normalization_priority and canonical_name:
            resolved_name = canonical_name
        else:
            resolved_name = self._normalize_name(entity_name)

        resolved_name = self._apply_alias_map(resolved_name)

        labels = self._normalize_entity_labels(raw_type, item.get("labels") or item.get("标签"))
        primary_type, labels = self._resolve_entity_type(labels)

        confidence = self._clamp_confidence(item.get("confidence"), 0.7)

        attributes = item.get("attributes") or item.get("属性") or {}
        if not isinstance(attributes, dict):
            attributes = {}

        aliases: List[str] = []
        if item.get("aliases") and isinstance(item.get("aliases"), list):
            aliases.extend(self._normalize_name(str(alias)) for alias in item.get("aliases") if str(alias).strip())
        if entity_name and entity_name != resolved_name:
            aliases.append(entity_name)

        unique_aliases: List[str] = []
        for alias in aliases:
            if alias and alias not in unique_aliases:
                unique_aliases.append(alias)

        return {
            "name": resolved_name,
            "canonical_name": resolved_name,
            "type": primary_type,
            "labels": labels,
            "confidence": confidence,
            "attributes": attributes,
            "mention_count": 1,
            "chunk_ids": [chunk_id] if chunk_id else [],
            "aliases": unique_aliases
        }

    def _normalize_relation_item(
        self,
        item: Dict[str, Any],
        chunk_id: Optional[str],
        alias_to_canonical: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        source_value = item.get("source") or item.get("主体")
        target_value = item.get("target") or item.get("客体")
        relation_value = item.get("relation") or item.get("关系") or self.config.unknown_relation_type

        if not source_value or not target_value:
            return None

        source_name = self._normalize_name(str(source_value))
        target_name = self._normalize_name(str(target_value))

        source_name = alias_to_canonical.get(source_name, self._apply_alias_map(source_name))
        target_name = alias_to_canonical.get(target_name, self._apply_alias_map(target_name))

        if not source_name or not target_name or source_name == target_name:
            return None

        relation_name = self._normalize_name(str(relation_value)) or self.config.unknown_relation_type
        valid_relation_types = set(self.config.valid_relation_types or [])
        if valid_relation_types and relation_name not in valid_relation_types and self.config.enable_unknown_bucket:
            relation_name = self.config.unknown_relation_type

        confidence = self._clamp_confidence(item.get("confidence"), 0.6)

        attributes = item.get("attributes") or item.get("属性") or {}
        if not isinstance(attributes, dict):
            attributes = {}

        return {
            "source": source_name,
            "target": target_name,
            "relation": relation_name,
            "confidence": confidence,
            "evidence_count": 1,
            "chunk_ids": [chunk_id] if chunk_id else [],
            "attributes": attributes
        }

    async def extract_from_text(
        self,
        text: str,
        chunk_id: Optional[str] = None,
        min_length_override: Optional[int] = None
    ) -> Dict[str, Any]:
        """从单个文本块提取实体和关系。"""
        try:
            min_length = min_length_override if min_length_override is not None else self.config.min_text_length
            if len(text or "") < min_length:
                return {
                    "text_types": [],
                    "entities": [],
                    "relations": [],
                    "chunk_id": chunk_id,
                    "unclassified": {"entities": [], "relations": []}
                }

            prompt = self._build_extraction_prompt(text)
            messages = [{"role": "user", "content": prompt}]

            response_text = None
            last_error = None
            max_retries = max(1, int(getattr(self.config, "max_retries", 1) or 1))
            timeout = int(getattr(self.config, "timeout", 300) or 300)
            max_tokens = int(getattr(self.config, "max_tokens", 512) or 512)
            start_time = time.perf_counter()

            for attempt_index in range(1, max_retries + 1):
                try:
                    response_text = await self.ollama.chat(
                        model=self.config.ollama_model,
                        messages=messages,
                        temperature=self.config.temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        response_format="json"
                    )
                    break
                except Exception as error:
                    last_error = error
                    logger.warning(
                        "实体提取调用失败: attempt=%s/%s, error=%s",
                        attempt_index,
                        max_retries,
                        str(error)
                    )
                    if attempt_index < max_retries:
                        await asyncio.sleep(min(2 ** (attempt_index - 1), 4))

            if response_text is None:
                raise RuntimeError(f"实体提取重试失败: {str(last_error)}")

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info(
                "实体提取完成: chunk_id=%s, text_len=%s, elapsed_ms=%s",
                chunk_id,
                len(text or ""),
                elapsed_ms
            )

            parsed = self._parse_json_response(response_text)

            normalized_entities: List[Dict[str, Any]] = []
            alias_to_canonical: Dict[str, str] = {}

            for raw_entity in parsed.get("entities", []):
                if not isinstance(raw_entity, dict):
                    continue
                entity_item = self._normalize_entity_item(raw_entity, chunk_id)
                if not entity_item:
                    continue

                normalized_entities.append(entity_item)
                alias_to_canonical[entity_item["name"]] = entity_item["name"]
                for alias in entity_item.get("aliases", []):
                    alias_to_canonical[alias] = entity_item["name"]

            valid_entity_names: Set[str] = {item["name"] for item in normalized_entities}

            normalized_relations: List[Dict[str, Any]] = []
            for raw_relation in parsed.get("relations", []):
                if not isinstance(raw_relation, dict):
                    continue
                relation_item = self._normalize_relation_item(raw_relation, chunk_id, alias_to_canonical)
                if not relation_item:
                    continue
                if relation_item["source"] not in valid_entity_names or relation_item["target"] not in valid_entity_names:
                    continue
                normalized_relations.append(relation_item)

            unclassified_entities = [
                item["name"]
                for item in normalized_entities
                if item.get("type") == self.config.unknown_entity_type
            ]
            unclassified_relations = [
                item["relation"]
                for item in normalized_relations
                if item.get("relation") == self.config.unknown_relation_type
            ]

            return {
                "text_types": parsed.get("text_types", []),
                "entities": normalized_entities,
                "relations": normalized_relations,
                "chunk_id": chunk_id,
                "unclassified": {
                    "entities": unclassified_entities,
                    "relations": unclassified_relations
                }
            }

        except Exception as error:
            logger.error("实体提取失败: %s", str(error))
            return {
                "text_types": [],
                "entities": [],
                "relations": [],
                "chunk_id": chunk_id,
                "unclassified": {"entities": [], "relations": []}
            }

    async def batch_extract(
        self,
        texts: List[Tuple[str, Optional[str]]],
        concurrency: int = None
    ) -> List[Dict[str, Any]]:
        """批量并发提取实体和关系。"""
        if not texts:
            return []

        concurrency_limit = concurrency or self.config.batch_size
        semaphore = asyncio.Semaphore(concurrency_limit)

        async def extract_with_limit(text_item: str, chunk_identifier: Optional[str]):
            async with semaphore:
                return await self.extract_from_text(text_item, chunk_identifier)

        tasks = [extract_with_limit(text_item, chunk_identifier) for text_item, chunk_identifier in texts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        normalized_results: List[Dict[str, Any]] = []
        for index, result_item in enumerate(results):
            if isinstance(result_item, Exception):
                logger.error("任务%s失败: %s", index, str(result_item))
                normalized_results.append({
                    "text_types": [],
                    "entities": [],
                    "relations": [],
                    "chunk_id": texts[index][1],
                    "unclassified": {"entities": [], "relations": []}
                })
            else:
                normalized_results.append(result_item)

        return normalized_results

    def merge_extraction_results(self, results: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        """合并多个提取结果并去重聚合。"""
        all_entities: List[Dict[str, Any]] = []
        all_relations: List[Dict[str, Any]] = []

        for result_item in results:
            all_entities.extend(result_item.get("entities", []))
            all_relations.extend(result_item.get("relations", []))

        entity_dict: Dict[str, Dict[str, Any]] = {}

        for entity_item in all_entities:
            canonical_name = self._normalize_name(entity_item.get("canonical_name") or entity_item.get("name"))
            if not canonical_name:
                continue

            existing = entity_dict.get(canonical_name)
            if not existing:
                entity_dict[canonical_name] = {
                    "name": canonical_name,
                    "canonical_name": canonical_name,
                    "type": entity_item.get("type") or self.config.unknown_entity_type,
                    "labels": list(entity_item.get("labels") or [entity_item.get("type") or self.config.unknown_entity_type]),
                    "confidence": self._clamp_confidence(entity_item.get("confidence"), 0.7),
                    "mention_count": int(entity_item.get("mention_count", 1) or 1),
                    "chunk_ids": set(entity_item.get("chunk_ids", [])),
                    "aliases": set(entity_item.get("aliases", [])),
                    "attributes": dict(entity_item.get("attributes", {}) or {})
                }
                continue

            existing["mention_count"] += int(entity_item.get("mention_count", 1) or 1)
            existing["confidence"] = max(
                self._clamp_confidence(existing.get("confidence"), 0.7),
                self._clamp_confidence(entity_item.get("confidence"), 0.7)
            )

            current_labels = set(existing.get("labels", []))
            current_labels.update(entity_item.get("labels", []))
            existing["labels"] = list(current_labels)

            existing["chunk_ids"].update(entity_item.get("chunk_ids", []))
            existing["aliases"].update(entity_item.get("aliases", []))

            incoming_type = entity_item.get("type")
            if existing.get("type") == self.config.unknown_entity_type and incoming_type:
                existing["type"] = incoming_type

            incoming_attributes = entity_item.get("attributes", {}) or {}
            if isinstance(incoming_attributes, dict):
                for key, value in incoming_attributes.items():
                    if key not in existing["attributes"]:
                        existing["attributes"][key] = value

        alias_to_canonical: Dict[str, str] = {}
        for canonical_name, entity_item in entity_dict.items():
            alias_to_canonical[canonical_name] = canonical_name
            for alias_name in entity_item.get("aliases", set()):
                normalized_alias = self._normalize_name(str(alias_name))
                if normalized_alias:
                    alias_to_canonical[normalized_alias] = canonical_name

        relation_dict: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        for relation_item in all_relations:
            source_name = self._normalize_name(relation_item.get("source", ""))
            target_name = self._normalize_name(relation_item.get("target", ""))

            source_name = alias_to_canonical.get(source_name, self._apply_alias_map(source_name))
            target_name = alias_to_canonical.get(target_name, self._apply_alias_map(target_name))

            relation_name = self._normalize_name(relation_item.get("relation") or self.config.unknown_relation_type)
            if not relation_name:
                relation_name = self.config.unknown_relation_type

            if source_name not in entity_dict or target_name not in entity_dict or source_name == target_name:
                continue

            relation_key = (source_name, target_name, relation_name)
            existing_relation = relation_dict.get(relation_key)

            if not existing_relation:
                relation_dict[relation_key] = {
                    "source": source_name,
                    "target": target_name,
                    "relation": relation_name,
                    "confidence": self._clamp_confidence(relation_item.get("confidence"), 0.6),
                    "evidence_count": int(relation_item.get("evidence_count", 1) or 1),
                    "chunk_ids": set(relation_item.get("chunk_ids", [])),
                    "attributes": dict(relation_item.get("attributes", {}) or {})
                }
                continue

            existing_relation["confidence"] = max(
                self._clamp_confidence(existing_relation.get("confidence"), 0.6),
                self._clamp_confidence(relation_item.get("confidence"), 0.6)
            )
            existing_relation["evidence_count"] += int(relation_item.get("evidence_count", 1) or 1)
            existing_relation["chunk_ids"].update(relation_item.get("chunk_ids", []))

            incoming_relation_attrs = relation_item.get("attributes", {}) or {}
            if isinstance(incoming_relation_attrs, dict):
                for key, value in incoming_relation_attrs.items():
                    if key not in existing_relation["attributes"]:
                        existing_relation["attributes"][key] = value

        unique_entities: List[Dict[str, Any]] = []
        for entity_item in entity_dict.values():
            labels = entity_item.get("labels", [])
            if self.config.unknown_entity_type not in labels and entity_item.get("type") == self.config.unknown_entity_type:
                labels.append(self.config.unknown_entity_type)

            unique_entities.append({
                "name": entity_item["name"],
                "canonical_name": entity_item["canonical_name"],
                "type": entity_item["type"] if self.config.keep_legacy_type_field else labels[0],
                "labels": labels,
                "confidence": round(float(entity_item.get("confidence", 0.7)), 4),
                "attributes": {
                    **entity_item.get("attributes", {}),
                    "mention_count": int(entity_item.get("mention_count", 1)),
                    "chunk_ids": sorted(list(entity_item.get("chunk_ids", set()))),
                    "aliases": sorted(list(entity_item.get("aliases", set())))
                }
            })

        unique_relations: List[Dict[str, Any]] = []
        for relation_item in relation_dict.values():
            unique_relations.append({
                "source": relation_item["source"],
                "target": relation_item["target"],
                "relation": relation_item["relation"],
                "confidence": round(float(relation_item.get("confidence", 0.6)), 4),
                "evidence_count": int(relation_item.get("evidence_count", 1)),
                "chunk_ids": sorted(list(relation_item.get("chunk_ids", set()))),
                "attributes": relation_item.get("attributes", {})
            })

        unique_entities.sort(key=lambda item: item.get("attributes", {}).get("mention_count", 0), reverse=True)
        unique_relations.sort(key=lambda item: item.get("evidence_count", 0), reverse=True)

        logger.info("结果合并完成: entities=%s, relations=%s", len(unique_entities), len(unique_relations))
        return unique_entities, unique_relations


_entity_extraction_service_instance = None


def get_entity_extraction_service() -> EntityExtractionService:
    """获取实体提取服务单例。"""
    global _entity_extraction_service_instance
    if _entity_extraction_service_instance is None:
        _entity_extraction_service_instance = EntityExtractionService()
    return _entity_extraction_service_instance
