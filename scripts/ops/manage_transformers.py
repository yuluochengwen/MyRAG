"""
Transformers模型管理工具
支持模型预加载、VRAM监控、量化配置
"""
import sys
import os
import asyncio
import json
from pathlib import Path
from typing import Optional

# 添加Backend到路径
backend_dir = Path(__file__).parent.parent / "Backend"
sys.path.insert(0, str(backend_dir))

import torch
from colorama import init, Fore, Style

# 初始化colorama
init(autoreset=True)


def print_header(text: str):
    """打印标题"""
    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{text.center(60)}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")


def print_success(text: str):
    """打印成功消息"""
    print(f"{Fore.GREEN}✓ {text}{Style.RESET_ALL}")


def print_error(text: str):
    """打印错误消息"""
    print(f"{Fore.RED}✗ {text}{Style.RESET_ALL}")


def print_info(text: str):
    """打印信息"""
    print(f"{Fore.YELLOW}ℹ {text}{Style.RESET_ALL}")


def check_gpu_status():
    """检查GPU状态"""
    print_header("GPU状态检查")
    
    if not torch.cuda.is_available():
        print_error("未检测到CUDA GPU")
        print_info("将使用CPU模式(性能较低)")
        return False
    
    gpu_count = torch.cuda.device_count()
    print_success(f"检测到 {gpu_count} 个CUDA GPU")
    
    for i in range(gpu_count):
        gpu_name = torch.cuda.get_device_name(i)
        props = torch.cuda.get_device_properties(i)
        total_memory = props.total_memory / 1024**3
        
        print(f"\n  GPU {i}: {gpu_name}")
        print(f"  总显存: {total_memory:.2f} GB")
        print(f"  计算能力: {props.major}.{props.minor}")
        
        # 显示当前显存使用
        allocated = torch.cuda.memory_allocated(i) / 1024**3
        reserved = torch.cuda.memory_reserved(i) / 1024**3
        free = total_memory - reserved
        
        print(f"  已分配: {allocated:.2f} GB")
        print(f"  已保留: {reserved:.2f} GB")
        print(f"  可用: {free:.2f} GB")
        
        # 显存建议
        if total_memory < 8:
            print_info(f"  建议: 显存<8GB,必须启用INT4量化")
        elif total_memory < 12:
            print_info(f"  建议: 显存<12GB,推荐启用INT8量化")
        else:
            print_success(f"  建议: 显存充足,可使用FP16")
    
    return True


def list_available_models():
    """列出可用模型"""
    print_header("可用模型列表")
    
    from app.core.config import settings
    models_dir = Path(settings.llm.local_models_dir) / "LLM"
    
    if not models_dir.exists():
        print_error(f"模型目录不存在: {models_dir}")
        return []
    
    models = []
    for model_dir in models_dir.iterdir():
        if not model_dir.is_dir():
            continue
        
        config_file = model_dir / "config.json"
        if not config_file.exists():
            continue
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 计算模型大小
            model_size = sum(
                f.stat().st_size 
                for f in model_dir.rglob('*.safetensors')
            ) / 1024**3
            
            architecture = config.get("architectures", ["Unknown"])[0]
            
            models.append({
                "name": model_dir.name,
                "path": str(model_dir),
                "architecture": architecture,
                "size_gb": model_size
            })
            
            print(f"  [{len(models)}] {model_dir.name}")
            print(f"      架构: {architecture}")
            print(f"      大小: {model_size:.2f} GB")
            
            # 显存估算
            estimated_vram = model_size * 1.2  # FP16
            estimated_vram_int8 = model_size * 0.6  # INT8
            estimated_vram_int4 = model_size * 0.4  # INT4
            
            print(f"      估算显存需求:")
            print(f"        FP16: {estimated_vram:.2f} GB")
            print(f"        INT8: {estimated_vram_int8:.2f} GB")
            print(f"        INT4: {estimated_vram_int4:.2f} GB")
            print()
            
        except Exception as e:
            print_error(f"读取模型{model_dir.name}失败: {e}")
            continue
    
    if not models:
        print_error("未找到可用模型")
    
    return models


async def load_model_interactive():
    """交互式加载模型"""
    print_header("模型加载")
    
    # 检查GPU
    has_gpu = check_gpu_status()
    
    # 列出模型
    models = list_available_models()
    if not models:
        return
    
    # 选择模型
    print("\n请选择要加载的模型:")
    try:
        choice = int(input(f"  请输入模型编号 (1-{len(models)}): "))
        if choice < 1 or choice > len(models):
            print_error("无效的选择")
            return
        
        selected_model = models[choice - 1]
        
    except ValueError:
        print_error("请输入数字")
        return
    
    # 选择量化方式
    print("\n请选择量化方式:")
    print("  [1] INT4 (最省显存,适合6GB显存)")
    print("  [2] INT8 (平衡性能和显存)")
    print("  [3] FP16 (最高质量,需要充足显存)")
    
    try:
        quant_choice = int(input("  请输入量化方式 (1-3): "))
        if quant_choice not in [1, 2, 3]:
            print_error("无效的选择")
            return
        
        quantize = quant_choice in [1, 2]
        
    except ValueError:
        print_error("请输入数字")
        return
    
    # 加载模型
    print(f"\n{Fore.CYAN}开始加载模型...{Style.RESET_ALL}")
    print(f"  模型: {selected_model['name']}")
    print(f"  量化: {'INT4' if quant_choice == 1 else 'INT8' if quant_choice == 2 else 'FP16'}")
    
    try:
        from app.services.transformers_service import transformers_service
        
        success = await transformers_service.load_model(
            selected_model['name'],
            quantize=quantize
        )
        
        if success:
            print_success(f"模型加载成功: {selected_model['name']}")
            
            # 显示显存使用
            if has_gpu:
                allocated = torch.cuda.memory_allocated(0) / 1024**3
                reserved = torch.cuda.memory_reserved(0) / 1024**3
                print(f"\n  显存使用:")
                print(f"    已分配: {allocated:.2f} GB")
                print(f"    已保留: {reserved:.2f} GB")
        else:
            print_error("模型加载失败")
            
    except Exception as e:
        print_error(f"加载模型时出错: {e}")
        import traceback
        traceback.print_exc()


