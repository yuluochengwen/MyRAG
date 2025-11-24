"""
Agent Service - 智能体服务
实现基于 ReAct 框架的简单 Agent 系统
"""
import json
import re
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Tool:
    """工具基类"""
    
    def __init__(self, name: str, description: str, func: Callable):
        self.name = name
        self.description = description
        self.func = func
    
    def run(self, *args, **kwargs) -> str:
        """执行工具"""
        try:
            result = self.func(*args, **kwargs)
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
        
        # 注册默认工具
        self._register_default_tools()
    
    def _register_default_tools(self):
        """注册默认工具"""
        
        # 工具1: 知识库搜索
        if self.kb_service:
            def search_knowledge_base(query: str, kb_id: int = None, top_k: int = 3) -> str:
                """搜索知识库获取相关信息"""
                try:
                    if kb_id:
                        results = self.kb_service.search(kb_id, query, top_k)
                    else:
                        # 搜索所有知识库
                        all_results = []
                        kbs = self.kb_service.get_all_knowledge_bases()
                        for kb in kbs[:3]:  # 最多搜索3个知识库
                            results = self.kb_service.search(kb['id'], query, top_k=2)
                            all_results.extend(results)
                        results = all_results
                    
                    if not results:
                        return "未找到相关信息"
                    
                    # 格式化搜索结果
                    formatted = []
                    for i, doc in enumerate(results, 1):
                        content = doc.get('content', '')[:200]  # 限制长度
                        source = doc.get('metadata', {}).get('source', '未知')
                        formatted.append(f"{i}. [{source}] {content}")
                    
                    return "\n".join(formatted)
                except Exception as e:
                    return f"知识库搜索失败: {str(e)}"
            
            self.register_tool(
                name="search_knowledge_base",
                description="搜索知识库获取相关文档和信息。参数: query(必需)-搜索查询, kb_id(可选)-知识库ID, top_k(可选)-返回结果数量",
                func=search_knowledge_base
            )
        
        # 工具2: 计算器
        def calculator(expression: str) -> str:
            """执行数学计算"""
            try:
                # 安全的数学表达式求值
                allowed_chars = set('0123456789+-*/(). ')
                if not all(c in allowed_chars for c in expression):
                    return "表达式包含不允许的字符"
                
                result = eval(expression, {"__builtins__": {}}, {})
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
    
    def register_tool(self, name: str, description: str, func: Callable):
        """注册新工具"""
        self.tools[name] = Tool(name, description, func)
        logger.info(f"Tool registered: {name}")
    
    def _build_prompt(self, user_query: str) -> str:
        """构建 Agent 提示词"""
        
        # 工具列表
        tools_desc = "\n".join([
            f"- {tool.name}: {tool.description}"
            for tool in self.tools.values()
        ])
        
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

用户问题: {user_query}

开始!
"""
        return prompt
    
    def _parse_action(self, text: str) -> Optional[tuple]:
        """
        解析 LLM 输出中的 Action
        
        Returns:
            (action_name, action_input) 或 None
        """
        # 匹配 Action 和 Action Input
        action_match = re.search(r'Action:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        input_match = re.search(r'Action Input:\s*(.+?)(?:\n|$)', text, re.IGNORECASE | re.DOTALL)
        
        if not action_match:
            return None
        
        action_name = action_match.group(1).strip()
        action_input = input_match.group(1).strip() if input_match else "{}"
        
        return action_name, action_input
    
    def _parse_final_answer(self, text: str) -> Optional[str]:
        """解析最终答案"""
        match = re.search(r'Final Answer:\s*(.+)', text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
    
    async def run(self, user_query: str, session_id: str = None) -> Dict[str, Any]:
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
        steps = []
        prompt = self._build_prompt(user_query)
        
        try:
            for iteration in range(self.max_iterations):
                logger.info(f"Agent iteration {iteration + 1}/{self.max_iterations}")
                
                # 调用 LLM 生成响应
                response = await self.llm_service.generate(
                    prompt=prompt,
                    max_tokens=500,
                    temperature=0.1  # 降低随机性，使输出更稳定
                )
                
                llm_output = response.get('text', '')
                logger.debug(f"LLM output: {llm_output}")
                
                # 记录思考过程
                thought_match = re.search(r'Thought:\s*(.+?)(?:\n|$)', llm_output, re.IGNORECASE)
                if thought_match:
                    thought = thought_match.group(1).strip()
                    steps.append({
                        "type": "thought",
                        "content": thought
                    })
                
                # 检查是否有最终答案
                final_answer = self._parse_final_answer(llm_output)
                if final_answer:
                    steps.append({
                        "type": "final_answer",
                        "content": final_answer
                    })
                    return {
                        "answer": final_answer,
                        "steps": steps,
                        "success": True,
                        "iterations": iteration + 1
                    }
                
                # 解析并执行 Action
                action_result = self._parse_action(llm_output)
                if action_result:
                    action_name, action_input = action_result
                    
                    # 执行工具
                    if action_name in self.tools:
                        steps.append({
                            "type": "action",
                            "tool": action_name,
                            "input": action_input
                        })
                        
                        try:
                            # 解析 JSON 输入
                            input_params = json.loads(action_input)
                            observation = self.tools[action_name].run(**input_params)
                        except json.JSONDecodeError:
                            # 如果不是 JSON，当作字符串参数
                            observation = self.tools[action_name].run(action_input)
                        except Exception as e:
                            observation = f"工具执行错误: {str(e)}"
                        
                        steps.append({
                            "type": "observation",
                            "content": observation
                        })
                        
                        # 更新 prompt，加入观察结果
                        prompt += f"\n{llm_output}\nObservation: {observation}\n"
                    else:
                        error_msg = f"未找到工具: {action_name}"
                        steps.append({
                            "type": "error",
                            "content": error_msg
                        })
                        prompt += f"\n{llm_output}\nObservation: {error_msg}\n"
                else:
                    # 没有识别到 Action 或 Final Answer，尝试直接返回
                    return {
                        "answer": llm_output,
                        "steps": steps,
                        "success": True,
                        "iterations": iteration + 1,
                        "note": "未识别到标准格式，返回原始输出"
                    }
            
            # 达到最大迭代次数
            return {
                "answer": "抱歉，我无法在限定步骤内完成任务，请尝试简化问题或提供更多信息。",
                "steps": steps,
                "success": False,
                "iterations": self.max_iterations,
                "error": "达到最大迭代次数"
            }
            
        except Exception as e:
            logger.error(f"Agent execution failed: {str(e)}")
            return {
                "answer": f"执行过程中发生错误: {str(e)}",
                "steps": steps,
                "success": False,
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
