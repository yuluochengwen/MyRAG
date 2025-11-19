# 测试说明

本目录包含 MyRAG 项目的测试脚本，用于验证各个功能模块是否正常工作。

## 测试模块列表

1. **test_01_config.py** - 配置加载测试
   - 测试配置文件是否正确加载
   - 验证数据库、向量数据库、嵌入模型等配置

2. **test_02_database.py** - 数据库连接测试
   - 测试MySQL数据库连接
   - 检查必要的数据表是否存在

3. **test_03_services.py** - 服务单例测试
   - 验证VectorStoreService单例模式
   - 验证EmbeddingService单例模式
   - 验证TransformersService单例模式

4. **test_04_vector_store.py** - 向量存储测试
   - 测试ChromaDB向量存储功能
   - 测试添加、搜索、删除向量

5. **test_05_api_endpoints.py** - API端点测试（需要服务运行）
   - 测试健康检查端点
   - 测试知识库、智能助手、模型管理API

6. **test_06_text_splitting.py** - 文本分割测试
   - 测试递归字符分割器
   - 测试语义分割器（如果配置）

## 运行测试

### 方式1: 运行所有测试
```bash
cd test
E:/Anaconda/envs/MyRAG/python.exe test_runner.py
```

### 方式2: 运行单个测试
```bash
cd test
E:/Anaconda/envs/MyRAG/python.exe test_01_config.py
E:/Anaconda/envs/MyRAG/python.exe test_02_database.py
E:/Anaconda/envs/MyRAG/python.exe test_03_services.py
E:/Anaconda/envs/MyRAG/python.exe test_04_vector_store.py
E:/Anaconda/envs/MyRAG/python.exe test_06_text_splitting.py
```

### 方式3: API端点测试（需要先启动服务）
```bash
# 1. 先启动服务
cd ..
start-fast.bat

# 2. 在另一个终端运行测试
cd test
E:/Anaconda/envs/MyRAG/python.exe test_05_api_endpoints.py
```

## 注意事项

1. **测试顺序**: 建议按照编号顺序运行测试
2. **依赖服务**: 
   - test_01-04, test_06 不需要API服务运行
   - test_05 需要先启动API服务（运行 start-fast.bat）
3. **数据库**: 确保MySQL数据库服务已启动
4. **环境**: 确保已激活 MyRAG Conda 环境

## 测试结果说明

- ✅ 表示测试通过
- ❌ 表示测试失败
- ⚠️  表示警告或跳过

## 故障排查

### 配置加载失败
- 检查 `Backend/config.yaml` 文件是否存在
- 验证配置文件格式是否正确

### 数据库连接失败
- 确认MySQL服务是否运行
- 检查数据库连接配置（host, port, user, password）
- 验证数据库 `myrag` 是否已创建

### 向量存储测试失败
- 检查 VectorDB 目录是否有写入权限
- 确认 ChromaDB 是否正确安装

### API端点测试失败
- 确保已运行 `start-fast.bat` 启动服务
- 检查端口 8000 是否被占用
- 查看服务日志是否有错误信息