async def test_chat():
    """测试聊天功能"""
    print_header("聊天测试")
    
    from app.services.transformers_service import transformers_service
    
    # 检查当前模型
    current_model = await transformers_service.get_current_model()
    if not current_model:
        print_error("未加载任何模型,请先加载模型")
        return
    
    print_success(f"当前模型: {current_model}")
    print_info("输入 'exit' 或 'quit' 退出")
    print()
    
    while True:
        try:
            user_input = input(f"{Fore.GREEN}User: {Style.RESET_ALL}")
            if user_input.lower() in ['exit', 'quit']:
                break
            
            if not user_input.strip():
                continue
            
            print(f"{Fore.BLUE}Assistant: {Style.RESET_ALL}", end="", flush=True)
            
            messages = [{"role": "user", "content": user_input}]
            response = await transformers_service.chat(
                model=current_model,
                messages=messages,
                temperature=0.7,
                max_tokens=512
            )
            
            print(response)
            print()
            
        except KeyboardInterrupt:
            print("\n\n对话已中断")
            break
        except Exception as e:
            print_error(f"生成回复时出错: {e}")


async def show_service_status():
    """显示服务状态"""
    print_header("服务状态")
    
    try:
        from app.services.transformers_service import transformers_service
        
        health = await transformers_service.check_health()
        
        print(f"  状态: {Fore.GREEN if health['status'] == 'healthy' else Fore.RED}{health['status']}{Style.RESET_ALL}")
        print(f"  设备: {health.get('device', 'N/A')}")
        print(f"  当前模型: {health.get('current_model', '未加载')}")
        print(f"  可用模型数: {health.get('models_available', 0)}")
        
        if 'gpu_name' in health:
            print(f"\n  GPU信息:")
            print(f"    名称: {health['gpu_name']}")
            print(f"    已分配显存: {health.get('gpu_memory_allocated_gb', 0):.2f} GB")
            print(f"    已保留显存: {health.get('gpu_memory_reserved_gb', 0):.2f} GB")
        
        # 列出所有模型
        models = await transformers_service.list_models()
        if models:
            print(f"\n  模型列表:")
            for model in models:
                status = "✓" if model['loaded'] else " "
                print(f"    [{status}] {model['name']}")
                print(f"        架构: {model['architecture']}")
                print(f"        大小: {model['size_gb']} GB")
        
    except Exception as e:
        print_error(f"获取服务状态失败: {e}")
        import traceback
        traceback.print_exc()


async def unload_current_model():
    """卸载当前模型"""
    print_header("卸载模型")
    
    try:
        from app.services.transformers_service import transformers_service
        
        current_model = await transformers_service.get_current_model()
        if not current_model:
            print_info("没有已加载的模型")
            return
        
        print(f"  当前模型: {current_model}")
        confirm = input(f"  确认卸载? (y/n): ")
        
        if confirm.lower() != 'y':
            print_info("已取消")
            return
        
        success = await transformers_service.unload_model()
        if success:
            print_success("模型已卸载,显存已释放")
        else:
            print_error("卸载失败")
            
    except Exception as e:
        print_error(f"卸载模型时出错: {e}")


async def main_menu():
    """主菜单"""
    while True:
        print_header("Transformers模型管理")
        
        print("  [1] 检查GPU状态")
        print("  [2] 列出可用模型")
        print("  [3] 加载模型")
        print("  [4] 卸载当前模型")
        print("  [5] 查看服务状态")
        print("  [6] 测试聊天")
        print("  [0] 退出")
        
        try:
            choice = input(f"\n{Fore.CYAN}请选择操作: {Style.RESET_ALL}")
            
            if choice == '0':
                print_info("再见!")
                break
            elif choice == '1':
                check_gpu_status()
            elif choice == '2':
                list_available_models()
            elif choice == '3':
                await load_model_interactive()
            elif choice == '4':
                await unload_current_model()
            elif choice == '5':
                await show_service_status()
            elif choice == '6':
                await test_chat()
            else:
                print_error("无效的选择")
            
            input(f"\n{Fore.CYAN}按Enter继续...{Style.RESET_ALL}")
            
        except KeyboardInterrupt:
            print("\n")
            print_info("程序已中断")
            break
        except Exception as e:
            print_error(f"操作失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main_menu())
