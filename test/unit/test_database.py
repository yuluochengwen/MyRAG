#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试2: 数据库连接测试"""

import sys
from pathlib import Path

# 添加Backend到路径
backend_path = Path(__file__).parent.parent / "Backend"
sys.path.insert(0, str(backend_path))


def test_database():
    """测试数据库连接"""
    print("\n1. 测试数据库连接...")
    
    try:
        from app.core.database import DatabaseManager
        print(f"   ✓ 数据库模块导入成功")
        
        # 创建数据库管理器
        print(f"\n2. 创建数据库管理器...")
        db_manager = DatabaseManager()
        print(f"   ✓ 数据库管理器创建成功")
        
        # 测试连接
        print(f"\n3. 测试数据库连接...")
        with db_manager.get_connection() as conn:
            print(f"   ✓ 数据库连接成功")
            
            # 执行简单查询
            print(f"\n4. 执行测试查询...")
            cursor = conn.cursor()
            cursor.execute("SELECT 1 as test")
            result = cursor.fetchone()
            cursor.close()
            
            if result and result.get('test') == 1:
                print(f"   ✓ 查询执行成功")
            else:
                print(f"   ❌ 查询结果异常")
                return False
        
        # 测试表是否存在
        print(f"\n5. 检查数据库表...")
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            tables = ['knowledge_bases', 'files', 'text_chunks', 'conversations', 'messages', 'intelligent_assistants']
            for table in tables:
                cursor.execute(f"SHOW TABLES LIKE '{table}'")
                if cursor.fetchone():
                    print(f"   ✓ 表 {table} 存在")
                else:
                    print(f"   ⚠️  表 {table} 不存在")
            
            cursor.close()
            
        print(f"\n✅ 数据库连接测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 数据库连接测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_database()
    exit(0 if success else 1)
