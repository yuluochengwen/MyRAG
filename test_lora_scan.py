"""
测试 LoRA 扫描功能
验证是否能正确扫描 LLaMA-Training/saves 目录
"""
import sys
from pathlib import Path

# 添加 Backend 到路径
sys.path.insert(0, str(Path(__file__).parent / "Backend"))

from app.services.model_scanner import ModelScanner
from app.core.config import settings

def test_lora_scan():
    print("=" * 60)
    print("测试 LoRA 模型扫描功能")
    print("=" * 60)
    print()
    
    # 创建扫描器
    scanner = ModelScanner()
    
    # 显示扫描目录
    print(f"📁 Models/LoRA 目录: {scanner.lora_dir}")
    print(f"   存在: {scanner.lora_dir.exists()}")
    print()
    
    training_saves = scanner.base_dir / "LLaMA-Training" / "saves"
    print(f"📁 LLaMA-Training/saves 目录: {training_saves}")
    print(f"   存在: {training_saves.exists()}")
    print()
    
    # 扫描 LoRA 模型
    print("🔍 开始扫描 LoRA 模型...")
    print()
    
    lora_models = scanner.scan_lora_models()
    
    # 显示结果
    print(f"✅ 找到 {len(lora_models)} 个 LoRA 模型:")
    print()
    
    for i, model in enumerate(lora_models, 1):
        print(f"{i}. {model['name']}")
        print(f"   路径: {model['path']}")
        print(f"   基座模型: {model['base_model']}")
        print(f"   Rank: {model['rank']}")
        print(f"   Alpha: {model['lora_alpha']}")
        print(f"   大小: {model['size']}")
        print(f"   创建时间: {model['created_at']}")
        print()
    
    print("=" * 60)
    print("测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    test_lora_scan()
