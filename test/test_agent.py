"""
Agent 功能测试脚本
测试 Agent 的基本功能和工具调用
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "Backend"))

from app.services.agent_service import AgentService, Tool


class MockLLMService:
    """模拟 LLM 服务用于测试"""
    
    async def generate(self, prompt: str, **kwargs):
        """模拟 LLM 响应"""
        print(f"\n{'='*60}")
        print("LLM Prompt:")
        print(prompt)
        print(f"{'='*60}\n")
        
        # 根据 prompt 返回模拟响应
        if "现在几点" in prompt or "时间" in prompt:
            return {
                "text": """Thought: 用户想知道当前时间，我需要使用 get_current_time 工具
Action: get_current_time
Action Input: {}
"""
            }
        elif "计算" in prompt or "+" in prompt or "*" in prompt:
            return {
                "text": """Thought: 这是一个数学计算问题，我需要使用 calculator 工具
Action: calculator
Action Input: {"expression": "2+3*4"}
"""
            }
        elif "知识库" in prompt:
            return {
                "text": """Thought: 用户想搜索知识库，我需要使用 search_knowledge_base 工具
Action: search_knowledge_base
Action Input: {"query": "RAG", "top_k": 3}
"""
            }
        else:
            # 如果包含 Observation，说明是第二轮，应该返回最终答案
            if "Observation:" in prompt:
                return {
                    "text": """Thought: 我已经获得了必要的信息，现在可以给出最终答案
Final Answer: 根据工具返回的结果，这是最终答案。
"""
                }
            else:
                return {
                    "text": """Thought: 这是一个简单问题，不需要使用工具
Final Answer: 这是一个直接的回答。
"""
                }


class MockKnowledgeBaseService:
    """模拟知识库服务"""
    
    def search(self, kb_id, query, top_k=3):
        """模拟搜索"""
        return [
            {
                "content": f"这是关于 {query} 的第1个文档内容...",
                "metadata": {"source": "document1.pdf"}
            },
            {
                "content": f"这是关于 {query} 的第2个文档内容...",
                "metadata": {"source": "document2.pdf"}
            }
        ]
    
    def get_all_knowledge_bases(self):
        """获取所有知识库"""
        return [
            {"id": 1, "name": "知识库1"},
            {"id": 2, "name": "知识库2"}
        ]


async def test_basic_agent():
    """测试基本 Agent 功能"""
    print("\n" + "="*70)
    print("测试 1: 基本 Agent 功能")
    print("="*70)
    
    # 创建 Agent
    llm_service = MockLLMService()
    kb_service = MockKnowledgeBaseService()
    agent = AgentService(llm_service, kb_service, max_iterations=3)
    
    # 测试问题
    result = await agent.run("现在几点了？")
    
    print("\n" + "-"*70)
    print("测试结果:")
    print(f"成功: {result['success']}")
    print(f"迭代次数: {result.get('iterations', 'N/A')}")
    print(f"答案: {result['answer']}")
    print(f"执行步骤数: {len(result['steps'])}")
    print("\n执行步骤:")
    for i, step in enumerate(result['steps'], 1):
        print(f"  {i}. {step['type']}: {step.get('content', step.get('tool', 'N/A'))}")
    print("-"*70)


async def test_calculator_tool():
    """测试计算器工具"""
    print("\n" + "="*70)
    print("测试 2: 计算器工具")
    print("="*70)
    
    llm_service = MockLLMService()
    agent = AgentService(llm_service, None, max_iterations=3)
    
    result = await agent.run("计算 2+3*4")
    
    print("\n" + "-"*70)
    print("测试结果:")
    print(f"成功: {result['success']}")
    print(f"答案: {result['answer']}")
    print("-"*70)


async def test_knowledge_base_search():
    """测试知识库搜索"""
    print("\n" + "="*70)
    print("测试 3: 知识库搜索工具")
    print("="*70)
    
    llm_service = MockLLMService()
    kb_service = MockKnowledgeBaseService()
    agent = AgentService(llm_service, kb_service, max_iterations=3)
    
    result = await agent.run("搜索知识库中关于 RAG 的内容")
    
    print("\n" + "-"*70)
    print("测试结果:")
    print(f"成功: {result['success']}")
    print(f"答案: {result['answer']}")
    print("-"*70)


async def test_custom_tool():
    """测试自定义工具注册"""
    print("\n" + "="*70)
    print("测试 4: 自定义工具")
    print("="*70)
    
    llm_service = MockLLMService()
    agent = AgentService(llm_service, None, max_iterations=3)
    
    # 注册自定义工具
    def reverse_string(text: str) -> str:
        """反转字符串"""
        return text[::-1]
    
    agent.register_tool(
        name="reverse_string",
        description="反转输入的字符串。参数: text-要反转的文本",
        func=reverse_string
    )
    
    # 获取工具列表
    tools = agent.get_tools_info()
    
    print("\n注册的工具:")
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description']}")
    
    print("-"*70)


def test_tool_execution():
    """测试工具直接执行"""
    print("\n" + "="*70)
    print("测试 5: 工具直接执行")
    print("="*70)
    
    llm_service = MockLLMService()
    kb_service = MockKnowledgeBaseService()
    agent = AgentService(llm_service, kb_service)
    
    # 测试计算器
    calc_tool = agent.tools['calculator']
    result1 = calc_tool.run(expression="10 + 20 * 3")
    print(f"\n计算器测试: 10 + 20 * 3 = {result1}")
    
    # 测试时间
    time_tool = agent.tools['get_current_time']
    result2 = time_tool.run()
    print(f"时间工具测试: {result2}")
    
    # 测试知识库搜索
    kb_tool = agent.tools['search_knowledge_base']
    result3 = kb_tool.run(query="测试查询", top_k=2)
    print(f"知识库搜索测试:\n{result3}")
    
    print("\n" + "-"*70)


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*70)
    print("Agent 功能测试套件")
    print("="*70)
    
    try:
        # 测试 1: 基本功能
        await test_basic_agent()
        
        # 测试 2: 计算器
        await test_calculator_tool()
        
        # 测试 3: 知识库搜索
        await test_knowledge_base_search()
        
        # 测试 4: 自定义工具
        await test_custom_tool()
        
        # 测试 5: 工具直接执行
        test_tool_execution()
        
        print("\n" + "="*70)
        print("✅ 所有测试完成！")
        print("="*70 + "\n")
        
    except Exception as e:
        print("\n" + "="*70)
        print(f"❌ 测试失败: {str(e)}")
        print("="*70 + "\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
