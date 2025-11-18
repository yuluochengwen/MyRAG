# Ollama LLM集成功能说明

## 功能概述

本次更新为MyRAG系统的智能助手功能集成了**Ollama LLM支持**，用户现在可以在创建或编辑智能助手时选择使用Ollama的本地模型或云端模型，与原有的Transformers本地模型和远程API模型形成互补。

## 主要特性

### 1. 多LLM提供方支持
- **Transformers本地模型**：使用HuggingFace Transformers加载本地模型（原有功能）
- **Ollama模型**：通过Ollama API调用本地或云端LLM模型（✨新增）
- **远程API模型**：OpenAI、Azure等云服务（预留接口）

### 2. 自动模型发现
- 系统自动检测Ollama服务可用性
- 实时获取已安装的Ollama模型列表
- 智能过滤embedding模型，仅显示LLM模型

### 3. 统一对话接口
- 支持标准对话和流式对话
- 保持上下文记忆和RAG增强功能
- provider参数透明路由到对应服务

## 技术实现

### 后端架构

#### 1. OllamaLLMService (`Backend/app/services/ollama_llm_service.py`)
```python
class OllamaLLMService:
    """Ollama LLM服务"""
    
    def is_available(self) -> bool:
        """检查Ollama服务可用性"""
    
    def list_available_models(self) -> List[Dict]:
        """获取LLM模型列表（自动过滤embedding模型）"""
    
    async def chat(self, model, messages, temperature) -> str:
        """标准对话"""
    
    async def chat_stream(self, model, messages, temperature):
        """流式对话"""
```

**关键特性：**
- 基于HTTP API调用 `http://localhost:11434`
- 模型名称智能识别（Qwen、LLaMA、DeepSeek等）
- 模型大小自动计算和格式化
- 超时保护和错误处理

#### 2. ModelScanner扩展 (`Backend/app/services/model_scanner.py`)
```python
def get_all_llm_models(self) -> Dict[str, List[Dict]]:
    """返回: {"local": [...], "ollama": [...], "remote": [...]}"""
```

**输出示例：**
```json
{
  "local": [{"name": "Qwen3-8B", "type": "Qwen", ...}],
  "ollama": [
    {"name": "qwen2.5:7b", "type": "Qwen", "size": 4.36, "provider": "ollama"},
    {"name": "deepseek-r1:8b", "type": "DeepSeek", "size": 4.87, "provider": "ollama"}
  ],
  "remote": [...]
}
```

#### 3. ChatService增强 (`Backend/app/services/chat_service.py`)
在 `_generate_answer()` 和 `_generate_answer_stream()` 中添加Ollama路由：

```python
if llm_provider == 'ollama':
    from app.services.ollama_llm_service import get_ollama_llm_service
    ollama_service = get_ollama_llm_service()
    return await ollama_service.chat(model=model_name, messages=messages, ...)
```

**支持功能：**
- ✅ 上下文记忆
- ✅ RAG知识库增强
- ✅ 流式响应
- ✅ 系统提示词
- ✅ 温度控制

#### 4. API层验证 (`Backend/app/api/assistant.py`)
```python
# 创建/更新助手时验证Ollama模型
if assistant_data.llm_provider == "ollama":
    if not ollama_service.is_available():
        raise HTTPException(503, "Ollama服务不可用")
    
    if model_name not in available_models:
        raise HTTPException(404, "模型不存在或未安装")
```

#### 5. 数据模型更新 (`Backend/app/models/schemas.py`)
```python
class AssistantCreate(BaseModel):
    llm_provider: str = Field(
        default="local", 
        description="LLM提供方: local, ollama, openai, azure"
    )
    
    @validator('llm_provider')
    def validate_llm_provider(cls, v):
        if v not in ['local', 'transformers', 'ollama', 'openai', 'azure']:
            raise ValueError('不支持的LLM提供方')
        return v
```

### 前端实现

