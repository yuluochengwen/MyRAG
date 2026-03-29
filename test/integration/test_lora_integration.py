"""
LoRA 微调系统集成测试

测试完整的训练和推理流程
"""
import pytest
import asyncio
import json
from pathlib import Path

# 测试数据
SAMPLE_ALPACA_DATA = [
    {
        "instruction": "解释什么是机器学习",
        "input": "",
        "output": "机器学习是人工智能的一个分支，它使计算机能够从数据中学习并改进性能，而无需明确编程。"
    },
    {
        "instruction": "翻译成英文",
        "input": "你好，世界",
        "output": "Hello, World"
    }
]

SAMPLE_CONVERSATION_DATA = [
    {
        "conversations": [
            {"role": "user", "content": "什么是Python？"},
            {"role": "assistant", "content": "Python是一种高级编程语言，以其简洁的语法和强大的功能而闻名。"}
        ]
    }
]


class TestDatasetValidator:
    """测试数据集验证服务"""
    
    @pytest.mark.asyncio
    async def test_validate_alpaca_format(self):
        """测试 Alpaca 格式验证"""
        from app.services.dataset_validator_service import DatasetValidatorService
        
        validator = DatasetValidatorService()
        
        # 创建临时测试文件
        test_file = Path("test_alpaca.json")
        test_file.write_text(json.dumps(SAMPLE_ALPACA_DATA, ensure_ascii=False))
        
        try:
            result = await validator.validate_dataset(str(test_file))
            
            assert result['valid'] == True
            assert result['format'] == 'alpaca'
            assert result['sample_count'] == 2
            assert len(result['errors']) == 0
        finally:
            test_file.unlink()
    
    @pytest.mark.asyncio
    async def test_validate_conversation_format(self):
        """测试 Conversation 格式验证"""
        from app.services.dataset_validator_service import DatasetValidatorService
        
        validator = DatasetValidatorService()
        
        test_file = Path("test_conversation.json")
        test_file.write_text(json.dumps(SAMPLE_CONVERSATION_DATA, ensure_ascii=False))
        
        try:
            result = await validator.validate_dataset(str(test_file))
            
            assert result['valid'] == True
            assert result['format'] == 'conversation'
            assert result['sample_count'] == 1
        finally:
            test_file.unlink()
    
    @pytest.mark.asyncio
    async def test_validate_invalid_format(self):
        """测试无效格式"""
        from app.services.dataset_validator_service import DatasetValidatorService
        
        validator = DatasetValidatorService()
        
        invalid_data = [{"invalid": "data"}]
        test_file = Path("test_invalid.json")
        test_file.write_text(json.dumps(invalid_data))
        
        try:
            result = await validator.validate_dataset(str(test_file))
            
            assert result['valid'] == False
            assert len(result['errors']) > 0
        finally:
            test_file.unlink()


class TestLoRAService:
    """测试 LoRA 模型管理服务"""
    
    @pytest.mark.asyncio
    async def test_scan_lora_models(self):
        """测试扫描 LoRA 模型"""
        from app.services.lora_service import LoRAService
        from app.core.database import db_manager
        
        service = LoRAService(db_manager)
        models = await service.scan_lora_models()
        
        assert isinstance(models, list)
        # 注意：实际测试时可能没有模型，这里只验证返回类型
    
    @pytest.mark.asyncio
    async def test_get_lora_models_by_base(self):
        """测试按基座模型筛选"""
        from app.services.lora_service import LoRAService
        from app.core.database import db_manager
        
        service = LoRAService(db_manager)
        models = await service.get_lora_models_by_base("Qwen3-8B")
        
        assert isinstance(models, list)


