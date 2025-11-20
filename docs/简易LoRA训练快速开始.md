# 🚀 简易 LoRA 训练 - 5 分钟快速上手

## 📦 **第一步：安装依赖**

打开 PowerShell，执行：

```powershell
cd C:\Users\Man\Desktop\MyRAG
conda activate MyRAG
pip install peft>=0.11.0 datasets>=2.18.0 trl>=0.8.0
```

## 🗄️ **第二步：初始化数据库**

在 MySQL 中执行（只需执行一次）：

```sql
-- 复制 Backend/scripts/init_simple_lora_tables.sql 的内容
-- 在 MySQL Workbench 或命令行中执行
```

或使用命令行：

```powershell
mysql -u root -p rag_system < Backend\scripts\init_simple_lora_tables.sql
```

## 🎯 **第三步：启动服务**

### 方法 1：使用启动脚本（推荐）

```powershell
.\start-training.bat
```

### 方法 2：手动启动

```powershell
cd Backend
python main.py
```

## 🌐 **第四步：开始训练**

1. **打开浏览器**，访问：
   ```
   http://localhost:8000/static/simple-lora-training.html
   ```

2. **上传数据集**
   - 拖拽 JSON 文件或点击上传
   - 系统已提供示例数据集：`TrainingData/example_alpaca_dataset.json`

3. **选择基座模型**
   - 从下拉列表选择（例如：`DeepSeek-R1-Distill-Qwen-1.5B`）

4. **输入任务名称**
   - 例如：`my_first_lora`

5. **点击"开始训练"**
   - 系统自动配置参数
   - 后台开始训练
   - 右侧实时显示进度

## 📊 **监控训练进度**

训练任务会显示：
- ✅ **状态**：等待中 → 训练中 → 已完成
- 📈 **进度条**：实时更新百分比
- 🔄 **当前轮次**：显示训练到第几轮

## 🎉 **训练完成后**

### 选项 1：部署到 Ollama（推荐）

1. 访问模型管理页面：
   ```
   http://localhost:8000/static/model-management.html
   ```

2. 切换到"LoRA 管理"标签

3. 点击"扫描新模型"

4. 找到你的模型，点击"部署"

5. 在智能助手中绑定使用

### 选项 2：直接使用

训练结果保存在：
```
Models/LoRA/<任务名>_<时间戳>/
├── adapter_config.json
├── adapter_model.safetensors
└── tokenizer配置文件
```

## 💡 **示例数据集**

系统已提供示例数据集 `TrainingData/example_alpaca_dataset.json`，包含 10 个样本：
- 人工智能解释
- 编程学习指导
- 翻译任务
- 数学计算
- 健康建议
- ...等

你可以直接使用它来测试训练流程！

## ⏱️ **训练时间估算**

| 样本数 | 显卡 | 预计时间 |
|--------|------|---------|
| 10 样本 | RTX 3060 | ~5 分钟 |
| 100 样本 | RTX 3060 | ~15 分钟 |
| 500 样本 | RTX 3060 | ~40 分钟 |
| 2000 样本 | RTX 3060 | ~2.5 小时 |

## ❓ **遇到问题？**

### 显存不足

训练参数已针对 6GB 显卡优化，如果仍然不足：
- 确保没有其他程序占用显卡
- 关闭浏览器多余标签页
- 重启电脑释放显存

### 数据格式错误

确保 JSON 格式正确：
```json
[
    {
        "instruction": "问题",
        "input": "",
        "output": "答案"
    }
]
```

### 训练失败

查看任务状态中的错误消息，或查看后端日志：
```powershell
type logs\app.log
```

## 📚 **更多功能**

- 📖 完整文档：`docs/简易LoRA训练功能说明.md`
- 🔧 API 接口：查看文档中的接口说明
- 💬 社区支持：提交 Issue 或 PR

---

## 🎊 **就这么简单！**

只需：
1. 上传数据集
2. 选择模型
3. 点击开始

系统自动完成：
- ✨ 参数优化
- ✨ 4-bit 量化
- ✨ LoRA 配置
- ✨ 训练监控
- ✨ 模型保存

**专注于数据和应用，让技术细节自动化！** 🚀
