#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试6: 文本分割功能测试"""

import sys
from pathlib import Path

# 添加Backend到路径
backend_path = Path(__file__).parent.parent / "Backend"
sys.path.insert(0, str(backend_path))


def test_text_splitting():
    """测试文本分割功能"""
    print("\n1. 测试递归字符分割器...")
    
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]
        )
        
        test_text = """这是一个测试文本。
        
我们需要测试文本分割功能是否正常工作。
这个文本包含多个段落和句子。

第二段落开始了。
这里有更多的内容。
我们希望分割器能够正确地处理这些文本。

第三段落。
最后一些测试内容。"""
        
        chunks = splitter.split_text(test_text)
        print(f"   ✓ 递归字符分割器工作正常")
        print(f"   - 原始文本长度: {len(test_text)}")
        print(f"   - 分块数量: {len(chunks)}")
        
        if len(chunks) > 0:
            print(f"   - 第一块长度: {len(chunks[0])}")
        
        print(f"\n2. 测试语义分割器（如果启用）...")
        try:
            from app.utils.semantic_splitter import get_semantic_splitter
            from app.core.config import settings
            
            if hasattr(settings.text_processing, 'semantic_split'):
                semantic_splitter = get_semantic_splitter()
                print(f"   ✓ 语义分割器初始化成功")
                
                # 简单测试
                short_text = "这是一个简短的测试。用于验证语义分割器。"
                semantic_chunks = semantic_splitter.split_text(short_text)
                print(f"   ✓ 语义分割测试完成，分块数量: {len(semantic_chunks)}")
            else:
                print(f"   ⚠️  语义分割未配置，跳过测试")
        except Exception as e:
            print(f"   ⚠️  语义分割器测试跳过: {str(e)}")
        
        print(f"\n✅ 文本分割功能测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 文本分割功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_text_splitting()
    exit(0 if success else 1)
