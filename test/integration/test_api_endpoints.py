#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试5: API健康检查和基础端点测试"""

import sys
from pathlib import Path
import requests
import time

# 添加Backend到路径
backend_path = Path(__file__).parent.parent / "Backend"
sys.path.insert(0, str(backend_path))


def test_api_endpoints():
    """测试API端点"""
    base_url = "http://localhost:8000"
    
    print("\n1. 等待API服务启动...")
    max_retries = 3
    for i in range(max_retries):
        try:
            response = requests.get(f"{base_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"   ✓ API服务已启动")
                break
        except:
            if i < max_retries - 1:
                print(f"   ⏳ 等待中... ({i+1}/{max_retries})")
                time.sleep(2)
            else:
                print(f"   ❌ API服务未启动，请先运行 start-fast.bat")
                return False
    
    try:
        # 测试健康检查
        print(f"\n2. 测试健康检查端点...")
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ 健康检查通过: {data}")
        else:
            print(f"   ❌ 健康检查失败: {response.status_code}")
            return False
        
        # 测试API文档
        print(f"\n3. 测试API文档端点...")
        response = requests.get(f"{base_url}/docs")
        if response.status_code == 200:
            print(f"   ✓ API文档可访问")
        else:
            print(f"   ⚠️  API文档不可访问: {response.status_code}")
        
        # 测试知识库列表
        print(f"\n4. 测试知识库列表端点...")
        response = requests.get(f"{base_url}/api/knowledge-bases")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ 知识库列表获取成功，共 {len(data)} 个知识库")
        else:
            print(f"   ❌ 知识库列表获取失败: {response.status_code}")
            return False
        
        # 测试智能助手列表
        print(f"\n5. 测试智能助手列表端点...")
        response = requests.get(f"{base_url}/api/intelligent-assistants")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ 智能助手列表获取成功，共 {len(data)} 个助手")
        else:
            print(f"   ❌ 智能助手列表获取失败: {response.status_code}")
            return False
        
        # 测试模型列表
        print(f"\n6. 测试模型列表端点...")
        response = requests.get(f"{base_url}/api/models/list")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ 模型列表获取成功")
            if 'llm_models' in data:
                print(f"     - LLM模型: {len(data['llm_models'])} 个")
            if 'embedding_models' in data:
                print(f"     - 嵌入模型: {len(data['embedding_models'])} 个")
        else:
            print(f"   ❌ 模型列表获取失败: {response.status_code}")
            return False
        
        print(f"\n✅ API端点测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ API端点测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_api_endpoints()
    exit(0 if success else 1)
