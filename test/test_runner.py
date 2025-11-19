#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试运行器 - 运行所有测试模块"""

import sys
import os
from pathlib import Path

# 添加Backend到路径
backend_path = Path(__file__).parent.parent / "Backend"
sys.path.insert(0, str(backend_path))

class TestRunner:
    """测试运行器"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def run_test_module(self, module_name, test_func):
        """运行单个测试模块"""
        print(f"\n{'='*60}")
        print(f"测试模块: {module_name}")
        print(f"{'='*60}")
        
        try:
            result = test_func()
            if result:
                self.passed += 1
                print(f"✅ {module_name} - 通过")
            else:
                self.failed += 1
                self.errors.append(f"{module_name}: 测试失败")
                print(f"❌ {module_name} - 失败")
        except Exception as e:
            self.failed += 1
            self.errors.append(f"{module_name}: {str(e)}")
            print(f"❌ {module_name} - 异常: {str(e)}")
    
    def print_summary(self):
        """打印测试摘要"""
        print(f"\n{'='*60}")
        print("测试摘要")
        print(f"{'='*60}")
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"总计: {self.passed + self.failed}")
        
        if self.errors:
            print(f"\n失败详情:")
            for error in self.errors:
                print(f"  - {error}")
        
        print(f"\n{'='*60}")
        if self.failed == 0:
            print("🎉 所有测试通过!")
        else:
            print(f"⚠️  有 {self.failed} 个测试失败")
        print(f"{'='*60}\n")


def main():
    """主函数"""
    runner = TestRunner()
    
    # 导入测试模块
    print("正在加载测试模块...")
    print("提示: 可以单独运行每个测试文件，例如: python test_01_config.py")
    print()
    
    try:
        from test_01_config import test_config
        from test_02_database import test_database
        from test_03_services import test_services
        from test_04_vector_store import test_vector_store
        from test_06_text_splitting import test_text_splitting
        
        # 运行测试（按模块）
        runner.run_test_module("01. 配置加载", test_config)
        runner.run_test_module("02. 数据库连接", test_database)
        runner.run_test_module("03. 服务单例", test_services)
        runner.run_test_module("04. 向量存储", test_vector_store)
        runner.run_test_module("06. 文本分割", test_text_splitting)
        
    except ImportError as e:
        print(f"❌ 导入测试模块失败: {e}")
        print("请确保所有测试文件都已创建")
        return 1
    
    # 打印摘要
    runner.print_summary()
    
    return 0 if runner.failed == 0 else 1


if __name__ == "__main__":
    exit(main())