#### 1. 模型列表展示 (`Frontend/js/intelligent-assistant.js`)
```javascript
function renderLLMOptions() {
    // 🤖 本地模型 (Transformers)
    if (llmModels.local && llmModels.local.length > 0) {
        html += '<optgroup label="🤖 本地模型 (Transformers)">';
        // ...
    }
    
    // 🦙 Ollama模型
    if (llmModels.ollama && llmModels.ollama.length > 0) {
        html += '<optgroup label="🦙 Ollama模型">';
        llmModels.ollama.forEach(model => {
            html += `<option value="${model.name}" data-provider="ollama">
                ${model.name} (${model.size}GB)
            </option>`;
        });
        html += '</optgroup>';
    }
    
    // ☁️ 远程API
    // ...
}
```

**UI特性：**
- 使用emoji图标区分不同provider（🤖 Transformers、🦙 Ollama、☁️ 远程）
- 显示模型大小信息（如 `qwen2.5:7b (4.36GB)`）
- 使用 `data-provider` 属性存储提供方信息

#### 2. 表单提交
```javascript
const data = {
    llm_model: formData.get('llm_model'),
    llm_provider: document.querySelector('#llmModelSelect option:checked')?.dataset.provider || 'local',
    // ...
};
```

## 使用指南

### 前置条件

1. **安装Ollama**
   ```bash
   # Windows/Mac/Linux
   curl -fsSL https://ollama.ai/install.sh | sh
   ```

2. **启动Ollama服务**
   ```bash
   ollama serve
   ```
   默认监听 `http://localhost:11434`

3. **下载模型**
   ```bash
   # 推荐的中文模型
   ollama pull qwen2.5:7b          # 通用对话（4.4GB）
   ollama pull deepseek-r1:8b      # 推理增强（4.9GB）
   ollama pull deepseek-r1:1.5b    # 轻量级（1GB）
   
   # 查看已安装模型
   ollama list
   ```

### 创建使用Ollama的智能助手

1. 访问智能助手管理页面：`http://localhost:8000/intelligent-assistant.html`

2. 点击"创建智能助手"

3. 填写基本信息：
   - **助手名称**：例如"Ollama对话助手"
   - **描述**：例如"使用Qwen2.5模型的智能助手"

4. 选择LLM模型：
   - 在"大语言模型"下拉框中找到 **"🦙 Ollama模型"** 分组
   - 选择已安装的模型（如 `qwen2.5:7b (4.36GB)`）
   - **系统会自动识别并设置 `llm_provider="ollama"`**

5. （可选）配置知识库和系统提示词

6. 点击"创建"

### 验证功能

1. **检查助手详情**
   - LLM模型应显示为 `qwen2.5:7b`
   - LLM提供方应显示为 `ollama`

2. **进行对话测试**
   - 点击助手卡片进入对话页面
   - 发送测试消息
   - 确认回答由Ollama模型生成

## 配置说明

### Ollama服务配置
在 `Backend/config.yaml` 中（复用embedding配置）：

```yaml
embedding:
  ollama:
    base_url: "http://localhost:11434"  # Ollama服务地址
    timeout: 30                          # API超时时间（秒）
    default_model: "nomic-embed-text"    # 默认embedding模型
```

**注意：** LLM功能复用此配置的 `base_url` 和 `timeout`。

### 自定义Ollama地址
如果Ollama运行在其他端口或服务器：

```yaml
embedding:
  ollama:
    base_url: "http://192.168.1.100:11434"  # 远程Ollama服务器
    timeout: 60                              # 增加超时（网络较慢时）
```

## API接口

### 获取LLM模型列表
```http
GET /api/assistants/models/llm
```

**响应示例：**
```json
{
  "local": [
    {"name": "Qwen3-8B", "type": "Qwen", "size": "15.5GB"}
  ],
  "ollama": [
    {"name": "qwen2.5:7b", "type": "Qwen", "size": 4.36, "provider": "ollama"},
    {"name": "deepseek-r1:8b", "type": "DeepSeek", "size": 4.87, "provider": "ollama"}
  ],
  "remote": []
}
```

### 创建使用Ollama的助手
```http
POST /api/assistants
Content-Type: application/json

{
  "name": "Ollama助手",
  "description": "使用Ollama模型",
  "llm_model": "qwen2.5:7b",
  "llm_provider": "ollama",
  "embedding_model": "BERT-Base",
  "system_prompt": "你是一个专业的AI助手",
  "color_theme": "blue"
}
```

