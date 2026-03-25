"""
Agent Service - 智能体服务
实现基于 ReAct 框架的简单 Agent 系统
"""
import json
import re
import time
import ast
import operator
import inspect
from collections import OrderedDict
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from app.utils.logger import get_logger
from app.core.config import settings

logger = get_logger(__name__)


class Tool:
    """工具基类"""
    
    def __init__(self, name: str, description: str, func: Callable):
        self.name = name
        self.description = description
        self.func = func
    
    def run(self, *args, **kwargs) -> str:
        """执行工具"""
        try:
            if inspect.iscoroutinefunction(self.func):
                raise RuntimeError("异步工具请使用 arun 调用")
            result = self.func(*args, **kwargs)
            if inspect.isawaitable(result):
                raise RuntimeError("异步工具请使用 arun 调用")
            return str(result)
        except Exception as e:
            logger.error(f"Tool {self.name} execution failed: {str(e)}")
            return f"工具执行失败: {str(e)}"

    async def arun(self, *args, **kwargs) -> str:
        """异步执行工具，兼容同步/异步函数"""
        try:
            result = self.func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return str(result)
        except Exception as e:
            logger.error(f"Tool {self.name} execution failed: {str(e)}")
            return f"工具执行失败: {str(e)}"


class AgentService:
    """
    Agent 服务 - 基于 ReAct (Reasoning + Acting) 框架
    
    工作流程:
    1. Thought (思考): Agent 分析当前状态
    2. Action (行动): Agent 决定使用什么工具
    3. Observation (观察): 获取工具执行结果
    4. 重复上述过程直到得到最终答案
    """
    
    def __init__(self, llm_service, knowledge_base_service=None, max_iterations: int = 5):
        """
        初始化 Agent
        
        Args:
            llm_service: LLM 服务实例
            knowledge_base_service: 知识库服务实例
            max_iterations: 最大迭代次数
        """
        self.llm_service = llm_service
        self.kb_service = knowledge_base_service
        self.max_iterations = max_iterations
        self.tools: Dict[str, Tool] = {}
        self.conversation_history: List[Dict] = []
        self.session_histories: Dict[str, List[Dict[str, str]]] = {}
        self.session_access_order: "OrderedDict[str, float]" = OrderedDict()
        self.max_history_turns = 6
        self.max_session_histories = int(getattr(settings, 'agent_max_sessions', 200) or 200)
        self.session_ttl_seconds = int(getattr(settings, 'agent_session_ttl_seconds', 4 * 3600) or (4 * 3600))
        
        # 注册默认工具
        self._register_default_tools()
    
    def _register_default_tools(self):
        """注册默认工具"""
        
        # 工具1: 知识库搜索
        if self.kb_service:
            async def search_knowledge_base(query: str, kb_id: int = None, kb_ids: Optional[List[int]] = None, top_k: int = 3) -> str:
                """搜索知识库获取相关信息"""
                try:
                    resolved_kb_ids = await self._resolve_kb_ids(kb_id=kb_id, kb_ids=kb_ids, limit=5)
                    if not resolved_kb_ids:
                        return "EVIDENCE_NONE: 未找到可检索的知识库"

                    use_hybrid = bool(getattr(settings.hybrid_retrieval, 'enabled', True))
                    results = await self._agent_retrieve_evidence(
                        kb_ids=resolved_kb_ids,
                        query=query,
                        top_k=max(1, int(top_k or 3)),
                        use_hybrid=use_hybrid
                    )

                    results = self._filter_agent_retrieval_results(results)
                    if not results:
                        return "EVIDENCE_NONE: 未找到相关信息"
                    
                    # 格式化搜索结果
                    formatted = []
                    for i, doc in enumerate(results, 1):
                        content = str(doc.get('content', '') or '')[:240]
                        metadata = doc.get('metadata', {}) or {}
                        source = doc.get('source') or metadata.get('source', '未知')
                        score = float(doc.get('similarity', doc.get('final_score', doc.get('score', 0.0))) or 0.0)
                        file_id = metadata.get('file_id', 'unknown')
                        formatted.append(f"{i}. [source={source}; file_id={file_id}; score={score:.3f}] {content}")
                    
                    return "EVIDENCE_OK:\n" + "\n".join(formatted)
                except Exception as e:
                    return f"EVIDENCE_NONE: 知识库搜索失败: {str(e)}"
            
            self.register_tool(
                name="search_knowledge_base",
                description="搜索知识库获取相关文档和信息。参数: query(必需)-搜索查询, kb_id(可选)-知识库ID, top_k(可选)-返回结果数量",
                func=search_knowledge_base
            )
        
        # 工具2: 计算器
        def calculator(expression: str) -> str:
            """执行数学计算"""
            try:
                result = self._safe_eval_math(expression)
                return f"计算结果: {result}"
            except Exception as e:
                return f"计算失败: {str(e)}"
        
        self.register_tool(
            name="calculator",
            description="执行数学计算。参数: expression-数学表达式(如: 2+3*4)",
            func=calculator
        )
        
        # 工具3: 当前时间
        def get_current_time() -> str:
            """获取当前时间"""
            now = datetime.now()
            return now.strftime("%Y-%m-%d %H:%M:%S")
        
        self.register_tool(
            name="get_current_time",
            description="获取当前日期和时间。无需参数",
            func=get_current_time
        )

    async def _resolve_kb_ids(self, kb_id: Optional[int], kb_ids: Optional[List[int]] = None, limit: int = 5) -> List[int]:
        if kb_id:
            if kb_ids and int(kb_id) not in [int(x) for x in kb_ids]:
                return []
            return [int(kb_id)]

        if kb_ids:
            unique = []
            for item in kb_ids:
                try:
                    value = int(item)
                except Exception:
                    continue
                if value not in unique:
                    unique.append(value)
            return unique[:limit]

        kb_ids: List[int] = []
        if hasattr(self.kb_service, "list_knowledge_bases"):
            kbs = await self._maybe_await(self.kb_service.list_knowledge_bases, skip=0, limit=limit)
            for kb in (kbs or []):
                kb_id_val = kb.get("id") if isinstance(kb, dict) else getattr(kb, "id", None)
                if kb_id_val is not None:
                    kb_ids.append(int(kb_id_val))
        elif hasattr(self.kb_service, "get_all_knowledge_bases"):
            kbs = await self._maybe_await(self.kb_service.get_all_knowledge_bases)
            for kb in (kbs or [])[:limit]:
                kb_id_val = kb.get("id") if isinstance(kb, dict) else getattr(kb, "id", None)
                if kb_id_val is not None:
                    kb_ids.append(int(kb_id_val))
        return kb_ids[:limit]

    def _touch_session(self, session_key: str) -> None:
        now = time.time()
        self.session_access_order[session_key] = now
        self.session_access_order.move_to_end(session_key)

    def _cleanup_sessions(self) -> None:
        now = time.time()
        expired_keys = []
        for key, ts in self.session_access_order.items():
            if (now - ts) > self.session_ttl_seconds:
                expired_keys.append(key)
        for key in expired_keys:
            self.session_access_order.pop(key, None)
            self.session_histories.pop(key, None)

        while len(self.session_access_order) > self.max_session_histories:
            oldest_key, _ = self.session_access_order.popitem(last=False)
            self.session_histories.pop(oldest_key, None)

    def _get_session_history(self, session_key: str) -> List[Dict[str, str]]:
        self._cleanup_sessions()
        self._touch_session(session_key)
        return list(self.session_histories.get(session_key, []))

    def _save_session_history(self, session_key: str, history: List[Dict[str, str]]) -> None:
        self.session_histories[session_key] = history[-self.max_history_turns:]
        self._touch_session(session_key)
        self._cleanup_sessions()

    async def _agent_retrieve_evidence(self, kb_ids: List[int], query: str, top_k: int, use_hybrid: bool) -> List[Dict[str, Any]]:
        # 优先复用智能助手的混合检索能力（向量+图谱），不可用时降级纯向量
        if use_hybrid and bool(getattr(settings.knowledge_graph, 'enabled', False)):
            try:
                from app.services.retrieval.hybrid_retrieval_service import get_hybrid_retrieval_service
                hybrid_service = get_hybrid_retrieval_service()
                all_results: List[Dict[str, Any]] = []
                for each_kb_id in kb_ids:
                    payload = await hybrid_service.hybrid_search(
                        kb_id=each_kb_id,
                        query=query,
                        top_k=top_k,
                        enable_graph=True
                    )
                    all_results.extend(payload.get('results', []) or [])
                if all_results:
                    all_results.sort(
                        key=lambda x: float(x.get('final_score', x.get('similarity', x.get('score', 0.0))) or 0.0),
                        reverse=True
                    )
                    return all_results[: max(top_k * 2, top_k)]
            except Exception as error:
                logger.warning("Agent 混合检索降级到向量检索: %s", str(error))

        if hasattr(self.kb_service, "search_knowledge_bases"):
            return await self._maybe_await(
                self.kb_service.search_knowledge_bases,
                kb_ids=kb_ids,
                query=query,
                top_k=top_k,
                score_threshold=0.2
            )

        all_results = []
        for each_kb_id in kb_ids:
            if hasattr(self.kb_service, "search_knowledge_base"):
                partial = await self._maybe_await(
                    self.kb_service.search_knowledge_base,
                    kb_id=each_kb_id,
                    query=query,
                    top_k=max(2, top_k)
                )
            else:
                partial = await self._maybe_await(self.kb_service.search, each_kb_id, query, max(2, top_k))
            all_results.extend(partial or [])
        return all_results

    def _filter_agent_retrieval_results(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not search_results:
            return []

        max_results = max(1, int(getattr(settings.hybrid_retrieval, 'chat_context_max_results', 8) or 8))
        min_similarity = float(getattr(settings.hybrid_retrieval, 'chat_min_similarity', 0.12) or 0.12)
        min_graph_similarity = float(getattr(settings.hybrid_retrieval, 'chat_graph_min_similarity', min_similarity) or min_similarity)
        min_graph_confidence = float(getattr(settings.hybrid_retrieval, 'chat_graph_min_confidence', 0.35) or 0.35)

        scored = sorted(
            search_results,
            key=lambda item: float(item.get('similarity', item.get('final_score', item.get('score', 0.0))) or 0.0),
            reverse=True,
        )
        filtered: List[Dict[str, Any]] = []
        for item in scored:
            similarity = float(item.get('similarity', item.get('final_score', item.get('score', 0.0))) or 0.0)
            source = str(item.get('source', '') or '')
            threshold = min_graph_similarity if source.startswith('graph') else min_similarity
            if similarity < threshold:
                continue

            if source == 'graph_direct':
                metadata = item.get('metadata', {}) or {}
                attrs = metadata.get('entity_attributes') if isinstance(metadata, dict) else {}
                confidence = 0.0
                if isinstance(attrs, dict):
                    confidence = float(attrs.get('confidence', 0.0) or 0.0)
                if confidence and confidence < min_graph_confidence:
                    continue

            normalized = dict(item)
            normalized['similarity'] = similarity
            filtered.append(normalized)
            if len(filtered) >= max_results:
                break

        # 保底保留最高分结果，避免阈值过严导致全部过滤
        if not filtered and scored:
            keep = dict(scored[0])
            keep['similarity'] = float(keep.get('similarity', keep.get('final_score', keep.get('score', 0.0))) or 0.0)
            filtered = [keep]

        return filtered

    async def _maybe_await(self, fn: Callable, *args, **kwargs):
        """调用并兼容同步/异步函数。"""
        result = fn(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
    
    def register_tool(self, name: str, description: str, func: Callable):
        """注册新工具"""
        self.tools[name] = Tool(name, description, func)
        logger.info(f"Tool registered: {name}")
    
    def _build_prompt(self, user_query: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """构建 Agent 提示词"""
        
        # 工具列表
        tools_desc = "\n".join([
            f"- {tool.name}: {tool.description}"
            for tool in self.tools.values()
        ])
        
        history_text = ""
        if history:
            # 只保留最近若干轮，避免 prompt 无限制增长
            latest_history = history[-self.max_history_turns:]
            history_lines = []
            for item in latest_history:
                role = item.get("role", "unknown")
                content = item.get("content", "")
                history_lines.append(f"{role}: {content}")
            history_text = "\n\n历史对话:\n" + "\n".join(history_lines)

        prompt = f"""你是一个智能 Agent，能够使用工具来回答用户问题。

可用工具:
{tools_desc}

请使用以下格式回答:

Thought: 我需要思考如何回答这个问题
Action: 工具名称
Action Input: 工具的输入参数(JSON格式)
Observation: [工具返回的结果会显示在这里]
... (可以重复 Thought/Action/Observation 多次)
Thought: 我现在知道最终答案了
Final Answer: 最终答案

重要规则:
1. 必须严格按照格式输出
2. Action Input 必须是有效的 JSON 格式
3. 如果不需要使用工具，直接给出 Final Answer
4. 每次只执行一个 Action
5. 涉及事实性问题时，必须优先检索知识库；若未拿到明确证据，只能说明“未检索到可靠信息”，禁止编造

用户问题: {user_query}
{history_text}

开始!
"""
        return prompt

    def _is_kb_observation_unreliable(self, tool_name: str, observation: str) -> bool:
        """判断知识库检索结果是否不可靠（失败/空结果）。"""
        if tool_name != "search_knowledge_base":
            return False
        text = (observation or "").strip()
        if not text:
            return True
        upper_text = text.upper()
        if upper_text.startswith("EVIDENCE_NONE"):
            return True
        if upper_text.startswith("EVIDENCE_OK"):
            return False
        return text.startswith("知识库搜索失败") or text.startswith("未找到相关信息")

    def _should_force_kb_lookup(self, user_query: str) -> bool:
        """判断是否应在推理前先执行一次知识库检索。"""
        query = (user_query or "").strip().lower()
        if not query:
            return False

        # 时间/计算由专用工具优先处理
        if self._should_force_time_tool(query) or self._should_force_calculator_tool(query):
            return False

        factual_markers = [
            "谁", "什么", "介绍", "查询", "规定", "政策", "流程", "办法", "说明", "资料", "文档",
            "工资", "请假", "报销", "制度", "公司", "实习", "合同", "标准", "多少", "是否", "有无",
            "who", "what", "how", "policy", "salary", "company", "document", "rule", "regulation",
        ]
        return any(marker in query for marker in factual_markers)

    def _safe_eval_math(self, expression: str) -> Any:
        """安全计算数学表达式，仅允许基础算术操作。"""
        expr = (expression or "").strip()
        if not expr:
            raise ValueError("表达式为空")

        operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.FloorDiv: operator.floordiv,
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
        }

        def _eval(node):
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            if isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)):
                    return node.value
                raise ValueError("表达式包含非法常量")
            if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
                return operators[type(node.op)](_eval(node.operand))
            if isinstance(node, ast.BinOp) and type(node.op) in operators:
                left = _eval(node.left)
                right = _eval(node.right)
                return operators[type(node.op)](left, right)
            raise ValueError("表达式包含不支持的语法")

        tree = ast.parse(expr, mode="eval")
        value = _eval(tree)
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    def _should_force_calculator_tool(self, user_query: str) -> bool:
        """识别明显的数学计算问题，优先直连计算器工具。"""
        query = (user_query or "").lower()
        has_digit = bool(re.search(r"\d", query))
        has_operator = bool(re.search(r"[+\-*/()%]", query))
        has_math_kw = any(k in query for k in ["计算", "算一下", "等于", "加", "减", "乘", "除", "次方", "平方"])
        return has_digit and (has_operator or has_math_kw)

    def _extract_math_expression(self, user_query: str) -> Optional[str]:
        """从用户问题中提取可计算表达式。"""
        query = (user_query or "").strip()
        if not query:
            return None

        # 常见中文运算词归一化
        normalized = query
        replacements = [
            ("（", "("),
            ("）", ")"),
            ("×", "*"),
            ("x", "*"),
            ("X", "*"),
            ("÷", "/"),
            ("加上", "+"),
            ("加", "+"),
            ("减去", "-"),
            ("减", "-"),
            ("乘以", "*"),
            ("乘", "*"),
            ("除以", "/"),
            ("除", "/"),
        ]
        for old, new in replacements:
            normalized = normalized.replace(old, new)

        candidates = re.findall(r"[\d\s+\-*/().%]+", normalized)
        candidates = [c.strip() for c in candidates if c and re.search(r"\d", c) and re.search(r"[+\-*/()%]", c)]
        if not candidates:
            return None

        # 取最长候选作为表达式
        return max(candidates, key=len)

    async def _build_forced_calculator_result(self, expression: str, show_steps: bool) -> Dict[str, Any]:
        """构造计算器工具直连响应。"""
        observation = await self.tools["calculator"].arun(expression=expression)
        answer = observation if observation else "计算失败: 无结果"
        steps = []
        if show_steps:
            steps = [
                {"type": "thought", "content": "这是数学计算问题，直接调用计算器工具更可靠。"},
                {"type": "action", "tool": "calculator", "input": json.dumps({"expression": expression}, ensure_ascii=False)},
                {"type": "observation", "content": observation},
                {"type": "final_answer", "content": answer},
            ]
        return {
            "answer": answer,
            "steps": steps,
            "success": not str(answer).startswith("计算失败"),
            "iterations": 1
        }
    
    def _parse_action(self, text: str) -> Optional[tuple]:
        """
        解析 LLM 输出中的 Action
        
        Returns:
            (action_name, action_input) 或 None
        """
        # 匹配 Action 和 Action Input（兼容多种输出格式）
        action_match = re.search(r'Action\s*:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        input_match = re.search(
            r'Action\s*Input\s*:\s*(.+?)(?=\n\w+\s*:|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        
        if not action_match:
            return None
        
        action_name = self._normalize_action_name(action_match.group(1).strip())
        action_input = self._normalize_action_input(input_match.group(1).strip() if input_match else "{}")
        
        return action_name, action_input

    def _normalize_action_name(self, action_name: str) -> str:
        """规范化工具名，兼容模型输出中的括号、反引号、空格等。"""
        name = (action_name or "").strip()
        name = re.sub(r'[`\"\']', '', name)
        name = re.sub(r'\(.*\)$', '', name).strip()
        name = name.replace(" ", "")
        return name

    def _normalize_action_input(self, action_input: str) -> str:
        """提取 JSON 输入，兼容 ```json 代码块。"""
        text = (action_input or "").strip()
        code_block = re.search(r'```(?:json)?\s*(.*?)```', text, re.IGNORECASE | re.DOTALL)
        if code_block:
            text = code_block.group(1).strip()
        return text or "{}"

    def _should_force_time_tool(self, user_query: str) -> bool:
        """时间类问题直接走时间工具，避免模型幻想时间。"""
        query = (user_query or "").lower()
        keywords = [
            "现在几点", "几点", "当前时间", "现在时间", "什么时间", "时间是什么", "当前是几点",
            "今天几号", "今天星期", "当前日期", "今天日期", "日期时间",
            "what time", "current time", "date today", "time now"
        ]
        return any(key in query for key in keywords)

    async def _build_forced_time_result(self, show_steps: bool) -> Dict[str, Any]:
        """构造时间工具直连响应。"""
        observation = await self.tools["get_current_time"].arun()
        answer = f"当前时间是: {observation}"
        steps = []
        if show_steps:
            steps = [
                {"type": "thought", "content": "这是时间查询问题，直接调用当前时间工具更可靠。"},
                {"type": "action", "tool": "get_current_time", "input": "{}"},
                {"type": "observation", "content": observation},
                {"type": "final_answer", "content": answer},
            ]
        return {
            "answer": answer,
            "steps": steps,
            "success": True,
            "iterations": 1
        }
    
    def _parse_final_answer(self, text: str) -> Optional[str]:
        """解析最终答案"""
        match = re.search(r'Final Answer:\s*(.+)', text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
    
    async def run(
        self,
        user_query: str,
        session_id: str = None,
        kb_ids: Optional[List[int]] = None,
        max_iterations: Optional[int] = None,
        llm_model: Optional[str] = None,
        temperature: Optional[float] = None,
        show_steps: bool = True,
        step_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
    ) -> Dict[str, Any]:
        """
        运行 Agent
        
        Args:
            user_query: 用户问题
            session_id: 会话ID（用于保持上下文）
        
        Returns:
            {
                "answer": "最终答案",
                "steps": [执行步骤],
                "success": True/False
            }
        """
        start_time = time.time()
        steps = []
        tools_called = 0
        kb_unreliable = False
        kb_last_observation = ""
        session_key = session_id or "default"
        history = self._get_session_history(session_key)
        runtime_max_iterations = max(1, min(10, int(max_iterations if max_iterations is not None else self.max_iterations)))

        async def record_step(step: Dict[str, Any]) -> None:
            if show_steps:
                steps.append(step)
            if step_callback is not None:
                try:
                    callback_result = step_callback(step)
                    if inspect.isawaitable(callback_result):
                        await callback_result
                except Exception as callback_error:
                    logger.warning("Step callback failed: %s", str(callback_error))

        # 对强确定性时间查询优先直连工具，避免模型输出错误时间
        if "get_current_time" in self.tools and self._should_force_time_tool(user_query):
            result = await self._build_forced_time_result(show_steps=show_steps)
            if step_callback is not None:
                for step in result.get("steps", []) or []:
                    callback_result = step_callback(step)
                    if inspect.isawaitable(callback_result):
                        await callback_result
            history.append({"role": "user", "content": user_query})
            history.append({"role": "assistant", "content": result["answer"]})
            self._save_session_history(session_key, history)
            return result

        # 对明确数学计算问题优先直连计算器，避免模型格式不稳定导致失败
        if "calculator" in self.tools and self._should_force_calculator_tool(user_query):
            expression = self._extract_math_expression(user_query)
            if expression:
                result = await self._build_forced_calculator_result(expression=expression, show_steps=show_steps)
                if step_callback is not None:
                    for step in result.get("steps", []) or []:
                        callback_result = step_callback(step)
                        if inspect.isawaitable(callback_result):
                            await callback_result
                history.append({"role": "user", "content": user_query})
                history.append({"role": "assistant", "content": result["answer"]})
                self._save_session_history(session_key, history)
                return result

        # 对事实型问题先执行一次确定性的知识库检索，避免模型跳过工具直接回答
        preloaded_kb_observation = ""
        if "search_knowledge_base" in self.tools and self._should_force_kb_lookup(user_query):
            preloaded_kb_observation = await self.tools["search_knowledge_base"].arun(
                query=user_query,
                kb_ids=kb_ids,
                top_k=5
            )
            tools_called += 1

            if show_steps:
                await record_step({"type": "thought", "content": "这是事实型问题，先检索知识库证据再作答。"})
                await record_step({"type": "action", "tool": "search_knowledge_base", "input": json.dumps({"query": user_query, "top_k": 5}, ensure_ascii=False)})
                await record_step({"type": "observation", "content": preloaded_kb_observation})

            if self._is_kb_observation_unreliable("search_knowledge_base", preloaded_kb_observation):
                grounded_answer = (
                    "我暂时无法从知识库检索到可靠信息，"
                    "因此不能给出基于证据的结论。"
                    f"检索反馈: {preloaded_kb_observation or '未返回有效结果'}"
                )
                history.append({"role": "user", "content": user_query})
                history.append({"role": "assistant", "content": grounded_answer})
                self._save_session_history(session_key, history)
                return {
                    "answer": grounded_answer,
                    "steps": steps if show_steps else [],
                    "success": False,
                    "iterations": 1,
                    "note": "知识库前置检索未获得可靠证据"
                }

        prompt = self._build_prompt(user_query, history)
        if preloaded_kb_observation:
            prompt += (
                "\n已检索证据如下，请优先基于这些证据回答：\n"
                f"{preloaded_kb_observation}\n"
                "若证据不足，请明确说明证据不足，不要编造。\n"
            )
        runtime_temperature = 0.1 if temperature is None else temperature
        
        try:
            for iteration in range(runtime_max_iterations):
                logger.info(f"Agent iteration {iteration + 1}/{runtime_max_iterations}")
                
                # 调用 LLM 生成响应
                response = await self.llm_service.generate(
                    prompt=prompt,
                    max_tokens=500,
                    temperature=runtime_temperature,
                    llm_model=llm_model
                )
                
                llm_output = response.get('text', '')
                logger.debug(f"LLM output: {llm_output}")
                
                # 记录思考过程
                thought_match = re.search(r'Thought:\s*(.+?)(?:\n|$)', llm_output, re.IGNORECASE)
                if thought_match:
                    thought = thought_match.group(1).strip()
                    await record_step({
                        "type": "thought",
                        "content": thought
                    })
                
                # 检查是否有最终答案
                final_answer = self._parse_final_answer(llm_output)
                if final_answer:
                    if kb_unreliable:
                        grounded_answer = (
                            "我暂时无法从知识库检索到可靠信息，"
                            "因此不能给出基于证据的结论。"
                            f"检索反馈: {kb_last_observation or '未返回有效结果'}"
                        )
                        history.append({"role": "user", "content": user_query})
                        history.append({"role": "assistant", "content": grounded_answer})
                        self._save_session_history(session_key, history)
                        duration_ms = int((time.time() - start_time) * 1000)
                        logger.info(
                            "Agent metrics: %s",
                            json.dumps({
                                "session_id": session_id,
                                "iterations": iteration + 1,
                                "tools_called": tools_called,
                                "duration_ms": duration_ms,
                                "success": False,
                                "note": "kb_unreliable_guard_on_final"
                            }, ensure_ascii=False)
                        )
                        return {
                            "answer": grounded_answer,
                            "steps": steps if show_steps else [],
                            "success": False,
                            "iterations": iteration + 1,
                            "note": "知识库检索失败，已阻止无依据回答"
                        }

                    if show_steps:
                        await record_step({
                            "type": "final_answer",
                            "content": final_answer
                        })
                    history.append({"role": "user", "content": user_query})
                    history.append({"role": "assistant", "content": final_answer})
                    self._save_session_history(session_key, history)
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.info(
                        "Agent metrics: %s",
                        json.dumps({
                            "session_id": session_id,
                            "iterations": iteration + 1,
                            "tools_called": tools_called,
                            "duration_ms": duration_ms,
                            "success": True
                        }, ensure_ascii=False)
                    )
                    return {
                        "answer": final_answer,
                        "steps": steps if show_steps else [],
                        "success": True,
                        "iterations": iteration + 1
                    }
                
                # 解析并执行 Action
                action_result = self._parse_action(llm_output)
                if action_result:
                    action_name, action_input = action_result
                    
                    # 执行工具
                    if action_name in self.tools:
                        tools_called += 1
                        if show_steps:
                            await record_step({
                                "type": "action",
                                "tool": action_name,
                                "input": action_input
                            })
                        
                        try:
                            # 解析 JSON 输入
                            input_params = json.loads(action_input)
                            if isinstance(input_params, dict):
                                if action_name == "search_knowledge_base" and kb_ids:
                                    allowed_kb_ids = [int(x) for x in kb_ids]
                                    if "kb_id" in input_params and int(input_params.get("kb_id")) not in allowed_kb_ids:
                                        observation = "EVIDENCE_NONE: 请求的知识库不在允许范围内"
                                        if show_steps:
                                            await record_step({"type": "observation", "content": observation})
                                        kb_unreliable = True
                                        kb_last_observation = observation
                                        prompt += f"\n{llm_output}\nObservation: {observation}\n"
                                        continue
                                    if "kb_id" not in input_params and "kb_ids" not in input_params:
                                        input_params["kb_ids"] = allowed_kb_ids
                                observation = await self.tools[action_name].arun(**input_params)
                            elif input_params in (None, "", []):
                                observation = await self.tools[action_name].arun()
                            else:
                                observation = await self.tools[action_name].arun(input_params)
                        except json.JSONDecodeError:
                            # 如果不是 JSON，按无参或单字符串参数处理
                            if action_input.strip() in ("", "{}", "null", "None"):
                                observation = await self.tools[action_name].arun()
                            else:
                                observation = await self.tools[action_name].arun(action_input)
                        except Exception as e:
                            observation = f"工具执行错误: {str(e)}"
                        
                        if show_steps:
                            await record_step({
                                "type": "observation",
                                "content": observation
                            })

                        if self._is_kb_observation_unreliable(action_name, observation):
                            kb_unreliable = True
                            kb_last_observation = observation
                        
                        # 更新 prompt，加入观察结果
                        prompt += f"\n{llm_output}\nObservation: {observation}\n"
                        if kb_unreliable:
                            prompt += (
                                "\n重要约束: 知识库检索未返回可靠证据，"
                                "后续回答只能明确说明未检索到可信信息，"
                                "禁止基于常识或记忆编造具体事实。\n"
                            )
                    else:
                        error_msg = f"未找到工具: {action_name}"
                        if show_steps:
                            await record_step({
                                "type": "error",
                                "content": error_msg
                            })
                        prompt += f"\n{llm_output}\nObservation: {error_msg}\n"
                else:
                    # 没有识别到 Action 或 Final Answer，尝试直接返回
                    if kb_unreliable:
                        grounded_answer = (
                            "我暂时无法从知识库检索到可靠信息，"
                            "因此不能给出基于证据的结论。"
                            f"检索反馈: {kb_last_observation or '未返回有效结果'}"
                        )
                        history.append({"role": "user", "content": user_query})
                        history.append({"role": "assistant", "content": grounded_answer})
                        self._save_session_history(session_key, history)
                        duration_ms = int((time.time() - start_time) * 1000)
                        logger.info(
                            "Agent metrics: %s",
                            json.dumps({
                                "session_id": session_id,
                                "iterations": iteration + 1,
                                "tools_called": tools_called,
                                "duration_ms": duration_ms,
                                "success": False,
                                "note": "kb_unreliable_guard"
                            }, ensure_ascii=False)
                        )
                        return {
                            "answer": grounded_answer,
                            "steps": steps if show_steps else [],
                            "success": False,
                            "iterations": iteration + 1,
                            "note": "知识库检索失败，已阻止无依据回答"
                        }

                    fallback_answer = llm_output or "抱歉，未获得有效回答。"
                    history.append({"role": "user", "content": user_query})
                    history.append({"role": "assistant", "content": fallback_answer})
                    self._save_session_history(session_key, history)
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.info(
                        "Agent metrics: %s",
                        json.dumps({
                            "session_id": session_id,
                            "iterations": iteration + 1,
                            "tools_called": tools_called,
                            "duration_ms": duration_ms,
                            "success": True,
                            "note": "fallback_raw_output"
                        }, ensure_ascii=False)
                    )
                    return {
                        "answer": fallback_answer,
                        "steps": steps if show_steps else [],
                        "success": True,
                        "iterations": iteration + 1,
                        "note": "未识别到标准格式，返回原始输出"
                    }
            
            # 达到最大迭代次数
            max_iter_answer = "抱歉，我无法在限定步骤内完成任务，请尝试简化问题或提供更多信息。"
            history.append({"role": "user", "content": user_query})
            history.append({"role": "assistant", "content": max_iter_answer})
            self._save_session_history(session_key, history)
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Agent metrics: %s",
                json.dumps({
                    "session_id": session_id,
                    "iterations": runtime_max_iterations,
                    "tools_called": tools_called,
                    "duration_ms": duration_ms,
                    "success": False,
                    "error": "max_iterations_reached"
                }, ensure_ascii=False)
            )
            return {
                "answer": max_iter_answer,
                "steps": steps if show_steps else [],
                "success": False,
                "iterations": runtime_max_iterations,
                "error": "达到最大迭代次数"
            }
            
        except Exception as e:
            logger.error(f"Agent execution failed: {str(e)}")
            error_answer = f"执行过程中发生错误: {str(e)}"
            history.append({"role": "user", "content": user_query})
            history.append({"role": "assistant", "content": error_answer})
            self._save_session_history(session_key, history)
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Agent metrics: %s",
                json.dumps({
                    "session_id": session_id,
                    "iterations": 0,
                    "tools_called": tools_called,
                    "duration_ms": duration_ms,
                    "success": False,
                    "error": str(e)
                }, ensure_ascii=False)
            )
            return {
                "answer": error_answer,
                "steps": steps if show_steps else [],
                "success": False,
                "iterations": 0,
                "error": str(e)
            }
    
    def get_tools_info(self) -> List[Dict[str, str]]:
        """获取所有工具信息"""
        return [
            {
                "name": tool.name,
                "description": tool.description
            }
            for tool in self.tools.values()
        ]