class TestLoRAInferenceService:
    """测试 LoRA 推理服务"""
    
    @pytest.mark.asyncio
    async def test_cache_management(self):
        """测试缓存管理"""
        from app.services.lora_inference_service import LoRAInferenceService
        
        service = LoRAInferenceService()
        
        # 验证缓存初始化
        assert hasattr(service, 'base_model_cache')
        assert hasattr(service, 'lora_model_cache')
    
    @pytest.mark.asyncio
    async def test_unload_lora_model(self):
        """测试卸载 LoRA 模型"""
        from app.services.lora_inference_service import LoRAInferenceService
        
        service = LoRAInferenceService()
        
        # 测试卸载不存在的模型（应该不报错）
        service.unload_lora_model(999)


class TestLoRAAPI:
    """测试 LoRA API 端点"""
    
    @pytest.mark.asyncio
    async def test_get_base_models(self, client):
        """测试获取基座模型列表"""
        response = await client.get("/api/lora/base-models")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_lora_models(self, client):
        """测试获取 LoRA 模型列表"""
        response = await client.get("/api/lora/models")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_validate_dataset_api(self, client):
        """测试数据集验证 API"""
        test_file = Path("test_api_alpaca.json")
        test_file.write_text(json.dumps(SAMPLE_ALPACA_DATA, ensure_ascii=False))
        
        try:
            with open(test_file, 'rb') as f:
                files = {'file': ('test.json', f, 'application/json')}
                response = await client.post("/api/lora/validate-dataset", files=files)
            
            assert response.status_code == 200
            data = response.json()
            assert data['valid'] == True
            assert data['format'] == 'alpaca'
        finally:
            test_file.unlink()


class TestAssistantLoRAIntegration:
    """测试智能助手 LoRA 集成"""
    
    @pytest.mark.asyncio
    async def test_create_assistant_with_lora(self, client):
        """测试创建带 LoRA 的助手"""
        # 注意：这个测试需要先有可用的 LoRA 模型
        assistant_data = {
            "name": "测试助手",
            "description": "测试用助手",
            "llm_model": "Qwen3-8B",
            "llm_provider": "local",
            "embedding_model": "bge-large-zh-v1.5",
            "lora_model_id": None,  # 如果有 LoRA 模型，设置为实际 ID
            "system_prompt": "你是一个测试助手",
            "color_theme": "blue"
        }
        
        response = await client.post("/api/assistants", json=assistant_data)
        
        # 如果没有 LLM 模型，可能返回 404
        assert response.status_code in [201, 404]
    
    @pytest.mark.asyncio
    async def test_lora_model_mismatch(self, client):
        """测试 LoRA 与基座模型不匹配的情况"""
        # 这个测试需要数据库中有不匹配的 LoRA 模型
        # 实际测试时需要根据数据库状态调整
        pass


class TestEndToEndWorkflow:
    """端到端工作流测试"""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_complete_training_workflow(self, client):
        """
        测试完整的训练工作流
        
        注意：这是一个慢速测试，需要实际的 GPU 和模型
        在 CI 环境中应该跳过
        """
        # 1. 验证数据集
        test_file = Path("test_training.json")
        test_file.write_text(json.dumps(SAMPLE_ALPACA_DATA * 10, ensure_ascii=False))
        
        try:
            with open(test_file, 'rb') as f:
                files = {'file': ('test.json', f, 'application/json')}
                response = await client.post("/api/lora/validate-dataset", files=files)
            
            assert response.status_code == 200
            
            # 2. 提交训练任务（实际环境中会执行）
            # 注意：这里只测试 API 调用，不实际训练
            # 实际训练需要 GPU 和较长时间
            
        finally:
            test_file.unlink()


# Pytest fixtures
@pytest.fixture
async def client():
    """创建测试客户端"""
    from httpx import AsyncClient
    from app.main import app
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


# 运行测试的说明
"""
运行所有测试：
    pytest test/test_lora_integration.py -v

运行快速测试（跳过慢速测试）：
    pytest test/test_lora_integration.py -v -m "not slow"

运行特定测试类：
    pytest test/test_lora_integration.py::TestDatasetValidator -v

生成覆盖率报告：
    pytest test/test_lora_integration.py --cov=app.services --cov-report=html
"""
