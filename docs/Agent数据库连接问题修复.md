# Agent 数据库连接问题修复

## 问题描述

启动 Agent 服务时出现错误：
```
Failed to initialize agent service: 'DatabaseManager' object is not an iterator
```

## 原因分析

在 `Backend/app/api/agent.py` 中，错误地使用了 `next(get_db())`：

```python
# ❌ 错误写法
kb_service = KnowledgeBaseService(next(get_db()))
```

`get_db()` 返回的是 `DatabaseManager` 对象本身，不是迭代器，因此不能使用 `next()`。

## 解决方案

直接使用 `get_db()` 返回的 `DatabaseManager` 对象：

```python
# ✅ 正确写法
db_manager = get_db()
kb_service = KnowledgeBaseService(db_manager)
```

## 修复步骤

### 1. 已自动修复
文件 `Backend/app/api/agent.py` 已自动修复。

### 2. 重启服务

在运行后端服务的终端中：

```bash
# 按 Ctrl+C 停止当前服务

# 重新启动
python Backend/main.py
```

### 3. 验证修复

访问 Agent 界面并测试：
```
http://localhost:8000/static/agent-demo.html
```

尝试发送测试问题：
- "现在几点了？"
- "帮我计算 2+3"

如果能正常返回结果，说明修复成功！

## 技术细节

### DatabaseManager 的正确使用方式

```python
# 方式1: 直接传递 DatabaseManager 对象
db_manager = get_db()
service = SomeService(db_manager)

# 方式2: 在服务内部使用上下文管理器
class SomeService:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def query_data(self):
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM table")
            return cursor.fetchall()
```

### FastAPI 依赖注入的正确写法

如果要使用 FastAPI 的依赖注入：

```python
from fastapi import Depends

@app.get("/endpoint")
async def endpoint(db: DatabaseManager = Depends(get_db)):
    # 使用 db
    with db.get_cursor() as cursor:
        cursor.execute("SELECT ...")
```

## 相关文件

- `Backend/app/api/agent.py` - Agent API（已修复）
- `Backend/app/core/database.py` - 数据库管理器定义
- `Backend/app/services/knowledge_base_service.py` - 知识库服务

## 预防措施

在使用数据库服务时，记住：
1. ✅ `get_db()` 返回 `DatabaseManager` 对象
2. ❌ 不要使用 `next(get_db())`
3. ✅ 使用 `with db.get_cursor()` 或 `with db.get_connection()` 执行数据库操作

---

修复完成！现在 Agent 应该可以正常工作了 🎉