## 性能对比

| 特性 | Transformers本地 | Ollama | 远程API |
|------|-----------------|--------|---------|
| 推理速度 | 慢（CPU offload） | 快（优化推理） | 快（云端） |
| 显存占用 | 高（6-8GB） | 中（4-6GB） | 无 |
| 模型切换 | 慢（加载模型） | 快（已预加载） | 即时 |
| 离线可用 | ✅ | ✅ | ❌ |
| 成本 | 免费 | 免费 | 按量付费 |

## 故障排查

### 问题1: "Ollama服务不可用"
**原因：** Ollama未启动或端口不正确

**解决：**
```bash
# 检查Ollama进程
ps aux | grep ollama

# 启动Ollama
ollama serve

# 验证连接
curl http://localhost:11434/api/tags
```

### 问题2: "模型不存在或未安装"
**原因：** 选择的模型未下载

**解决：**
```bash
# 查看已安装模型
ollama list

# 下载模型
ollama pull qwen2.5:7b

# 再次尝试创建助手
```

### 问题3: 对话生成失败
**原因：** 模型太大导致OOM或网络超时

**解决：**
1. 使用更小的模型（如 `deepseek-r1:1.5b`）
2. 增加超时时间：修改 `config.yaml` 中的 `timeout: 60`
3. 检查系统内存：`ollama ps`

### 问题4: 前端不显示Ollama模型
**原因：** 
- Ollama服务未启动
- 后端未正确扫描模型

**调试：**
```bash
# 测试后端API
curl http://localhost:8000/api/assistants/models/llm

# 应包含 "ollama": [...] 字段
```

## 测试验证

运行集成测试脚本：
```bash
cd c:\Users\Man\Desktop\MyRAG
conda activate MyRAG
python test_ollama_llm_integration.py
```

**预期输出：**
```
🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙
Ollama LLM集成测试
🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙🦙

测试1: Ollama服务可用性 ✅ 通过
测试2: LLM模型列表API ✅ 通过
测试3: Ollama对话功能 ✅ 通过
测试4: 创建智能助手 ✅ 通过

🎉 所有测试通过！Ollama LLM集成成功！
```

## 最佳实践

### 1. 模型选择建议
- **日常对话**：`qwen2.5:7b` 或 `qwen2.5:14b`（中文优秀）
- **代码生成**：`codellama:7b` 或 `deepseek-coder:6.7b`
- **推理任务**：`deepseek-r1:8b`（带CoT推理）
- **资源受限**：`deepseek-r1:1.5b` 或 `qwen2.5:3b`

### 2. 性能优化
- 预加载常用模型：`ollama pull <model>`
- 使用GPU加速：确保Ollama检测到GPU
- 调整并发限制：Ollama默认支持多请求

### 3. 知识库集成
Ollama模型可以无缝配合RAG使用：
1. 创建知识库（使用Transformers或Ollama embedding）
2. 创建助手时选择该知识库
3. 选择Ollama LLM模型
4. Ollama模型将基于检索到的知识生成回答

## 未来扩展

- [ ] 支持Ollama云端模型（需API密钥）
- [ ] 模型性能监控和统计
- [ ] 自动模型推荐（根据任务类型）
- [ ] 模型量化选项（4bit/8bit）
- [ ] 批量对话优化

## 相关文档

- [Ollama官方文档](https://github.com/ollama/ollama)
- [Ollama模型库](https://ollama.ai/library)
- [智能助手功能说明](./功能实现说明_智能助手.md)
- [Ollama Embedding集成](./Ollama嵌入模型集成功能说明.md)

## 更新日志

**2025-01-18**
- ✨ 新增Ollama LLM服务支持
- ✨ 智能助手支持选择Ollama模型
- ✨ 前端UI区分不同provider
- ✅ 通过完整集成测试
- 📝 完成功能文档

---

**作者：** MyRAG开发团队  
**版本：** v1.1.0  
**日期：** 2025-01-18
