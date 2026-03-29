"""实体提取服务 - 基于 ZAI/OLLAMA 的通用实体关系抽取"""
import asyncio
import copy
import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import httpx

from app.core.config import settings
from app.services.infrastructure.llm.ollama_llm_service import OllamaLLMService
from app.utils.logger import get_logger

try:
    from zai import ZhipuAiClient
except Exception:  # pragma: no cover - 环境未安装时允许回退
    ZhipuAiClient = None

logger = get_logger(__name__)


class EntityExtractionService:
    """实体提取服务 - 通用实体/关系抽取与归一化"""

    def __init__(self, ollama_service: OllamaLLMService = None):
        self.ollama = ollama_service or OllamaLLMService()
        self.config = settings.knowledge_graph.entity_extraction
        self.min_entity_length = settings.knowledge_graph.min_entity_length
        # 强制避免使用 DeepSeek 思考模型，防止结构化抽取出现不可控长推理输出。
        self._ensure_non_reasoning_deepseek_model()
        self.requested_provider = (self.config.provider or "zai").lower()
        self.provider = self.requested_provider
        self.zai_client = self._build_zai_client()
        self.deepseek_available = self._has_deepseek_credentials()
        if self.requested_provider == "deepseek" and not self.deepseek_available:
            logger.warning("未配置 DEEPSEEK_API_KEY，将回退到 Ollama")
            self.provider = "ollama"
        if self.requested_provider == "zai" and self.zai_client is None:
            self.provider = "ollama"

        self._cache_lock = asyncio.Lock()
        self._cache_map: Dict[str, Dict[str, Any]] = {}
        self._cache_file = Path(self.config.extraction_cache_file)
        self._load_extraction_cache()

        logger.info(
            "实体提取服务初始化: requested_provider=%s, effective_provider=%s, deepseek_model=%s, zai_model=%s, ollama_model=%s, batch_size=%s",
            self.requested_provider,
            self.provider,
            self.config.deepseek_model,
            self.config.zai_model,
            self.config.ollama_model,
            self.config.batch_size,
        )

    def _ensure_non_reasoning_deepseek_model(self) -> None:
        model_name = str(getattr(self.config, "deepseek_model", "") or "").strip().lower()
        if not model_name:
            return

        reasoning_markers = ("reasoner", "deepseek-r1", "-r1", "r1-")
        if any(marker in model_name for marker in reasoning_markers):
            logger.warning(
                "检测到 DeepSeek 思考模型(%s)，实体抽取将强制切换到 deepseek-chat",
                self.config.deepseek_model,
            )
            self.config.deepseek_model = "deepseek-chat"

    def _has_deepseek_credentials(self) -> bool:
        return bool(str(getattr(self.config, "deepseek_api_key", "") or "").strip())

    def _build_zai_client(self):
        if self.requested_provider != "zai":
            return None
        if ZhipuAiClient is None:
            logger.warning("zai-sdk 不可用，将回退到 Ollama")
            return None
        if not self.config.zai_api_key:
            logger.warning("未配置 ZAI_API_KEY/ZHIPU_API_KEY，将回退到 Ollama")
            return None
        try:
            return ZhipuAiClient(
                api_key=self.config.zai_api_key,
                base_url=self.config.zai_base_url,
                max_retries=max(1, int(self.config.max_retries or 1)),
            )
        except Exception as error:
            logger.error("初始化 ZAI 客户端失败: %s", str(error))
            return None

    def _normalize_name(self, name: str) -> str:
        return " ".join(str(name or "").strip().split())

    def _truncate_for_log(self, text: str, limit: int = 280) -> str:
        raw = str(text or "").replace("\n", " ").replace("\r", " ").strip()
        if len(raw) <= limit:
            return raw
        return raw[:limit] + "..."

    def _clamp_confidence(self, value: Any, default_value: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default_value
        return max(0.0, min(1.0, parsed))

    def _cache_key(self, text: str, stage: str = "extract") -> str:
        text_hash = hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()
        if self.provider == "zai":
            active_model = self.config.zai_model
        elif self.provider == "deepseek":
            active_model = self.config.deepseek_model
        else:
            active_model = self.config.ollama_model
        return f"{stage}:{self.provider}:{active_model}:{self.config.prompt_version}:{text_hash}"

    def _load_extraction_cache(self) -> None:
        if not self.config.extraction_cache_enabled:
            return
        try:
            if not self._cache_file.exists():
                self._cache_file.parent.mkdir(parents=True, exist_ok=True)
                return

            now = datetime.utcnow()
            ttl = timedelta(hours=max(1, int(self.config.extraction_cache_ttl_hours or 1)))
            total_lines = 0

            with self._cache_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    total_lines += 1
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    key = payload.get("key")
                    cached_at_raw = payload.get("cached_at")
                    if not key or not cached_at_raw:
                        continue

                    try:
                        cached_at = datetime.fromisoformat(cached_at_raw)
                    except ValueError:
                        continue

                    if now - cached_at > ttl:
                        continue

                    value = payload.get("value")
                    if isinstance(value, dict):
                        self._cache_map[key] = {
                            "cached_at": cached_at_raw,
                            "value": value,
                        }

            # 自动 compact：如果文件行数远超有效条目，重写文件去除过期/损坏行
            evicted = total_lines - len(self._cache_map)
            if evicted > 200 or (total_lines > 0 and evicted > total_lines * 0.3):
                self._compact_cache_file()

            logger.info("抽取缓存加载完成: entries=%s, evicted=%s", len(self._cache_map), evicted)
        except Exception as error:
            logger.warning("加载抽取缓存失败: %s", str(error))

    def _compact_cache_file(self) -> None:
        """重写缓存文件，只保留内存中的有效条目。"""
        try:
            tmp_path = self._cache_file.with_suffix(".jsonl.tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                for key, item in self._cache_map.items():
                    payload = {
                        "key": key,
                        "cached_at": item.get("cached_at"),
                        "value": item.get("value"),
                    }
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            tmp_path.replace(self._cache_file)
            logger.info("抽取缓存compact完成: 保留 %s 条", len(self._cache_map))
        except Exception as error:
            logger.warning("抽取缓存compact失败: %s", str(error))

    def _is_empty_extraction_payload(self, value: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(value, dict):
            return True

        entities = value.get("entities") or []
        relations = value.get("relations") or []
        if entities or relations:
            return False

        metrics = value.get("metrics") if isinstance(value.get("metrics"), dict) else {}
        raw_entity_count = int(metrics.get("raw_entity_count", 0) or 0)
        raw_relation_count = int(metrics.get("raw_relation_count", 0) or 0)
        return raw_entity_count == 0 and raw_relation_count == 0

    async def _append_cache(self, key: str, value: Dict[str, Any]) -> None:
        if not self.config.extraction_cache_enabled:
            return
        if self._is_empty_extraction_payload(value):
            return
        payload = {
            "key": key,
            "cached_at": datetime.utcnow().isoformat(),
            "value": value,
        }
        async with self._cache_lock:
            self._cache_map[key] = {"cached_at": payload["cached_at"], "value": value}
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with self._cache_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.config.extraction_cache_enabled:
            return None
        item = self._cache_map.get(key)
        if not item:
            return None
        value = item.get("value")
        if self._is_empty_extraction_payload(value):
            return None
        return copy.deepcopy(value) if isinstance(value, dict) else None

    def _bind_chunk_context(self, payload: Dict[str, Any], chunk_id: Optional[str]) -> Dict[str, Any]:
        """将缓存结果绑定到当前 chunk，避免跨 chunk 复用时证据串位。"""
        bound = copy.deepcopy(payload or {})
        bound["chunk_id"] = chunk_id

        target_chunk_ids = [chunk_id] if chunk_id else []
        for entity in bound.get("entities", []) or []:
            if isinstance(entity, dict):
                entity["chunk_ids"] = list(target_chunk_ids)
                attrs = entity.get("attributes")
                if isinstance(attrs, dict):
                    attrs["chunk_ids"] = list(target_chunk_ids)

        for relation in bound.get("relations", []) or []:
            if isinstance(relation, dict):
                relation["chunk_ids"] = list(target_chunk_ids)

        return bound

    def _build_extraction_prompt(self, text: str) -> str:
                max_entities = max(8, int(getattr(self.config, "max_entities_per_chunk", 40) or 40))
                max_triples = max(8, int(getattr(self.config, "max_triples_per_chunk", 60) or 60))
                prompt = """
你是一个严格的JSON信息抽取器。请从文本中抽取实体与关系，并且只返回可被 json.loads 直接解析的 JSON 对象。

硬性约束（必须全部满足）：
1. 只能输出一个 JSON 对象；禁止 Markdown 代码块、禁止解释、禁止前后缀文字。
2. 顶层仅允许 3 个键：entities, triples, entity_attributes。不得新增其他键。
3. 所有键名必须使用双引号；字符串值必须使用双引号；禁止单引号。
4. 禁止尾逗号；禁止注释；禁止 NaN/Infinity；禁止省略引号。
5. confidence 必须是 0 到 1 的数字。
6. triples 中 head/tail 必须来自 entities。若无法确定关系，triples 返回空数组。
7. 抽取不到内容时返回空结构，不要编造。
8. 结果必须精简：仅保留最关键的信息，避免冗长枚举。

输出 JSON Schema（语义约束）：
{
    "entities": ["string"],
    "triples": [
        {
            "head": "string",
            "relation": "string",
            "tail": "string",
            "attributes": {},
            "confidence": 0.0
        }
    ],
    "entity_attributes": [
        {
            "entity": "string",
            "attributes": {}
        }
    ]
}

示例（无可抽取关系时）：
{"entities":["实体A"],"triples":[],"entity_attributes":[{"entity":"实体A","attributes":{}}]}

如果你即将输出任何非JSON内容，请停止并改为仅输出合法JSON。
"""
                return (
                    f"{prompt}\n"
                    f"数量限制：entities 最多 {max_entities} 项；triples 最多 {max_triples} 项。\n"
                    f"超过限制时，请按对问题最有用的优先级保留。\n"
                    f"待抽取文本：\n{text}"
                )

    def _build_json_repair_prompt(self, raw_json_text: str) -> str:
        """将近似JSON修复为合法JSON，结构限定为抽取协议。"""
        return (
            "你是JSON修复器。将下面内容修复为可被 json.loads 解析的单个 JSON 对象。\n"
            "只允许顶层键：entities, triples, entity_attributes。\n"
            "禁止输出任何解释、Markdown、代码块。\n"
            "若某字段无法修复，使用空数组。\n"
            "输出必须是严格JSON。\n\n"
            f"待修复内容：\n{raw_json_text}"
        )

    def _local_json_repair(self, text: str) -> Optional[str]:
        """本地 regex 修复常见 JSON 错误，避免不必要的 LLM 调用。"""
        import re as _re

        if not text or not text.strip():
            return None

        fixed = text.strip()
        # 提取 JSON 块
        if "```json" in fixed:
            start = fixed.find("```json") + 7
            end = fixed.find("```", start)
            if end > start:
                fixed = fixed[start:end].strip()
        elif "```" in fixed:
            start = fixed.find("```") + 3
            end = fixed.find("```", start)
            if end > start:
                fixed = fixed[start:end].strip()
        else:
            brace_start = fixed.find("{")
            brace_end = fixed.rfind("}")
            if brace_start >= 0 and brace_end > brace_start:
                fixed = fixed[brace_start:brace_end + 1]

        # 移除尾逗号: ,} -> }  ,] -> ]
        fixed = _re.sub(r',\s*([}\]])', r'\1', fixed)
        # 修复单引号为双引号（键 + 值 + 数组元素）
        fixed = _re.sub(r"(?<=[\[{,])\s*'([^']+)'\s*:", r' "\1":', fixed)
        fixed = _re.sub(r":\s*'([^']*)'", r': "\1"', fixed)
        fixed = _re.sub(r"(?<=[\[,])\s*'([^']*)'\s*(?=[,\]])", r' "\1"', fixed)
        # 移除 NaN/Infinity
        fixed = _re.sub(r'\bNaN\b', '0', fixed)
        fixed = _re.sub(r'\bInfinity\b', '1', fixed)

        try:
            json.loads(fixed)
            return fixed
        except json.JSONDecodeError:
            return None

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

    def _parse_llm_json(self, response: str) -> Dict[str, Any]:
        default_payload = {
            "entities": [],
            "triples": [],
            "entity_attributes": [],
            "entity_types": {},
            "relation_types": [],
            "_meta_parse_failed": True,
        }
        try:
            payload = json.loads(response)
        except json.JSONDecodeError:
            # 先尝试本地 regex 修复，避免额外 LLM 调用
            local_fixed = self._local_json_repair(response)
            if local_fixed:
                try:
                    payload = json.loads(local_fixed)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict):
                    payload.setdefault("_meta_parse_failed", False)
                    payload["_local_repaired"] = True
                    # 跳到后续标准化逻辑
                    return self._normalize_parsed_payload(payload, default_payload)

            try:
                payload = json.loads(self._extract_json_block(response))
            except Exception as error:
                logger.warning(
                    "实体提取JSON解析失败，返回空载荷: provider=%s, response_len=%s, preview=%s, error=%s",
                    self.provider,
                    len(str(response or "")),
                    self._truncate_for_log(response),
                    str(error),
                )
                return default_payload

        if not isinstance(payload, dict):
            logger.warning(
                "实体提取响应格式异常(非对象)，返回空载荷: provider=%s, payload_type=%s, preview=%s",
                self.provider,
                type(payload).__name__,
                self._truncate_for_log(response),
            )
            return default_payload

        return self._normalize_parsed_payload(payload, default_payload)

    def _normalize_parsed_payload(self, payload: Dict[str, Any], default_payload: Dict[str, Any]) -> Dict[str, Any]:
        """将LLM返回的原始JSON标准化为统一结构。"""
        if not isinstance(payload, dict):
            return default_payload

        entities = payload.get("entities", payload.get("nodes", []))
        triples = payload.get("triples", payload.get("edges", []))
        entity_attributes = payload.get("entity_attributes", [])
        relations_legacy = payload.get("relations", [])

        if not triples and isinstance(relations_legacy, list):
            for item in relations_legacy:
                if not isinstance(item, dict):
                    continue
                triples.append({
                    "head": item.get("source") or item.get("head"),
                    "relation": item.get("relation") or item.get("type"),
                    "tail": item.get("target") or item.get("tail"),
                    "attributes": item.get("attributes") or {},
                    "confidence": item.get("confidence", 0.6),
                })

        return {
            "entities": entities if isinstance(entities, list) else [],
            "triples": triples if isinstance(triples, list) else [],
            "entity_attributes": entity_attributes if isinstance(entity_attributes, list) else [],
            "entity_types": payload.get("entity_types") if isinstance(payload.get("entity_types"), dict) else {},
            "relation_types": payload.get("relation_types") if isinstance(payload.get("relation_types"), list) else [],
            "_meta_parse_failed": bool(payload.get("_meta_parse_failed", False)),
        }

    async def _call_zai(
        self,
        prompt: str,
        timeout: int,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        if not self.zai_client:
            raise RuntimeError("zai 客户端不可用")

        def _request() -> str:
            response = self.zai_client.chat.completions.create(
                model=self.config.zai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=float(self.config.temperature if temperature is None else temperature),
                max_tokens=int(self.config.max_tokens if max_tokens is None else max_tokens),
                timeout=timeout,
                response_format={"type": "json_object"},
            )
            choices = getattr(response, "choices", []) or []
            if not choices:
                raise RuntimeError("zai 返回为空")
            message = choices[0].message
            content = getattr(message, "content", "")
            if not content:
                raise RuntimeError("zai 返回缺少 content")
            return content

        return await asyncio.to_thread(_request)

    async def _call_deepseek(
        self,
        prompt: str,
        timeout: int,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        api_key = str(getattr(self.config, "deepseek_api_key", "") or "").strip()
        if not api_key:
            raise RuntimeError("deepseek api key 未配置")

        base_url = str(getattr(self.config, "deepseek_base_url", "https://api.deepseek.com") or "https://api.deepseek.com").rstrip("/")
        url = f"{base_url}/chat/completions"
        payload = {
            "model": self.config.deepseek_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(self.config.temperature if temperature is None else temperature),
            "max_tokens": int(self.config.max_tokens if max_tokens is None else max_tokens),
            "stream": False,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code if error.response is not None else "unknown"
            error_text = ""
            if error.response is not None:
                try:
                    error_text = error.response.text
                except Exception:
                    error_text = ""
            raise RuntimeError(f"DeepSeek API返回错误: {status_code} - {error_text}") from error
        except Exception as error:
            raise RuntimeError(f"DeepSeek 调用失败: {str(error)}") from error

        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise RuntimeError("deepseek 返回为空")
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
                elif isinstance(part, str):
                    parts.append(part)
            content = "\n".join([p for p in parts if p]).strip()
        if not content:
            raise RuntimeError("deepseek 返回缺少 content")
        return content

    async def _call_ollama(
        self,
        prompt: str,
        timeout: int,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        return await self.ollama.chat(
            model=self.config.ollama_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.temperature if temperature is None else temperature,
            max_tokens=int(self.config.max_tokens if max_tokens is None else max_tokens),
            timeout=timeout,
            response_format="json",
        )

    async def _repair_json_response(self, raw_text: str, timeout: int) -> Optional[str]:
        """先尝试本地regex修复，失败再调用LLM低温修复。"""
        if not bool(getattr(self.config, "enable_json_repair", True)):
            return None

        # 优先本地修复，避免额外的 LLM API 开销
        local_result = self._local_json_repair(raw_text)
        if local_result is not None:
            logger.info("JSON本地修复成功，跳过LLM修复调用")
            return local_result

        repair_prompt = self._build_json_repair_prompt(raw_text)
        repair_tokens = int(getattr(self.config, "json_repair_max_tokens", 768) or 768)
        repair_timeout = max(30, min(timeout, int(getattr(self.config, "timeout", 300) or 300)))
        try:
            if self.provider == "zai" and self.zai_client is not None:
                return await self._call_zai(
                    repair_prompt,
                    timeout=repair_timeout,
                    max_tokens=repair_tokens,
                    temperature=0.0,
                )
            if self.provider == "deepseek" and self.deepseek_available:
                return await self._call_deepseek(
                    repair_prompt,
                    timeout=repair_timeout,
                    max_tokens=repair_tokens,
                    temperature=0.0,
                )
            return await self._call_ollama(
                repair_prompt,
                timeout=repair_timeout,
                max_tokens=repair_tokens,
                temperature=0.0,
            )
        except Exception as error:
            logger.warning("JSON修复调用失败: provider=%s, error=%s", self.provider, str(error))
            return None

    async def _extract_once(self, text: str, chunk_id: Optional[str], timeout: int) -> Dict[str, Any]:
        prompt = self._build_extraction_prompt(text)

        response_text = None
        last_error = None
        max_retries = max(1, int(getattr(self.config, "max_retries", 1) or 1))

        for attempt_index in range(1, max_retries + 1):
            try:
                if self.provider == "zai" and self.zai_client is not None:
                    response_text = await self._call_zai(prompt, timeout)
                elif self.provider == "deepseek" and self.deepseek_available:
                    response_text = await self._call_deepseek(prompt, timeout)
                else:
                    response_text = await self._call_ollama(prompt, timeout)
                break
            except Exception as error:
                last_error = error
                logger.warning(
                    "实体提取调用失败: attempt=%s/%s, provider=%s, error=%s",
                    attempt_index,
                    max_retries,
                    self.provider,
                    str(error),
                )
                if attempt_index < max_retries:
                    await asyncio.sleep(min(2 ** (attempt_index - 1), 4))

        if response_text is None:
            raise RuntimeError(f"实体提取重试失败: {str(last_error)}")

        parsed = self._parse_llm_json(response_text)
        parse_failed = bool(parsed.get("_meta_parse_failed"))
        repaired = False
        if parse_failed:
            repaired_text = await self._repair_json_response(response_text, timeout=timeout)
            if repaired_text:
                repaired_payload = self._parse_llm_json(repaired_text)
                if not bool(repaired_payload.get("_meta_parse_failed")):
                    parsed = repaired_payload
                    parse_failed = False
                    repaired = True
                    logger.info(
                        "实体提取JSON修复成功: provider=%s, chunk_id=%s, repaired_len=%s",
                        self.provider,
                        chunk_id,
                        len(str(repaired_text or "")),
                    )
        if not parsed.get("entities") and not parsed.get("triples"):
            logger.warning(
                "实体提取返回空结构: provider=%s, chunk_id=%s, preview=%s",
                self.provider,
                chunk_id,
                self._truncate_for_log(response_text),
            )
        entity_attr_map: Dict[str, Dict[str, Any]] = {}
        for item in parsed.get("entity_attributes", []):
            if not isinstance(item, dict):
                continue
            name = self._normalize_name(item.get("entity", ""))
            attrs = item.get("attributes") or {}
            if name and isinstance(attrs, dict):
                entity_attr_map[name] = attrs

        entity_names: List[str] = []
        normalized_entities: List[Dict[str, Any]] = []

        for raw_entity in parsed.get("entities", []):
            if isinstance(raw_entity, str):
                entity_name = self._normalize_name(raw_entity)
                entity_type = self.config.unknown_entity_type
                attributes = entity_attr_map.get(entity_name, {})
                confidence = 0.7
            elif isinstance(raw_entity, dict):
                entity_name = self._normalize_name(raw_entity.get("name") or raw_entity.get("entity") or "")
                entity_type = self._normalize_name(raw_entity.get("type") or self.config.unknown_entity_type)
                attributes = raw_entity.get("attributes") or {}
                if not isinstance(attributes, dict):
                    attributes = {}
                confidence = self._clamp_confidence(raw_entity.get("confidence"), 0.7)
            else:
                continue

            if not entity_name or len(entity_name) < self.min_entity_length:
                continue

            if entity_name in entity_names:
                continue

            entity_names.append(entity_name)
            normalized_entities.append({
                "name": entity_name,
                "canonical_name": entity_name,
                "type": entity_type or self.config.unknown_entity_type,
                "labels": [entity_type] if entity_type else [self.config.unknown_entity_type],
                "confidence": confidence,
                "attributes": attributes,
                "mention_count": 1,
                "chunk_ids": [chunk_id] if chunk_id else [],
                "aliases": [],
            })

        valid_entities: Set[str] = set(entity_names)
        normalized_relations: List[Dict[str, Any]] = []
        dropped_relation_endpoints = 0

        for triple in parsed.get("triples", []):
            if not isinstance(triple, dict):
                continue
            head = self._normalize_name(triple.get("head") or triple.get("source") or "")
            tail = self._normalize_name(triple.get("tail") or triple.get("target") or "")
            relation_name = self._normalize_name(triple.get("relation") or self.config.unknown_relation_type)
            if not head or not tail or head == tail:
                dropped_relation_endpoints += 1
                continue

            if head not in valid_entities or tail not in valid_entities:
                dropped_relation_endpoints += 1
                continue

            attributes = triple.get("attributes") or {}
            if not isinstance(attributes, dict):
                attributes = {}

            normalized_relations.append({
                "source": head,
                "target": tail,
                "relation": relation_name or self.config.unknown_relation_type,
                "confidence": self._clamp_confidence(triple.get("confidence"), 0.6),
                "evidence_count": 1,
                "chunk_ids": [chunk_id] if chunk_id else [],
                "attributes": attributes,
            })

        return {
            "entities": normalized_entities,
            "relations": normalized_relations,
            "chunk_id": chunk_id,
            "metrics": {
                "dropped_relation_endpoints": dropped_relation_endpoints,
                "raw_entity_count": len(parsed.get("entities", [])),
                "raw_relation_count": len(parsed.get("triples", [])),
                "failed": parse_failed,
                "parse_failed": parse_failed,
                "repaired": repaired,
                "llm_empty": len(parsed.get("entities", [])) == 0 and len(parsed.get("triples", [])) == 0,
            },
        }

    def _slice_layers(self, text: str) -> List[str]:
        if not self.config.layered_extraction_enabled:
            return [text]

        if len(text) <= int(self.config.layer_window_chars or 3200):
            return [text]

        layers: List[str] = []
        window = max(400, int(self.config.layer_window_chars or 3200))
        overlap = max(0, int(self.config.layer_overlap_chars or 0))
        step = max(50, window - overlap)

        cursor = 0
        while cursor < len(text):
            piece = text[cursor:cursor + window].strip()
            if piece:
                layers.append(piece)
            cursor += step

        return layers or [text]

    async def extract_from_text(
        self,
        text: str,
        chunk_id: Optional[str] = None,
        min_length_override: Optional[int] = None,
        timeout_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        """从单个文本块提取实体和关系。"""
        min_length = min_length_override if min_length_override is not None else self.config.min_text_length
        if len(text or "") < min_length:
            return {
                "entities": [],
                "relations": [],
                "chunk_id": chunk_id,
                "metrics": {
                    "dropped_relation_endpoints": 0,
                    "raw_entity_count": 0,
                    "raw_relation_count": 0,
                    "failed": False,
                    "parse_failed": False,
                    "llm_empty": False,
                },
            }

        start_time = time.perf_counter()
        normalized_text = (text or "").strip()
        if len(normalized_text) > int(self.config.max_text_length or 9000):
            normalized_text = normalized_text[: int(self.config.max_text_length or 9000)]

        cache_key = self._cache_key(normalized_text, stage="extract")
        cached = self._get_cached(cache_key)
        if cached is not None:
            cached = self._bind_chunk_context(cached, chunk_id)
            cached.setdefault("metrics", {})["cache_hit"] = True
            return cached

        timeout = int(timeout_override or self.config.timeout or 300)
        layers = self._slice_layers(normalized_text)
        layer_results: List[Dict[str, Any]] = []

        for layer_text in layers:
            layer_key = self._cache_key(layer_text, stage="layer")
            layer_cached = self._get_cached(layer_key)
            if layer_cached is not None:
                layer_results.append(self._bind_chunk_context(layer_cached, chunk_id))
                continue

            one = await self._extract_once(layer_text, chunk_id=None, timeout=timeout)
            await self._append_cache(layer_key, one)
            layer_results.append(self._bind_chunk_context(one, chunk_id))

        merged_entities, merged_relations = self.merge_extraction_results(layer_results)
        metrics = {
            "dropped_relation_endpoints": sum(int((item.get("metrics") or {}).get("dropped_relation_endpoints", 0)) for item in layer_results),
            "raw_entity_count": sum(int((item.get("metrics") or {}).get("raw_entity_count", 0)) for item in layer_results),
            "raw_relation_count": sum(int((item.get("metrics") or {}).get("raw_relation_count", 0)) for item in layer_results),
            "failed": any(bool((item.get("metrics") or {}).get("failed")) for item in layer_results),
            "parse_failed": any(bool((item.get("metrics") or {}).get("parse_failed")) for item in layer_results),
            "llm_empty": all(
                int((item.get("metrics") or {}).get("raw_entity_count", 0)) == 0
                and int((item.get("metrics") or {}).get("raw_relation_count", 0)) == 0
                for item in layer_results
            ),
            "layer_count": len(layers),
            "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
            "cache_hit": False,
        }

        payload = {
            "entities": merged_entities,
            "relations": merged_relations,
            "chunk_id": chunk_id,
            "metrics": metrics,
        }
        await self._append_cache(cache_key, self._bind_chunk_context(payload, chunk_id=None))
        return payload

    async def batch_extract(
        self,
        texts: List[Tuple[str, Optional[str]]],
        concurrency: int = None,
    ) -> List[Dict[str, Any]]:
        """批量并发提取实体和关系（异步队列 + 自适应并发/超时）。"""
        if not texts:
            return []

        min_cc = max(1, int(self.config.min_concurrency or 1))
        max_cc = max(min_cc, int(self.config.max_concurrency or min_cc))
        current_cc = int(concurrency or self.config.batch_size or min_cc)
        current_cc = max(min_cc, min(max_cc, current_cc))
        current_timeout = int(self.config.timeout or 300)
        queue_batch_size = max(1, int(self.config.queue_batch_size or 16))

        results: List[Dict[str, Any]] = [
            {
                "entities": [],
                "relations": [],
                "chunk_id": chunk_id,
                "metrics": {
                    "dropped_relation_endpoints": 0,
                    "raw_entity_count": 0,
                    "raw_relation_count": 0,
                    "failed": False,
                    "parse_failed": False,
                    "llm_empty": False,
                },
            }
            for _, chunk_id in texts
        ]

        for offset in range(0, len(texts), queue_batch_size):
            batch_items = texts[offset: offset + queue_batch_size]
            queue: asyncio.Queue = asyncio.Queue()
            for index, item in enumerate(batch_items, start=offset):
                await queue.put((index, item[0], item[1]))

            errors = 0
            latencies: List[int] = []

            async def worker() -> None:
                nonlocal errors
                while True:
                    try:
                        index, item_text, chunk_id = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return

                    st = time.perf_counter()
                    try:
                        result_item = await self.extract_from_text(
                            item_text,
                            chunk_id,
                            timeout_override=current_timeout,
                        )
                        results[index] = result_item
                    except Exception as error:
                        errors += 1
                        logger.error("批量抽取任务失败: idx=%s, chunk_id=%s, error=%s", index, chunk_id, str(error))
                        results[index] = {
                            "entities": [],
                            "relations": [],
                            "chunk_id": chunk_id,
                            "metrics": {
                                "dropped_relation_endpoints": 0,
                                "raw_entity_count": 0,
                                "raw_relation_count": 0,
                                "failed": True,
                                "parse_failed": False,
                                "llm_empty": False,
                            },
                            "error": str(error),
                        }
                    finally:
                        latencies.append(int((time.perf_counter() - st) * 1000))
                        queue.task_done()

            workers = [asyncio.create_task(worker()) for _ in range(current_cc)]
            await queue.join()
            await asyncio.gather(*workers, return_exceptions=True)

            if self.config.adaptive_concurrency_enabled:
                avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
                err_ratio = errors / max(1, len(batch_items))
                target_latency = int(self.config.target_latency_ms or 2500)
                timeout_step = int(self.config.timeout_step_seconds or 30)

                if err_ratio > 0.2 or (avg_latency and avg_latency > int(target_latency * 1.4)):
                    current_cc = max(min_cc, current_cc - 1)
                    current_timeout = min(600, current_timeout + timeout_step)
                elif err_ratio == 0 and avg_latency and avg_latency < int(target_latency * 0.7):
                    current_cc = min(max_cc, current_cc + 1)
                    current_timeout = max(60, current_timeout - timeout_step)

                logger.info(
                    "抽取队列批次完成: offset=%s, size=%s, cc=%s, timeout=%s, avg_latency_ms=%s, err_ratio=%.2f",
                    offset,
                    len(batch_items),
                    current_cc,
                    current_timeout,
                    avg_latency,
                    err_ratio,
                )

        return results

    async def reclassify_unknowns(
        self,
        entities: List[Dict[str, Any]],
        relations: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """二次分类 Unknown，提升可用标签质量。"""
        if not self.config.enable_second_pass_reclassify:
            return {"entity_updates": 0, "relation_updates": 0}

        unknown_entities = [
            item for item in entities
            if item.get("type") == self.config.unknown_entity_type
        ]
        unknown_relations = [
            item for item in relations
            if item.get("relation") == self.config.unknown_relation_type
        ]

        if not unknown_entities and not unknown_relations:
            return {"entity_updates": 0, "relation_updates": 0}

        unknown_entities = unknown_entities[: int(self.config.reclassify_batch_limit or 80)]
        unknown_relations = unknown_relations[: int(self.config.reclassify_batch_limit or 80)]

        prompt = (
            "你是一个知识图谱标注助手。请将以下 unknown 实体和关系重新分类，输出 JSON。\n"
            "要求：\n"
            "1) 不要返回解释，只返回 JSON。\n"
            "2) entity_types 键是对象，key=实体名，value=新类型。\n"
            "3) relation_types 是数组，每项包含 source,target,old_relation,new_relation。\n"
            "JSON格式：{\"entity_types\":{},\"relation_types\":[]}\n\n"
            f"unknown_entities={json.dumps([item.get('name') for item in unknown_entities], ensure_ascii=False)}\n"
            f"unknown_relations={json.dumps([{ 'source': r.get('source'), 'target': r.get('target'), 'relation': r.get('relation')} for r in unknown_relations], ensure_ascii=False)}"
        )

        try:
            timeout = int(self.config.timeout or 300)
            if self.provider == "zai" and self.zai_client is not None:
                raw = await self._call_zai(prompt, timeout=timeout)
            elif self.provider == "deepseek" and self.deepseek_available:
                raw = await self._call_deepseek(prompt, timeout=timeout)
            else:
                raw = await self._call_ollama(prompt, timeout=timeout)

            payload = self._parse_llm_json(raw)
            entity_types = payload.get("entity_types") if isinstance(payload, dict) else {}
            relation_types = payload.get("relation_types") if isinstance(payload, dict) else []

            entity_updates = 0
            relation_updates = 0

            if isinstance(entity_types, dict):
                for item in entities:
                    if item.get("type") != self.config.unknown_entity_type:
                        continue
                    new_type = self._normalize_name(entity_types.get(item.get("name"), ""))
                    if new_type:
                        item["type"] = new_type
                        labels = item.get("labels") or []
                        if new_type not in labels:
                            labels.append(new_type)
                        item["labels"] = labels
                        entity_updates += 1

            if isinstance(relation_types, list):
                mapping: Dict[Tuple[str, str, str], str] = {}
                for row in relation_types:
                    if not isinstance(row, dict):
                        continue
                    source = self._normalize_name(row.get("source", ""))
                    target = self._normalize_name(row.get("target", ""))
                    old_rel = self._normalize_name(row.get("old_relation", ""))
                    new_rel = self._normalize_name(row.get("new_relation", ""))
                    if source and target and old_rel and new_rel:
                        mapping[(source, target, old_rel)] = new_rel

                for item in relations:
                    key = (
                        self._normalize_name(item.get("source", "")),
                        self._normalize_name(item.get("target", "")),
                        self._normalize_name(item.get("relation", "")),
                    )
                    new_rel = mapping.get(key)
                    if new_rel:
                        item["relation"] = new_rel
                        relation_updates += 1

            return {"entity_updates": entity_updates, "relation_updates": relation_updates}
        except Exception as error:
            logger.warning("Unknown 二次分类失败: %s", str(error))
            return {"entity_updates": 0, "relation_updates": 0}

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
                    "attributes": dict(entity_item.get("attributes", {}) or {}),
                }
                continue

            existing["mention_count"] += int(entity_item.get("mention_count", 1) or 1)
            existing["confidence"] = max(
                self._clamp_confidence(existing.get("confidence"), 0.7),
                self._clamp_confidence(entity_item.get("confidence"), 0.7),
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

        relation_dict: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for relation_item in all_relations:
            source_name = self._normalize_name(relation_item.get("source", ""))
            target_name = self._normalize_name(relation_item.get("target", ""))
            relation_name = self._normalize_name(relation_item.get("relation") or self.config.unknown_relation_type)

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
                    "attributes": dict(relation_item.get("attributes", {}) or {}),
                }
                continue

            existing_relation["confidence"] = max(
                self._clamp_confidence(existing_relation.get("confidence"), 0.6),
                self._clamp_confidence(relation_item.get("confidence"), 0.6),
            )
            existing_relation["evidence_count"] += int(relation_item.get("evidence_count", 1) or 1)
            existing_relation["chunk_ids"].update(relation_item.get("chunk_ids", []))

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
                    "aliases": sorted(list(entity_item.get("aliases", set()))),
                },
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
                "attributes": relation_item.get("attributes", {}),
            })

        unique_entities.sort(key=lambda item: item.get("attributes", {}).get("mention_count", 0), reverse=True)
        unique_relations.sort(key=lambda item: item.get("evidence_count", 0), reverse=True)

        return unique_entities, unique_relations


_entity_extraction_service_instance = None


def get_entity_extraction_service() -> EntityExtractionService:
    """获取实体提取服务单例。"""
    global _entity_extraction_service_instance
    if _entity_extraction_service_instance is None:
        _entity_extraction_service_instance = EntityExtractionService()
    return _entity_extraction_service_instance
